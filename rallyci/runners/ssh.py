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

LOG = logging.getLogger(__name__)


class Class:

    def __init__(self, config):
        self.config = config
        self.vms = []

    def cb(self, line):
        print(line)

    @asyncio.coroutine
    def run(self, job):
        self.prov = job.root.providers[self.config["provider"]]
        vms = [vm["name"] for vm in self.config["vms"]]
        scripts = [vm["scripts"] for vm in self.config.get("vms", [])]
        self.vms = yield from self.prov.get_vms(vms)
        LOG.debug(self.vms)
        for vm, scripts in zip(self.vms, scripts):
            for script in scripts:
                LOG.debug("Running test script %s on vm %s" % (script, vm))
                s = job.root.config.data["script"][script]
                yield from vm.run_script(s, cb=self.cb)

    @asyncio.coroutine
    def cleanup(self):
        yield from self.prov.cleanup(self.vms)
