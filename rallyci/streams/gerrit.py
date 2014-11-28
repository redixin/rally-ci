
import json
import subprocess

import base

class Stream(base.Stream):

    def generate(self):
        conf = self.config["ssh"]
        cmd = "ssh -p %(port)d %(username)s@%(hostname)s gerrit stream-events" % \
                self.config["ssh"]
        pipe = subprocess.Popen(cmd.split(" "),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        for line in iter(pipe.stdout.readline, b''):
            event = json.loads(line)
            yield(event)


