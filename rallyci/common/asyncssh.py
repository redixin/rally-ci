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


class AsyncSSH:
    def __init__(self, job, username, hostname, port=22):
        self.job = job
        self.username = username
        self.hostname = hostname
        self.port = str(port)

    def run_cmd(self, command):
        cmd = []
        if self.hostname != "localhost":
            cmd = ["ssh", "%s@%s" % (self.username, self.hostname), "-p", self.port]
        cmd += command.split(" ")
        process = yield from asyncio.create_subprocess_exec(*cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        while not process.stdout.at_eof():
            line = yield from process.stdout.readline()
            self.job.logger(line)
        return process.returncode
