
import json
import subprocess

import base

import logging
LOG = logging.getLogger(__name__)


class Stream(base.Stream):

    def generate(self):
        conf = self.config["ssh"]
        cmd = "ssh -p %(port)d %(username)s@%(hostname)s gerrit stream-events" % \
                self.config["ssh"]
        pipe = subprocess.Popen(cmd.split(" "),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        with open(self.config.get("pidfile", "/var/log/rally-ci/gerrit-ssh.pid"), "w") as pidfile:
            pidfile.write(str(pipe.pid))
        for line in iter(pipe.stdout.readline, b''):
            if not line:
                break
            try:
                event = json.loads(line)
            except ValueError:
                LOG.warning("Invalid json: %s" % line)
            yield(event)


