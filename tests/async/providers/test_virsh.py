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


import asyncio
import unittest
from unittest.mock import Mock

from rallyci.providers import virsh


class HostTestCase(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()

    @unittest.mock.patch("rallyci.providers.virsh.asyncssh")
    def test_update_stats(self, mock_ssh):

        @asyncio.coroutine
        def ssh(cmd, *args, **kwargs):
            return """16:51:56 up 83 days, 22:18,  5 users,  load average: 70.23, 124.89, 120.73
total       used       free     shared    buffers     cached
Mem:     131870688  123538232    8332456       2420     158360   73515476
-/+ buffers/cache:   49864396   82006292
Swap:       524284     524284          0"""

        fake_ssh = Mock()
        fake_ssh.run = Mock(wraps=ssh)
        mock_ssh.AsyncSSH.return_value = fake_ssh

        h = virsh.Host({},
                       {"storage": {"path": "path", "backend": "btrfs"}},
                       None, None)
        self.loop.run_until_complete(h.update_stats())
        self.assertEqual(70.23, h.la)
        self.assertEqual(81847932, h.free)


class ProviderTestCase(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()

    def test_get_vms(self):
        cfgs = [
                {'name': 'u1404_dsvm',
                 'scp': [['/home/rally', 'test-logs']],
                 'scripts': ['git_checkout', 'show_git_log']}
        ]
        p = virsh.Provider(None, {"name": "name"})
