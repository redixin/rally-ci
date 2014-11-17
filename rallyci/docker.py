
import random, string
import sys, subprocess
import sshutils

import logging
LOG = logging.getLogger(__name__)

class Driver(object):

    def __init__(self, config, job_name, dockerfilepath):
        self.name = job_name
        self.dockerfilepath = dockerfilepath
        self.config = config
        self.tag = "rallyci:" + dockerfilepath.replace('/', '_')
        self.number = 0
        self.current = self.tag
        self.names = []
        self.ssh = sshutils.SSH(config["ssh-user"],
                                config["ssh-host"],
                                port=config.get("ssh-port", 22))

    def _run(self, cmd, stdout, stdin=None):
        LOG.debug("Running cmd: %r" % cmd)
        return self.ssh.run(" ".join(cmd), stdout=stdout, stdin=stdin,
                            stderr=sshutils.STDOUT, raise_on_error=False)

    def build(self, stdout):
        cmd = ["docker", "build", "-t", self.tag, self.dockerfilepath]
        LOG.debug("Building image %r" % cmd)
        return self._run(cmd, stdout)

    def run(self, cmd, stdout, stdin=None):

        name = "".join(random.sample(string.letters, 12))
        self.names.append(name)
        command = ["docker", "run", "--name", name]
        if stdin:
            command += ["-i"]
        command += [self.current]
        command += cmd.split(" ")
        LOG.debug("Running command %r" % command)
        returncode = self._run(command, stdout, stdin=stdin)
        LOG.debug("Exit status: %d" % returncode)
        status, self.current, stderr = self.ssh.execute("docker commit %s" % name)
        self.current = self.current.strip()
        return returncode

    def cleanup(self):
        for name in self.names:
            subprocess.check_output(["docker", "rm", name])
        subprocess.check_output(["docker", "rmi", self.current])
