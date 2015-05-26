# Copyright 2015: Mirantis Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import unittest

from rallyci.runners import virsh

# {{{
SAMPLE_IP_LINK_LIST = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP
    link/ether 0c:c4:7a:13:89:52 brd ff:ff:ff:ff:ff:ff
3: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP
    link/ether 0c:c4:7a:13:89:53 brd ff:ff:ff:ff:ff:ff
4: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP
    link/ether fe:54:00:3b:84:70 brd ff:ff:ff:ff:ff:ff
5: br1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN
    link/ether 00:00:00:00:00:00 brd ff:ff:ff:ff:ff:ff
126: vnet12: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast
    link/ether fe:54:00:3b:84:70 brd ff:ff:ff:ff:ff:ff
1178: nr0: <NOARP> mtu 236 qdisc noop state DOWN mode DEFAULT group default
    link/generic 00:00:00:00:00:00:00 brd 00:00:00:00:00:00:00
1181: nr3: <NOARP> mtu 236 qdisc noop state DOWN mode DEFAULT group default
    link/generic 00:00:00:00:00:00:00 brd 00:00:00:00:00:00:00
1182: rose0: <NOARP> mtu 249 qdisc noop state DOWN mode DEFAULT group default
    link/rose 00:00:00:00:00 brd 00:00:00:00:00
1191: rose9: <NOARP> mtu 249 qdisc noop state DOWN mode DEFAULT group default
    link/rose 00:00:00:00:00 brd 00:00:00:00:00
433: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state
    link/ether 56:84:7a:fe:97:99 brd ff:ff:ff:ff:ff:ff
"""
# }}}

SAMPLE_CONFIG = {"ssh": {"user": "root", "host": "example.net"}}


class XMLElementTestCase(unittest.TestCase):

    def test_se(self):
        x = virsh.XMLElement(None, "root")
        x.se("se", attr="ok")
        self.assertEqual(b'<root><se attr="ok" /></root>', x.tostring())


class XMLTestCase(unittest.TestCase):

    def test_fd(self):
        cfg = {"memory": "123"}
        x = virsh.XML("test_name", cfg)
        with x.fd() as fd:
            data = fd.read()
        self.assertTrue(b"memballoon" in data)
        self.assertTrue(b"memory" in data)
