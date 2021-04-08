# srl-demo-agent
A sample custom Python agent running in SRLinux

## Installation
One way is to install 'git' on SRLinux, then check out the sources:
- Edit /etc/resolv.conf to add reachable nameservers, if needed
- `yum install -y git`
- `git clone https://github.com/jbemmel/srl-demo-agent.git /etc/opt/srlinux/appmgr`
- Restart appmgr (in SRLinux): `tools system app-management application app_mgr reload`

## Configuration
```
enter candidate
demo-fib-agent
input-fib /etc/opt/srlinux/appmgr/demo_routes.json
action add
commit now
```
