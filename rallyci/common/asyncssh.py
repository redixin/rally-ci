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

import asyncio
import subprocess
import tempfile
import logging


LOG = logging.getLogger(__name__)

class AsyncSSH:
    def __init__(self, username=None, hostname=None, port=22):
        self.username = username
        self.hostname = hostname
        self.port = str(port)

    def run(self, command, stdin=None, cb=None, return_output=False, strip_output=True):
        output = b""
        if isinstance(stdin, str):
            f = tempfile.TemporaryFile()
            f.write(stdin.encode())
            f.flush()
            f.seek(0)
            stdin = f
        cmd = []
        if self.hostname != "localhost":
            cmd = ["ssh", "%s@%s" % (self.username, self.hostname), "-p", self.port]
        cmd += command.split(" ")
        process = yield from asyncio.create_subprocess_exec(*cmd,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        LOG.debug("Running '%s'" % cmd)
        while not process.stdout.at_eof():
            line = yield from process.stdout.readline()
            if cb is not None:
                cb(line)
            if return_output:
                output += line
        if return_output:
            output = output.decode()
            if strip_output:
                return output.strip()
            return output
        return process.returncode
