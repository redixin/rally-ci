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
from rallyci.common.ssh import Client


class Class:
    data = ""

    def __init__(self, root, **kwargs):
        self.root = root
        self.loop = root.loop

    def handle_stdout(self, data):
        for line in data.split("\n"):
            if line == "":
                try:
                    self.handle_event(self.data)
                except:
                    LOG.exception("Error handling data %s" % self.data)
                finally:
                    self.data = ""
            else:
                self.data += line

    @asyncio.coroutine
    def run(self):
        reconnect_delay = self.cfg.get("reconnect_delay", 5)
        if "port" not in self.cfg["ssh"]:
            self.cfg["ssh"]["port"] = 29418
        ssh = Client(self.loop, **self.cfg["ssh"])
        while True:
            status = yield from ssh.run("gerrit stream-events")
            LOG.info("Gerrit stream was closed with status %s" % status)
            LOG.info("Reconnecting in %s seconds" % reconnect_delay
            yield from asyncio.sleep(reconnect_delay)

    @asyncio.coroutine
    def cleanup(self):
        yield from asyncio.sleep(0)
