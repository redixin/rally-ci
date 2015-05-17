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
import os
import logging

from rallyci import base
from rallyci.common import virsh
from rallyci import utils

LOG = logging.getLogger(__name__)


class Class(base.ClassWithLocal):
    """
    self.cfg is entry from runners section
      module: ...
      nodepool: ...
      vms:
        vm1:
          memory: 2048
          build-scripts: ["s1", "s2"]
          dataset: /tank/ds
          source: img@s
          net:
            - static-bridge: "br5"
            - dynamic-bridge: "dyn_br%d"

    self.local is runner section from jobs section:

      name: runner-name
      vms:
        - vm: vm-1-name
          scripts: ["s1", "s2"]
        - vm: vm-2-name
          ip_env_var: RCI_VM2_IP

    """

    @asyncio.coroutine
    def build(self):
        self.vms = []
        for vm_conf in self.local["vms"]:
            vm_name = vm_conf["vm"]
            cfg = self.cfg["vms"][vm_name]
            vm = virsh.VM(self.ssh, vm_name, cfg, vm_conf, self.job, self.config)
            self.job.set_status("building %s" % vm_name)
            yield from vm.build()
            self.vms.append(vm)

    @asyncio.coroutine
    def boot(self):
        for vm in self.vms:
            self.job.set_status("booting %s" % vm.name)
            yield from vm.boot()

    @asyncio.coroutine
    def _run_vm(self, vm):
        status = 0
        for s in vm.local.get("scripts", []):
            script = self.config.data["scripts"][s]
            self.job.set_status("%s: running %s" % (vm.name, s))
            status = yield from vm.run_script(script, raise_on_error=False)
            if status:
                break
        for src, dst in vm.local.get("scp", []):
            dst = os.path.join(self.job.full_log_path, dst)
            utils.makedirs(dst)
            yield from vm.get_ssh().scp_get(src, dst)
        return status

    @asyncio.coroutine
    def run(self):
        self.job.set_status("queued")
        self.ssh = yield from self.config.nodepools[self.cfg["nodepool"]].get_ssh(self.job)
        self.job.set_status("building")
        yield from self.build()
        self.job.set_status("booting")
        yield from self.boot()
        for vm in self.vms:
            status = yield from self._run_vm(vm)
            if status:
                self.job.set_status("failed")
                return status
        self.job.set_status("success")

    @asyncio.coroutine
    def cleanup(self):
        for vm in self.vms:
            yield from vm.cleanup()
