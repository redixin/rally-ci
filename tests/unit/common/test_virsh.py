
import mock
from mock import call
import unittest

from rallyci.common import virsh

# {{{
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
# }}}

SAMPLE_CONFIG = {"ssh": {"user": "root", "host": "example.net"}}


class VMTestCase(unittest.TestCase):

    def test__get_bridge(self):
        conf = mock.Mock()
        env = mock.Mock()
        env.ifs = {}
        vm = virsh.VM(conf, SAMPLE_CONFIG, env)
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

class VolumeTestCase(unittest.TestCase):

    def setUp(self):
        super(VolumeTestCase, self).setUp()
        self._m_utils = mock.patch('rallyci.common.virsh.utils')
        self.m_utils = self._m_utils.start()
        self.m_utils.get_rnd_name.return_value = "rnd_name"

        self.ssh = mock.Mock()
        self.xml = mock.MagicMock()

    def tearDown(self):
        self._m_utils.stop()

    def test_zfs(self):
        zfs = virsh.ZFS(self.ssh, "tank/src@1")
        zfs.build()
        self.ssh.run.assert_called_once_with("zfs clone tank/src@1 tank/rnd_name")

        zfs.gen_xml(self.xml)
        xml_calls = [
                call.disk(device='disk', type='block'),
                call.disk().__enter__(),
                call.driver(cache='directsync', type='raw', name='qemu', io='native'),
                call.source(dev='/dev/zvol/tank/rnd_name'),
                call.target(bus='virtio', dev='vda'),
                call.disk().__exit__(None, None, None),
            ]
        self.assertEqual(xml_calls, self.xml.mock_calls)

        zfs.cleanup()
        self.ssh.run.assert_has_calls(call('zfs destroy tank/rnd_name'))
        self.ssh.close.assert_called_once_with()

    def test_zfs_file(self):
        self.ssh.execute.return_value = [0, "img1.qcow2\nimg2.qcow2", ""]
        zfsf = virsh.ZFSFile(self.ssh, "tank/qcow", "img1@1")
        zfsf.build()
        self.ssh.run.assert_called_once_with("zfs clone tank/qcow/img1@1 tank/qcow/rnd_name")

        zfsf.gen_xml(self.xml)
        xml_calls = [
                call.disk(device='disk', type='file'),
                call.disk().__enter__(),
                call.driver(cache='unsafe', type='qcow2', name='qemu'),
                call.source(file='/tank/qcow/rnd_name/img1.qcow2'),
                call.target(bus='virtio', dev='vda'),
                call.disk().__exit__(None, None, None),
                call.disk(device='disk', type='file'),
                call.disk().__enter__(),
                call.driver(cache='unsafe', type='qcow2', name='qemu'),
                call.source(file='/tank/qcow/rnd_name/img2.qcow2'),
                call.target(bus='virtio', dev='vdb'),
                call.disk().__exit__(None, None, None),
            ]
        self.assertEqual(xml_calls, self.xml.mock_calls)

        zfsf.cleanup()
        self.ssh.run.assert_has_calls(call("zfs destroy tank/qcow/rnd_name"))
