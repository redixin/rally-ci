
import mock
import unittest

from rallyci.environments.virsh import Environment, VM

SAMPLE_IP_LINK_LIST = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default 
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 0c:c4:7a:13:89:52 brd ff:ff:ff:ff:ff:ff
3: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 0c:c4:7a:13:89:53 brd ff:ff:ff:ff:ff:ff
4: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default 
    link/ether fe:54:00:3b:84:70 brd ff:ff:ff:ff:ff:ff
5: br1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN mode DEFAULT group default 
    link/ether 00:00:00:00:00:00 brd ff:ff:ff:ff:ff:ff
126: vnet12: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast master br0 state UNKNOWN mode DEFAULT group default qlen 500
    link/ether fe:54:00:3b:84:70 brd ff:ff:ff:ff:ff:ff
1178: nr0: <NOARP> mtu 236 qdisc noop state DOWN mode DEFAULT group default 
    link/generic 00:00:00:00:00:00:00 brd 00:00:00:00:00:00:00
1181: nr3: <NOARP> mtu 236 qdisc noop state DOWN mode DEFAULT group default 
    link/generic 00:00:00:00:00:00:00 brd 00:00:00:00:00:00:00
1182: rose0: <NOARP> mtu 249 qdisc noop state DOWN mode DEFAULT group default 
    link/rose 00:00:00:00:00 brd 00:00:00:00:00
1191: rose9: <NOARP> mtu 249 qdisc noop state DOWN mode DEFAULT group default 
    link/rose 00:00:00:00:00 brd 00:00:00:00:00
433: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN mode DEFAULT group default 
    link/ether 56:84:7a:fe:97:99 brd ff:ff:ff:ff:ff:ff
"""

SAMPLE_CONFIG = {"host": ["user", "host"]}

class VMTestCase(unittest.TestCase):

    def test__get_bridge(self):
        conf = mock.Mock()
        job = mock.Mock()
        vm = VM(conf, SAMPLE_CONFIG)
        vm.ssh = mock.Mock()
        vm.ssh.execute.return_value = (0, SAMPLE_IP_LINK_LIST, "")
        self.assertEqual("nr1", vm._get_bridge("nr"))
        self.assertEqual("ok0", vm._get_bridge("ok"))
        calls = [
                mock.call("ip link add nr1 type bridge"),
                mock.call("ip link set nr1 up"),
                mock.call("ip link add ok0 type bridge"),
                mock.call("ip link set ok0 up"),
                ]
        self.assertEqual(calls, vm.ssh.run.mock_calls)
        self.assertEqual(["nr1", "ok0"], vm.ifs)
