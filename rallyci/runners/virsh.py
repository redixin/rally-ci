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
import logging

from rallyci import base
from rallyci.common import virsh
from rallyci import utils

LOG = logging.getLogger(__name__)


class Class(base.ClassWithLocal, base.GenericRunnerMixin):
    """
    self.cfg is entry from runners section
      module: ...
      nodepool: ...
      vms:
        img1:
          build-scripts: ["s1", "s2"]
          dataset: /tank/ds
          source: img@s
    self.local is runner section from jobs section
      name: runner-name
      image: runner-image
      scripts: ["s1", "s2"]
    """

    @asyncio.coroutine
    def build(self):
        ssh = yield from self.config.nodepools[self.cfg["nodepool"]].get_ssh(self.job)
        self.vm = virsh.VM(ssh, self.local["image"], self.cfg)
        yield from self.vm.build()

    @asyncio.coroutine
    def boot(self):
        yield from self.vm.boot()

    @asyncio.coroutine
    def run_script(self, script):
        yield from self.vm.run_script(script)

    @asyncio.coroutine
    def cleanup(self):
        yield from self.vm.cleanup()
