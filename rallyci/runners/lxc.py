
import threading
import logging
import StringIO

import base
from rallyci import sshutils
from rallyci import utils

LOG = logging.getLogger(__name__)
LOCK = threading.Lock()
BUILD_LOCK = {}


class Runner(base.Runner):

    def setup(self, name, template, build_scripts, template_options="", env_networks=None):
        self.base_name = name
        self.name = utils.get_rnd_name()
        self.ssh = sshutils.SSH(**self.config["ssh"])
        self.template = template
        self.template_options = template_options
        self.build_scripts = build_scripts
        self.env_networks = env_networks

    def _get_env_networks(self):
        for env_net in self.env_networks or []:
            ifname, ip = env_net.split(":")
            for env in self.job.envs:
                for vm in getattr(env, "vms", []):
                    for i in vm.ifs:
                        if i.startswith(ifname):
                            yield i, ip

    def _setup_env_networks(self, conf):
        for ifname, ip in self._get_env_networks():
            conf.write("lxc.network.type = veth\n"
                       "lxc.network.link = %s\n"
                       "lxc.network.flags = up\n"
                       "lxc.network.ipv4 = %s\n" % (ifname, ip))

    def _setup_base_networks(self, conf):
        for net in self.config["networking"]:
            conf.write("lxc.network.type = veth\n"
                       "lxc.network.link = %s\n" % net["bridge"])

    def _build(self, stdout_cb):
        failed = False
        try:
            cmd = "lxc-create -B zfs -t %s -n %s -- %s"
            cmd = cmd % (self.template,
                         self.base_name,
                         self.template_options)
            self.ssh.run(cmd, **utils.get_stdouterr(stdout_cb))
            conf = StringIO.StringIO()
            self._setup_base_networks(conf)
            conf.seek(0)
            self.ssh.run("cat >> /var/lib/lxc/%s/config" % self.base_name, stdin=conf)
            self.ssh.run("lxc-start -d -n %s" % self.base_name)
            for s in self.build_scripts:
                s = self.global_config.scripts[s]
                cmd = "lxc-attach -n %s -- %s" % (self.base_name,
                                                  s["interpreter"])
                path = s.get("path")
                if path:
                    if path.startswith("~"):
                        path = os.path.expanduser(path)
                    stdin = open(path, "rb")
                else:
                    stdin = StringIO.StringIO(s["data"])
                self.ssh.run(cmd, stdin=stdin, **utils.get_stdouterr(stdout_cb))
        except Exception as e:
            LOG.warning("Failed to build container.")
            self.ssh.execute("lxc-destroy -f -n %s" % self.base_name)
            raise
        self.ssh.execute("lxc-stop -n %s" % self.base_name)

    def build(self, stdout_callback):
        with LOCK:
            if self.base_name not in BUILD_LOCK:
                BUILD_LOCK[self.base_name] = threading.Lock()
        LOG.debug("Available locks: %r" % BUILD_LOCK)
        LOG.debug("is_locked 1 %r" % BUILD_LOCK[self.base_name].locked())
        with BUILD_LOCK[self.base_name]:
            LOG.debug("is_locked 2 %r" % BUILD_LOCK[self.base_name].locked())
            LOG.debug("Checking base container")
            status, out, err = self.ssh.execute("lxc-info -n %s" % self.base_name)
            if status:
                LOG.debug("No container %s. Building new one." % self.base_name)
                self._build(stdout_callback)
        LOG.info("Creating container %s as clone of %s" % (self.name, self.base_name))
        self.ssh.run("lxc-clone -s %s %s" % (self.base_name, self.name))

    def boot(self):
        conf = StringIO.StringIO()
        self._setup_env_networks(conf)
        conf.seek(0)
        self.ssh.run("cat >> /var/lib/lxc/%s/config" % self.name, stdin=conf)
        self.ssh.run("lxc-start -d -n %s" % self.name)

    def run(self, cmd, stdout_cb, stdin, env):
        cmd = "lxc-attach -n %s -- %s" % (self.name, cmd)
        for k, v in env.items():
            cmd = "%s=%s " % (k, v) + cmd
        LOG.debug("Executing '%s' in container" % cmd)
        self.ssh.run(cmd, stdin=stdin, **utils.get_stdouterr(stdout_cb))

    def cleanup(self):
        LOG.info("Removing container %s" % self.name)
        self.ssh.execute("lxc-destroy -f -n %s" % self.name)
        # https://github.com/lxc/lxc/issues/401
        self.ssh.execute("zfs destroy tank/lxc/%s@%s" % (self.base_name, self.name))
        self.ssh.close()
        del(self.ssh)
