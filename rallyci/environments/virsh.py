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

from rallyci.environments import base
from rallyci.common import virsh

import re
import logging
import threading


LOG = logging.getLogger(__name__)
PREFIX = "rci_"
LOCK_GET_SEM = threading.Lock()
LOCK = threading.Lock()
SEMS = {}
NETWORKS = set()
IFACE_RE = re.compile("\d+: ([a-z]+)([0-9]+): .*")


class Environment(base.Environment):

    def __init__(self, *args, **kwargs):
        super(Environment, self).__init__(*args, **kwargs)
        self.vms = []
        self.name = self.config["name"]
        self.ifs = {}

    def build(self):
        with LOCK_GET_SEM:
            if self.name not in SEMS:
                SEMS[self.name] = threading.Semaphore(
                        self.config["max_threads"])
        LOG.debug(SEMS)
        SEMS[self.name].acquire()
        LOG.debug("acquired %r" % SEMS[self.name])
        try:
            for vm_conf in self.config["create-vms"]:
                vm = virsh.VM(self.global_config, vm_conf, self)
                vm.build()
                ip_env_var = vm_conf.get("ip_env_var")
                if ip_env_var:
                    self.env[ip_env_var] = vm.get_ip()
                self.vms.append(vm)
        except:
            SEMS[self.name].release()
            raise

    def cleanup(self):
        SEMS[self.name].release()
        while self.vms:
            vm = self.vms.pop()
            vm.cleanup()
