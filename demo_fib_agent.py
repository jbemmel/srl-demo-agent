#!/usr/bin/env python
# coding=utf-8

import grpc
import datetime
import sys
import logging
import socket
import os
import ipaddress
import json
import signal
import subprocess # JvB for git pull call

import sdk_service_pb2
import sdk_service_pb2_grpc
import lldp_service_pb2
import interface_service_pb2
import networkinstance_service_pb2
import route_service_pb2
import route_service_pb2_grpc
import nexthop_group_service_pb2
import nexthop_group_service_pb2_grpc
import mpls_service_pb2
import mpls_service_pb2_grpc
import config_service_pb2
import telemetry_service_pb2
import telemetry_service_pb2_grpc
import sdk_common_pb2
from logging.handlers import RotatingFileHandler

############################################################
## Agent will start with this name
############################################################
agent_name='demo_fib_agent'

############################################################
## Open a GRPC channel to connect to sdk_mgr on the dut
## sdk_mgr will be listening on 50053
############################################################
#channel = grpc.insecure_channel('unix:///opt/srlinux/var/run/sr_sdk_service_manager:50053')
channel = grpc.insecure_channel('127.0.0.1:50053')
metadata = [('agent_name', agent_name)]
stub = sdk_service_pb2_grpc.SdkMgrServiceStub(channel)
pushed_routes = 0

############################################################
## Subscribe to required event
## This proc handles subscription of: Interface, LLDP,
##                      Route, Network Instance, Config
############################################################
def Subscribe(stream_id, option):
    op = sdk_service_pb2.NotificationRegisterRequest.AddSubscription
    if option == 'intf':
        entry = interface_service_pb2.InterfaceSubscriptionRequest()
        request = sdk_service_pb2.NotificationRegisterRequest(op=op, stream_id=stream_id, intf=entry)
    elif option == 'nw_inst':
        entry = networkinstance_service_pb2.NetworkInstanceSubscriptionRequest()
        request = sdk_service_pb2.NotificationRegisterRequest(op=op, stream_id=stream_id, nw_inst=entry)
    elif option == 'lldp':
        entry = lldp_service_pb2.LldpNeighborSubscriptionRequest()
        request = sdk_service_pb2.NotificationRegisterRequest(op=op, stream_id=stream_id, lldp_neighbor=entry)
    elif option == 'route':
        entry = route_service_pb2.IpRouteSubscriptionRequest()
        request = sdk_service_pb2.NotificationRegisterRequest(op=op, stream_id=stream_id, route=entry)
    elif option == 'cfg':
        entry = config_service_pb2.ConfigSubscriptionRequest()
        request = sdk_service_pb2.NotificationRegisterRequest(op=op, stream_id=stream_id, config=entry)
    subscription_response = stub.NotificationRegister(request=request, metadata=metadata)
    print('Status of subscription response for {}:: {}'.format(option, subscription_response.status))

############################################################
## Subscribe to all the events that Agent needs
############################################################
def Subscribe_Notifications(stream_id):
    '''
    Agent will receive notifications to what is subscribed here.
    '''
    if not stream_id:
        logging.info("Stream ID not sent.")
        return False

    ##Subscribe to Interface Notifications
    Subscribe(stream_id, 'intf')

    ##Subscribe to Network-Instance Notifications
    Subscribe(stream_id, 'nw_inst')

    ##Subscribe to LLDP Neighbor Notifications
    Subscribe(stream_id, 'lldp')

    ##Subscribe to IP Route Notifications
    Subscribe(stream_id, 'route')

    ##Subscribe to Config Notifications - configs added by the fib-agent
    Subscribe(stream_id, 'cfg')


############################################################
## Function to populate state of agent config
## using telemetry -- add/update info from state
############################################################
def Add_Telemetry(js_path, js_data ):
    telemetry_stub = telemetry_service_pb2_grpc.SdkMgrTelemetryServiceStub(channel)
    telemetry_update_request = telemetry_service_pb2.TelemetryUpdateRequest()
    telemetry_info = telemetry_update_request.state.add()
    telemetry_info.key.js_path = js_path
    telemetry_info.data.json_content = js_data
    logging.info(f"Telemetry_Update_Request :: {telemetry_update_request}")
    telemetry_response = telemetry_stub.TelemetryAddOrUpdate(request=telemetry_update_request, metadata=metadata)
    return telemetry_response

############################################################
## Function to cleanup state of agent config
## using telemetry -- cleanup info from state
############################################################
def Delete_Telemetry(js_path):
    telemetry_stub = telemetry_service_pb2_grpc.SdkMgrTelemetryServiceStub(channel)
    telemetry_delete_request = telemetry_service_pb2.TelemetryDeleteRequest()
    telemetry_delete = telemetry_delete_request.key.add()
    telemetry_delete.js_path = js_path
    logging.info(f"Telemetry_Delete_Request :: {telemetry_delete_request}")
    telemetry_response = telemetry_stub.TelemetryDelete(request=telemetry_delete_request, metadata=metadata)
    return telemetry_response

############################################################
## Function to populate state fields of the agent
## It updates command: info from state fib-agent
############################################################
def Update_Result(input_fib, result=True, reason=None, action='add'):
    js_path = '.demo_fib_agent.fib_result{.name=="' + input_fib + '"}'
    json_content='{"fib_result": '
    if action == 'add':
        for key in ['programmed-state', 'reason-code']:
            if key == 'programmed-state':
                json_content=json_content+ '{ "programmed_state" : {"value": ' + str(result).lower()+' },'
            else:
                if result == False:
                    code = reason
                else:
                    code = None
                json_content =json_content+  '"reason_code" : {"value": "' + str(code) +'"}'
        json_content =json_content+'}}'
        response = Add_Telemetry(js_path=js_path, js_data=json_content)
        logging.info(f"Telemetry_Update_Response :: {response}")
        return True
    elif action =='delete':
        response = Delete_Telemetry(js_path=js_path)
        logging.info(f"Telemetry_Delete_Response :: {response}")
        return True
    else:
        assert False, "Got unrecognized action"
    return True

############################################################
## Function to populate number of route count received by agent
## It updates command: info from state fib-agent route-count
############################################################
def Update_Routes(programmed, actual=None):
    json_content = ''
    js_path = '.demo_fib_agent'
    json_content = '{"programmed_routes": {"value": ' + str(programmed) + '},'
    if actual:
        route_count = actual
    else:
        route_count = pushed_routes
    json_content = json_content + '"route_count": {"value": ' + str(route_count) + '}}'

    Add_Telemetry(js_path=js_path, js_data=json_content)
    return True

############################################################
## Process Nexthop group add or replace request
## add/replace the given nexthop groups in the input fib
## data is picked from fib['nh_groups']
############################################################
def Handle_Nexthop_Group_Add_Request(action, fib, res):
    nhg_stub = nexthop_group_service_pb2_grpc.SdkMgrNextHopGroupServiceStub(channel)
    if action =='replace':
        nhg_stub.SyncStart(request=sdk_common_pb2.SyncRequest(),metadata=metadata)
    nh_request = nexthop_group_service_pb2.NextHopGroupRequest()
    for nhg in fib['nh_groups']:
        nhg_info = nh_request.group_info.add()
        nhg_info.key.network_instance_name = nhg['network_instance']
        nhg_info.key.name = nhg['name']
        for entry in nhg['entry']:
            nh = nhg_info.data.next_hop.add()
            ip = ipaddress.ip_address(entry['ip_nexthop'])
            nh_type = entry.get('type', 'direct')
            if nh_type == 'indirect':
                nh.resolve_to = nexthop_group_service_pb2.NextHop.INDIRECT

            #if 'egress_label' in entry:
            #    for lbl in entry['egress_label']:
            #        label = nh.mpls_nexthop.label_stack.add()
            #        label.mpls_label = int(lbl)
            #    nh.mpls_nexthop.ip_nexthop.addr = ip.packed
            #else:
            nh.ip_nexthop.addr = ip.packed

    logging.info(f"NH_REQUEST :: {nh_request}")
    nhg_response = nhg_stub.NextHopGroupAddOrUpdate(request=nh_request,metadata=metadata)
    logging.info(f"NH RESPONSE:: {nhg_response}")
    if  nhg_response.status !=0:
        res=False
    logging.info(f"NHG status:{nhg_response.status}")
    logging.info(f"NHG error:{nhg_response.error_str}")

    if action == 'replace':
        nhg_sync_response = nhg_stub.SyncEnd(request=sdk_common_pb2.SyncRequest(),metadata=metadata)
        logging.info(nhg_sync_response)

    return res

############################################################
## Process Nexthop group delete request
## delete the given nexthop groups in the input fib
## data is picked from fib['nh_groups']
############################################################
def Handle_Nexthop_Group_Del_Request(fib, res):
    nhg_stub = nexthop_group_service_pb2_grpc.SdkMgrNextHopGroupServiceStub(channel)
    nh_request = nexthop_group_service_pb2.NextHopGroupDeleteRequest()
    for nhg in fib['nh_groups']:
        nhg_key = nh_request.group_key.add()
        nhg_key.network_instance_name = nhg['network_instance']
        nhg_key.name = nhg['name']

    logging.info(f"NHG DEL REQUEST :: {nh_request}")
    nhg_del_response = nhg_stub.NextHopGroupDelete(request=nh_request,metadata=metadata)
    logging.info(f"NHG DELETE RESPONSE:: {nhg_del_response}")
    if nhg_del_response.status !=0:
        res=False
    logging.info(f"NHG status:{nhg_del_response.status}")
    logging.info(f"NHG error:{nhg_del_response.error_str}")
    return res

############################################################
## Process IP Route add or replace request
## add/replace the given IP routes in the input fib
## data is picked from fib['ip_table']
############################################################
def Handle_Route_Add_Request(action, fib, res):
    route_stub = route_service_pb2_grpc.SdkMgrRouteServiceStub(channel)
    route_count = 0
    global pushed_routes
    if action =='replace':
        route_stub.SyncStart(request=sdk_common_pb2.SyncRequest(),metadata=metadata)
    route_request = route_service_pb2.RouteAddRequest()
    for ip in fib['ip_table']:
        route_info = route_request.routes.add()
        if 'preference' in ip:
            route_info.data.preference = ip['preference']
        if 'metric' in ip:
            route_info.data.metric = ip['metric']
        prefix = ip['prefix'].split("/")
        ipaddr = ipaddress.ip_address(prefix[0])
        route_info.key.net_inst_name = ip['network_instance']
        route_info.key.ip_prefix.ip_addr.addr = ipaddr.packed
        route_info.key.ip_prefix.prefix_length = int(prefix[1])
        route_info.data.nexthop_group_name = ip['nexthop_group_name']
        route_count += 1

    logging.info(f"ROUTE REQUEST :: {route_request}")
    route_response = route_stub.RouteAddOrUpdate(request=route_request,metadata=metadata)
    logging.info(f"ROUTE RESPONSE:: {route_response}")
    if route_response.status !=0:
        res=False
    logging.info(f"Route status:{route_response.status}")
    logging.info(f"Route error:{route_response.error_str}")
    pushed_routes += route_count

    if action =='replace':
        pushed_routes = route_count
        route_sync_response = route_stub.SyncEnd(request=sdk_common_pb2.SyncRequest(),metadata=metadata)
        logging.info(route_sync_response)

    return res

############################################################
## Process IP Route delete request
## delete the given IP routes in the input fib
## data is picked from fib['ip_table']
############################################################
def Handle_Route_Del_Request(fib, res):
    route_stub = route_service_pb2_grpc.SdkMgrRouteServiceStub(channel)
    route_request = route_service_pb2.RouteDeleteRequest()
    del_route_count = 0
    global pushed_routes
    for ip in fib['ip_table']:
        route_info = route_request.routes.add()
        if 'prefix' in ip:
            prefix = ip['prefix'].split("/")
            ipaddr = ipaddress.ip_address(prefix[0])
            route_info.ip_prefix.ip_addr.addr = ipaddr.packed
            route_info.ip_prefix.prefix_length = int(prefix[1])
        if 'network_instance' in ip:
            route_info.net_inst_name = ip['network_instance']
        del_route_count += 1

    logging.info(f"IP ROUTE DEL REQUEST :: {route_request}")
    route_del_response = route_stub.RouteDelete(request=route_request,metadata=metadata)
    logging.info(f"IP ROUTE DELETE RESPONSE:: {route_del_response}")
    if route_del_response.status !=0:
        res=False
    logging.info(f"IP route status:{route_del_response.status}")
    logging.info(f"IP route error:{route_del_response.error_str}")
    pushed_routes = pushed_routes - del_route_count
    return res

##################################################################################################
## Program the routes that agent received in input-fib
## Update Success or Failure to the state output
## Action can be add/delete/replace
## When action is add/replace: data is picked from ['fib'] section of the input json
## When action is delete: data is picked from ['delete'] section of the input json
##################################################################################################
def ProgramFibRoutes(input_fib=None, action='add'):
    '''
    Actions : add/delete/replace
    input_fib is the input json fib file
    Based on the actions, this function will process the input fib json and add or delete routes/mpls labels/nexthop groups accordingly
    '''
    fib_data={}
    res=True
    if input_fib == '':
        logging.info('Nothing to process and no input-fib received')
        return

    try:
        with open(input_fib) as f:
            fib_data = json.load(f)
    except Exception as e:
        logging.info(f"Exception caught while reading file :: {e}")
        #Set programed status as false
        return False

    if action == 'delete':
        if 'delete' not in fib_data:
            logging.error('data to delete not present in the input fib file')
            return False
        fib = fib_data['delete']
    elif action=='add':
        if 'fib' not in fib_data:
            logging.error('data to add not present in the input fib file')
            return False
        fib = fib_data['fib']
    elif action=='replace':
        if 'fib' not in fib_data:
            logging.error('data to replace not present in the input fib file')
            return False
        fib = fib_data['fib']

    ## Process add or replace of fib
    if action == 'add' or action =='replace':
        if 'nh_groups' in fib and fib['nh_groups']:
            res = Handle_Nexthop_Group_Add_Request(action, fib, res)
        if 'ip_table' in fib and fib['ip_table']:
            res = Handle_Route_Add_Request(action, fib, res)
        #if 'mpls_table' in fib and fib['mpls_table']:
        #    res = Handle_Mpls_Add_Request(action, fib, res)
    ## Process delete of fib
    elif action == 'delete':
        if 'ip_table' in fib and fib['ip_table']:
            res = Handle_Route_Del_Request(fib, res)
        #if 'mpls_table' in fib and fib['mpls_table']:
        #    res = Handle_Mpls_Del_Request(fib, res)
        if 'nh_groups' in fib and fib['nh_groups']:
            res = Handle_Nexthop_Group_Del_Request(fib, res)

    ## Update the result of fib programming
    Update_Result(input_fib, result=res, action='add')
    return res

##################################################################
## Proc to process the config Notifications received by fib_agent
## At present processing config from js_path = .fib-agent
##################################################################
def Handle_Notification(obj, file_name, app_id, route_count):
    if obj.HasField('config') and obj.config.key.js_path != ".commit.end":
        logging.info(f"GOT CONFIG :: {obj.config.key.js_path}")
        logging.info(f"OLD FILE :: {file_name}")
        logging.info(f"Handle_Config with file_name as {file_name}")
        if "demo_fib_agent" in obj.config.key.js_path:
            logging.info(f"Got config for agent, now will handle it :: \n{obj.config}\
                            Operation :: {obj.config.op}\nData :: {obj.config.data.json}")
            if obj.config.op == 2:
                logging.info(f"Delete fib-agent cli scenario")
                if file_name != None:
                    Update_Result(file_name, action='delete')
                response=stub.AgentUnRegister(request=sdk_service_pb2.AgentRegistrationRequest(), metadata=metadata)
                route_count=0
                logging.info('Handle_Config: Unregister response:: {}'.format(response))
            else:
                json_acceptable_string = obj.config.data.json.replace("'", "\"")
                data = json.loads(json_acceptable_string)
                if 'input_fib' in data:
                    fib = data['input_fib']['value']
                    #delete old file's state before updating filename var with new input-file
                    if file_name != None:
                        Update_Result(file_name, action='delete')
                    logging.info(f"Got input-fib :: {data['input_fib']['value']}")
                    #if action is not set in cli, default it to 'add'
                    if 'action' in data:
                        action = data['action'][7:] # skip "ACTION_xxx"
                    else:
                        action = 'add'
                    logging.info(f"Action received is : {action}")
                    file_name=fib
                    if not ProgramFibRoutes(input_fib=fib, action=action):
                        logging.info(f"Something went wrong during action : {action}")
                        #update the file's status to be False and populate reason code
                        Update_Result(file_name, action='add',result=False,reason="ERROR:Couldnt program fib")
#                    global pushed_routes
                    Update_Routes(programmed=route_count, actual=pushed_routes)
            return file_name, route_count
    elif obj.HasField('route'):
        # Update the status if route info got
        if obj.route.data.owner_id == app_id:
            addr = ipaddress.ip_address(obj.route.key.ip_prefix.ip_addr.addr).__str__()
            prefix = obj.route.key.ip_prefix.prefix_length
            # process delete
            if obj.route.op == 2:
                logging.info(f'Got delete for route {addr}/{prefix}')
                route_count -= 1
                Update_Routes(programmed=route_count)
            elif obj.route.op == 1:
                # process modifications where we do not need any route count updates
                pass
            else:
                # proces add route scenario
                route_count += 1
                #logging.info(f'Got Route added by agent: {obj.route}')
                nhs = ''
                # Considering only ip nexthops. Will process mpls_next hops once dts319345 is resolved
                for nh in obj.route.data.nexthop:
                    logging.info(f'Route Nexthop to be processed - {nh}')
                    # for MPLS nexthop v/s IP nexthop
                    if nh.type==2:
                        nhs +=ipaddress.ip_address(nh.mpls_nexthop.ip_nexthop.addr).__str__() + ', '
                    else:
                        nhs += ipaddress.ip_address(nh.ip_nexthop.addr).__str__() + ', '
                logging.info(f'Route {addr}/{prefix} added by agent with nexthops {nhs}')
                Update_Routes(programmed=route_count)

        return file_name, route_count
    else:
        return file_name, route_count
    #always return
    return file_name, route_count
##################################################################################################
## This functions get the app_id from idb for a given app_name
##################################################################################################
def get_app_id(app_name):
    logging.info(f'Metadata {metadata} ')
    appId_req = sdk_service_pb2.AppIdRequest(name=app_name)
    app_id_response=stub.GetAppId(request=appId_req, metadata=metadata)
    logging.info(f'app_id_response {app_id_response.status} {app_id_response.id} ')
    return app_id_response.id

##################################################################################################
## This is the main proc where all processing for fib_agent starts.
## Agent registration, notification registration, Subscrition to notifications.
## Waits on the subscribed Notifications and once any config is received, handles that config
## If there are critical errors, Unregisters the fib_agent gracefully.
##################################################################################################
def Run():
    sub_stub = sdk_service_pb2_grpc.SdkNotificationServiceStub(channel)

    response = stub.AgentRegister(request=sdk_service_pb2.AgentRegistrationRequest(), metadata=metadata)
    logging.info(f"Registration response : {response.status}")

    app_id = get_app_id(agent_name)
    if not app_id:
        logging.error(f'idb does not have the appId for {agent_name} : {app_id}')
    else:
        logging.info(f'Got appId {app_id} for {agent_name}')

    request=sdk_service_pb2.NotificationRegisterRequest(op=sdk_service_pb2.NotificationRegisterRequest.Create)
    create_subscription_response = stub.NotificationRegister(request=request, metadata=metadata)
    stream_id = create_subscription_response.stream_id
    logging.info(f"Create subscription response received. stream_id : {stream_id}")

    Subscribe_Notifications(stream_id)

    stream_request = sdk_service_pb2.NotificationStreamRequest(stream_id=stream_id)
    stream_response = sub_stub.NotificationStream(stream_request, metadata=metadata)
    file_name=None
    count = 1
    route_count = 0
    try:
        for r in stream_response:
            logging.info(f"Count :: {count}  NOTIFICATION:: \n{r.notification}")
            count += 1
            for obj in r.notification:
                if obj.HasField('config') and obj.config.key.js_path == ".commit.end":
                    logging.info('TO DO -commit.end config')
                else:
                    file_name, route_count = Handle_Notification(obj, file_name, app_id, route_count)
    except grpc._channel._Rendezvous as err:
        logging.info('GOING TO EXIT NOW, DOING FINAL git pull: {}'.format(err))
        try:
           # Need to execute this in the mgmt network namespace, hardcoded name for now
           git_pull = subprocess.Popen(['/usr/sbin/ip','netns','exec','srbase-mgmt','/usr/bin/git','pull'],
                                       cwd='/etc/opt/srlinux/appmgr',
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
           stdoutput, stderroutput = git_pull.communicate()
           logging.info(f'git pull result: {stdoutput} err={stderroutput}')
        except Exception as e:
           logging.error(f'Exception caught in git pull :: {e}')

    except Exception as e:
        logging.error('Exception caught :: {}'.format(e))
        if file_name != None:
            Update_Result(file_name, action='delete')
        try:
            response = stub.AgentUnRegister(request=sdk_service_pb2.AgentRegistrationRequest(), metadata=metadata)
            logging.error('Run try: Unregister response:: {}'.format(response))
        except grpc._channel._Rendezvous as err:
            logging.info('GOING TO EXIT NOW: {}'.format(err))
            sys.exit()
        return True
    sys.exit()
    return True
############################################################
## Gracefully handle SIGTERM signal
## When called, will unregister Agent and gracefully exit
############################################################
def Exit_Gracefully(signum, frame):
    logging.info("Caught signal :: {}\n will unregister fib_agent".format(signum))
    try:
        response=stub.AgentUnRegister(request=sdk_service_pb2.AgentRegistrationRequest(), metadata=metadata)
        logging.error('try: Unregister response:: {}'.format(response))
        sys.exit()
    except grpc._channel._Rendezvous as err:
        logging.info('GOING TO EXIT NOW: {}'.format(err))
        sys.exit()

##################################################################################################
## Main from where the Agent starts
## Log file is written to: /var/log/srlinux/stdout/<dutName>_fibagent.log
## Signals handled for graceful exit: SIGTERM
##################################################################################################
if __name__ == '__main__':
    # hostname = socket.gethostname()
    stdout_dir = '/var/log/srlinux/stdout' # PyTEnv.SRL_STDOUT_DIR
    signal.signal(signal.SIGTERM, Exit_Gracefully)
    if not os.path.exists(stdout_dir):
        os.makedirs(stdout_dir, exist_ok=True)
    log_filename = '{}/demo_fibagent.log'.format(stdout_dir)
    logging.basicConfig(filename=log_filename, filemode='a',\
                        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',\
                        datefmt='%H:%M:%S', level=logging.INFO)
    handler = RotatingFileHandler(log_filename, maxBytes=3000000,backupCount=5)
    logging.getLogger().addHandler(handler)
    logging.info("START TIME :: {}".format(datetime.datetime.now()))
    if Run():
        logging.info('Agent unregistered and agent routes withdrawed from dut')
    else:
        logging.info('Should not happen')
