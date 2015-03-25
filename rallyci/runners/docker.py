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

import threading
import os.path

from rallyci import sshutils
from rallyci import utils
from rallyci.runners import base

import logging
LOG = logging.getLogger(__name__)


BUILD_LOCK = {}
LOCK = threading.Lock()


class Runner(base.Runner):

    def setup(self, dockerfile):
        self.ssh = sshutils.SSH(**self.config["ssh"])
        self.names = []
        self.number = 0
        tag = dockerfile.replace("/", "_")
        tag = tag.replace("~", "_")
        self.tag = "rallyci:" + tag
        self.dockerfile = os.path.expanduser(dockerfile)
        self.current = self.tag

    def _run(self, cmd, stdout_callback, stdin=None):
        LOG.debug("Running cmd: %r" % cmd)

        class Stdout(object):
            def write(self, line):
                stdout_callback((1, line))

        class Stderr(object):
            def write(self, line):
                stdout_callback((2, line))

        return self.ssh.run(" ".join(cmd), stdout=Stdout(), stderr=Stderr(),
                            stdin=stdin, raise_on_error=False)

    def _build(self, stdout_callback):
        LOG.debug("Uploading dockerfile")
        tmpdir = utils.get_rnd_name()
        tmpdir = os.path.join("/tmp", tmpdir)
        self.ssh.run("mkdir %s" % tmpdir)
        self.ssh.run("cat > %s/Dockerfile" % tmpdir,
                     stdin=open(self.dockerfile, "rb"))
        LOG.debug("Building image %r" % self.tag)
        return self._run(["docker", "build", "--no-cache",
                          "-t", self.tag, tmpdir],
                         stdout_callback)

    def build(self, stdout_callback):
        with LOCK:
            lock = BUILD_LOCK.get(self.tag)
            if not lock:
                lock = threading.Lock()
                BUILD_LOCK[self.tag] = lock
        with lock:
            LOG.debug("Checking docker image")
            status, out, err = self.ssh.execute("docker history %s" % self.tag)
            if status:
                return self._build(stdout_callback)

    def run(self, cmd, stdout_callback, stdin=None, env=None):
        name = utils.get_rnd_name()
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
        returncode = self._run(command, stdout_callback, stdin=stdin)
        LOG.debug("Exit status: %d" % returncode)
        status, self.current, err = self.ssh.execute("docker commit %s" % name)
        self.current = self.current.strip()
        return returncode

    def cleanup(self):
        for name in self.names:
            self.ssh.run("docker rm %s" % name)
        self.ssh.run("docker rmi %s" % self.current)
        self.ssh.close()
        del(self.ssh)
