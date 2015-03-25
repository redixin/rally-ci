
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
