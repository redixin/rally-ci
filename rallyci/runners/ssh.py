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

LOG = logging.getLogger(__name__)


class Class:

    def __init__(self, cfg, job, local_cfg):
        """Represent SSH runner.

        :param job: job instance
        :param cfg: config.runner
        :param local_cfg: config.job.runner
        """
        self.job = job
        self.local_cfg = local_cfg
        self.cfg = cfg
        self.vms = []
        self.log_path = os.path.join(cfg["logs"], job.log_path)
        os.makedirs(self.log_path, exist_ok=True)
        self.logfile = open(os.path.join(self.log_path, "console.txt"), "wb")

    def cb(self, line):
        self.logfile.write(line)
        self.logfile.flush()

    @asyncio.coroutine
    def run(self):
        self.job.set_status("started")
        self.prov = self.job.root.providers[self.cfg["provider"]]
        scripts = [vm.get("scripts", []) for vm in self.local_cfg["vms"]]
        self.vms = yield from self.prov.get_vms(self.local_cfg["vms"])
        for vm, scripts in zip(self.vms, scripts):
            for script in scripts:
                LOG.debug("Running test script %s on vm %s" % (script, vm))
                s = self.job.root.config.data["script"][script]
                self.job.set_status(script)
                yield from vm.run_script(s, cb=self.cb, env=self.job.env)
        self.job.set_status("finished")

    @asyncio.coroutine
    def cleanup(self):
        self.logfile.close()
        for vm in self.vms:
            for src, dst in vm.local_cfg.get("scp", []):
                dst = os.path.join(self.log_path, dst)
                ssh = yield from vm.get_ssh()
                yield from ssh.scp_get(src, dst)
        yield from self.prov.cleanup(self.vms)
