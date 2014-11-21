
import random
import string
import sshutils
import os.path

import logging
LOG = logging.getLogger(__name__)


class Driver(object):

    def __init__(self, host, user, port=22, **kwargs):
        self.config = kwargs
        self.number = 0
        self.names = []
        self.ssh = sshutils.SSH(user, host, port)

    def setup(self, dockerfilepath):
        tag = dockerfilepath.replace("/", "_")
        tag = tag.replace("~", "_")
        self.tag = "rallyci:" + tag
        self.dockerfilepath = os.path.expanduser(dockerfilepath)
        self.current = self.tag

    def _run(self, cmd, stdout, stdin=None):
        LOG.debug("Running cmd: %r" % cmd)
        return self.ssh.run(" ".join(cmd), stdout=stdout, stdin=stdin,
                            stderr=sshutils.STDOUT, raise_on_error=False)

    def build(self, stdout):
        cmd = ["docker", "build", "-t", self.tag, self.dockerfilepath]
        LOG.debug("Building image %r" % cmd)
        return self._run(cmd, stdout)

    def run(self, cmd, stdout, stdin=None, env=None):

        name = "".join(random.sample(string.letters, 12))
        self.names.append(name)
        command = ["docker", "run", "--name", name]
        if stdin:
            command += ["-i"]
        if env:
            for k, v in env.items():
                command += ["-e", "\"%s=%s\"" % (k, v)]
        command += [self.current]
        command += cmd.split(" ")
        LOG.debug("Running command %r" % command)
        returncode = self._run(command, stdout, stdin=stdin)
        LOG.debug("Exit status: %d" % returncode)
        status, self.current, err = self.ssh.execute("docker commit %s" % name)
        self.current = self.current.strip()
        return returncode

    def cleanup(self):
        for name in self.names:
            self.ssh.run("docker rm %s" % name)
        self.ssh.run("docker rmi %s" % self.current)
