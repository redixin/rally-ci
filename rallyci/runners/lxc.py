
import threading
import logging

import base

LOG = logging.getLogger(__name__)
LOCK = threading.Lock()
BUILD_LOCK = {}


class Stdout(object):

    def __init__(self, cb, num=1):
        self.cb = cb
        self.num = num

    def write(self, line):
        self.cb((self.num, line))


def get_rnd_name(length=12):
    return "".join(random.sample(string.letters, length))


class Runner(base.runner):

    def setup(self, name, template, build_script, template_options="", env_networks=None):
        self.name = name
        self.ssh = sshutils.SSH(**self.config["ssh"])
        self.template = template
        self.template_options = template_options
        self.build_scripts = build_scripts
        self.env_networks = env_networks

    def _get_networks(self):
        nets = []
        for env_net in self.env_networks or []:
            for env in self.job.envs:
                for vm in getattr(env, "vms", []):
                    for i in vm.ifs:
                        if i.startswith(env_net[0]):
                            nets.append((i, env_net))



    def _build(self, stdout_cb):
        cmd = "lxc create -B btrfs -t %s -n %s -- %s"
        cmd = cmd % (self.template,
                     self.name,
                     self.template_options))
        self.ssh.run(cmd, stdout=Stdout(stdout_cb),
                     stderr=Stdout(stdout_cb, 2))

    def build(self, stdout_callback):
        pass
