# srl-demo-agent
A sample custom Python agent running in SRLinux

This simple example demo agent
1. Registers a custom YAML model for CLI based configuration (path to a .json file with routes)
2. Upon configuration, reads the routes from the .json file and programs them into the datapath

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
