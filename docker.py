
import random, string
import sys, subprocess

from log import logging
LOG = logging.getLogger(__name__)

class Driver(object):

    def __init__(self, name, dockerfilepath):
        self.name = name
        self.dockerfilepath = dockerfilepath
        self.tag = "rallyci:" + dockerfilepath
        self.number = 0
        self.current = self.tag
        self.names = []

    def _run(self, cmd, stdout, stdin=None):
        pipe = subprocess.Popen(cmd, stdin=stdin,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)

        for line in iter(pipe.stdout.readline, b''):
            stdout.write(line)
        return pipe.returncode

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
        self.current = subprocess.check_output(
                ["docker", "commit", name]).strip()
        return returncode

    def cleanup(self):
        for name in self.names:
            subprocess.check_output(["docker", "rm", name])
        subprocess.check_output(["docker", "rmi", self.current])
