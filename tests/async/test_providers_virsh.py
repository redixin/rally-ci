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


from rallyci.providers import virsh

import base


OUT_ZFS_LIST = """NAME                                  USED  AVAIL  REFER  MOUNTPOINT
ci/lxc/test-ubuntu-base@pip-test         0      -   321M  -
ci/rally/mos_7_0_3@1                     0      -  3.07G  -
ci/rally/u1404@1                         0      -   247M  -
ci/rally/u1404_docker@1                  0      -  2.50G  -
ci/rally/u1404_dsvm@1                    0      -  4.16G  -"""

OUT_UPTIME = """16:51:56 up 83 days, 22:18,  5 users,  load average: 70.23, 124.89, 120.73
total       used       free     shared    buffers     cached
Mem:     131870688  123538232    8332456       2420     158360   73515476
-/+ buffers/cache:   49864396   82006292
Swap:       524284     524284          0"""


class HostTestCase(base.AsyncTest):

    @base.mock.patch("rallyci.providers.virsh.SSH")
    def test_update_stats_(self, mock_ssh):
        mock_ssh.return_value = base.FakeSSH([(0, OUT_UPTIME, "")])
        mock_provider = base.mock.Mock()
        mock_provider.config = {"storage": {"path": "p", "backend": "btrfs"}}
        h = virsh.Host({}, mock_provider, base.mock.Mock())
        self.loop.run_until_complete(h.update_stats())
        self.assertEqual(70.23, h.la)
        self.assertEqual(81847932, h.free)


class ZFSTestCase(base.AsyncTest):

    def test_list_images(self):
        zfs = virsh.ZFS(base.FakeSSH([(0, OUT_ZFS_LIST, "")]),
                        "/ci/rally", "ci/rally")
        images = self.loop.run_until_complete(zfs.list_images())
        expected = {'u1404_docker', 'u1404', 'mos_7_0_3', 'u1404_dsvm'}
        self.assertEqual(expected, images)
