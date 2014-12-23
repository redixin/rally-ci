import base
from rallyci.common import virsh
from rallyci import sshutils
from rallyci import utils
import logging


LOG = logging.getLogger(__name__)


class Runner(base.Runner):

    def setup(self, user):
        self.user = user

    def build(self, stdout_cb):
        self.vm = virsh.VM(self.global_config, self.config)
        self.vm.build()

    def boot(self):
        sshconf = {"user": self.user}
        sshconf["host"] = self.ip
        LOG.debug("Connecting to %r" % sshconf)
        self.ssh = sshutils.SSH(**sshconf)
        self.ssh.run("uname")

    @property
    def ip(self):
        if not hasattr(self, "_ip"):
            self._ip = self.vm.get_ip()
        return self._ip

    def run(self, cmd, stdout_cb, stdin, env):
        for k, v in env.items():
            cmd = "%s=%s " % (k, v) + cmd
        self.ssh.run(cmd, stdin=stdin, **utils.get_stdouterr(stdout_cb))

    def cleanup(self):
        self.vm.cleanup()
