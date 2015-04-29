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
import json
import subprocess
import logging

from rallyci import base

LOG = logging.getLogger(__name__)


class Class(base.Class):

    @asyncio.coroutine
    def run(self):
        root = self.config.root
        cfg = self.cfg
        port = str(cfg["port"])
        cmd = ["ssh", "-q", "-o", "StrictHostKeyChecking=no", "-p", port,
                "%s@%s" % (cfg["username"], cfg["hostname"]), "gerrit", "stream-events"]

        process = yield from asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        while not process.stdout.at_eof():
            line = yield from process.stdout.readline()
            try:
                event = json.loads(line.decode())
            except Exception:
                LOG.error("Unable to decode string: %s" % line)
            else:
                root.handle(event)
