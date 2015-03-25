from rallyci.streams import base

import json
import subprocess
import logging


LOG = logging.getLogger(__name__)
PIDFILE = "/var/log/rally-ci/gerrit-ssh.pid"


class Stream(base.Stream):

    def generate(self):
        cmd = "ssh -p %(port)d %(username)s@%(hostname)s gerrit stream-events" % \
              self.config["ssh"]
        pipe = subprocess.Popen(cmd.split(" "),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        try:
            with open(self.config.get("pidfile", PIDFILE), "w") as pidfile:
                pidfile.write(str(pipe.pid))
            for line in iter(pipe.stdout.readline, b''):
                if not line:
                    break
                try:
                    event = json.loads(line)
                except ValueError:
                    LOG.warning("Invalid json: %s" % line)
                    next
                yield(event)
        finally:
            pipe.terminate()
