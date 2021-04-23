# srl-demo-agent
A sample custom Python agent running in SR Linux

This simple example demo agent
1. Registers a custom YAML model for CLI based configuration (path to a .json file with routes)
2. Upon configuration, reads the routes from the .json file and programs them into the datapath

The intent is to illustrate the components required to deploy a custom agent on SRL; this can be used as the basis for your own development.
Specifically:
1. [demo_fib_agent.py] contains the Python code for the agent (single file)
2. demo_fib_agent.sh is a shell script to launch the Python agent, referenced from the .yml file
3. demo_fib_agent.yang is a YANG model for the configuration and state information provided by the Python agent
4. demo_fib_agent.yml is a YAML file that tells SRL where to find the custom agent to be loaded
5. demo_routes.json is an agent specific sample input file (least important)

## NetOps cycle enhancements

In addition to a sample Python agent, this repo contains some ideas and tricks to speed up development.

## Installation
One way is to install 'git' on SRLinux, then check out the sources:
- Edit /etc/resolv.conf to add reachable nameservers, if needed
- `sudo yum install -y git`
- `sudo git clone https://github.com/jbemmel/srl-demo-agent.git /etc/opt/srlinux/appmgr`
- Restart appmgr (in SRLinux): `tools system app-management application app_mgr reload`

## Configuration
```
enter candidate
demo-fib-agent
input-fib /etc/opt/srlinux/appmgr/demo_routes.json
action add
commit now
```
## Check routes
```
A:srl# show network-instance mgmt route-table ipv4-unicast summary                                                                                                                                                 
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
IPv4 Unicast route table of network instance mgmt
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
+--------------------------------------------+-------+------------+-----------------+---------+-------+-------------------------------------------------------------+---------------------------+
|                   Prefix                   |  ID   |   Active   |      Owner      | Metric  | Pref  |                       Next-hop (Type)                       |    Next-hop Interface     |
+============================================+=======+============+=================+=========+=======+=============================================================+===========================+
| 0.0.0.0/0                                  | 0     | true       | dhcp            | 0       | 5     | 172.20.20.1 (direct)                                        | mgmt0.0                   |
| 150.1.1.0/24                               | 0     | true       | ** sdk **       | 0       | 100   | 1.2.3.4 (static-mpls)                                       | None                      |
| 172.20.20.0/24                             | 0     | true       | local           | 0       | 0     | 172.20.20.3 (direct)                                        | mgmt0.0                   |
| 172.20.20.0/24                             | 1     | false      | linux           | 0       | 5     | 172.20.20.0 (direct)                                        | mgmt0.0                   |
| 172.20.20.3/32                             | 0     | true       | host            | 0       | 0     | None (extract)                                              | None                      |
| 172.20.20.255/32                           | 0     | true       | host            | 0       | 0     | None (broadcast)                                            | None                      |
+--------------------------------------------+-------+------------+-----------------+---------+-------+-------------------------------------------------------------+---------------------------+
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
6 IPv4 routes total
5 IPv4 prefixes with active routes
0 IPv4 prefixes with active ECMP routes
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
--{ [FACTORY] + running }--[ demo-fib-agent ]--
```
