#!/usr/bin/env python
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import asyncio
import importlib
import logging
import yaml
import json

from rallyci import cr

LOG = logging.getLogger(__name__)


class Config:
    def __init__(self, root, filename):
        self._modules = {}
        self.root = root
        self.data = yaml.safe_load(open(filename, "rb"))
        self.stream = self.init_obj(self.data["stream"])
        sections = list(self.data.keys())
        sections.remove("stream")

    def _get_module(self, name):
        """Get module by name.

        Import module if it is not imported.
        """
        module = self._modules.get(name)
        if not module:
            module = importlib.import_module(name)
            self._modules[name] = module
        return module

    def init_obj_with_local(self, section, local):
        cfg = self.data[section][local["name"]]
        return self._get_module(cfg["module"]).Class(self, cfg, local)

    def init_obj(self, cfg):
        return self._get_module(cfg["module"]).Class(self, cfg)


class WebSocket:
    def __init__(self, root):
        self.root = root
        self.root_listeners = []

    def send(self, listeners, data):
        for client in listeners:
            asyncio.async(client.send(json.dumps(data)), loop=self.root.loop)

    def cr_started(self, cr):
        jobs = [(id(job), job.name) for job in cr.jobs]
        data = {"task-started": str(cr), "jobs": jobs}
        self.send(self.root_listeners, data)

    def cr_finished(self, cr):
        data = {"task-finished": str(cr)}
        self.send(self.root_listeners, data)

    def send_all_tasks(self, client):
        data = [c.to_dict() for c in self.root.crs.values()]
        asyncio.async(client.send(json.dumps(data)), loop=self.root.loop)

    def new_line(self, job, line):
        pass

    def accept(self, client, path):
        LOG.debug("New WS connection %r, %s" % (client, path))
        if path == "/":
            self.root_listeners.append(client)
            self.send_all_tasks(client)
        data = yield from client.recv()
        LOG.debug("Received data: %r" % data)
        if path == "/":
            LOG.debug("Removed root listener %r" % client)
            self.root_listeners.remove(client)

    def start(self, host, port):
        import websockets
        self.future = websockets.serve(self.accept, host, port)
        asyncio.async(self.future, loop=self.root.loop)


class Root:
    def __init__(self, loop):
        self.crs = {}
        self.loop = loop
        self.ws = WebSocket(self)
        self.ws.start("0.0.0.0", 8000)

    def load_config(self, filename):
        self.config = Config(self, filename)
        self.init_stream(self.config.stream)

    def cr_done(self, future):
        LOG.debug("Completed cr: %r" % future)
        self.ws.cr_finished(self.crs[future])
        del(self.crs[future])

    def handle(self, event):
        cr_instance = cr.CR(self.config, event)
        if cr_instance.jobs:
            future = asyncio.async(cr_instance.run())
            self.crs[future] = cr_instance
            future.add_done_callback(self.cr_done)
            self.ws.cr_started(cr_instance)

    def init_stream(self, stream):
        self.stream = stream
        self.stream_status = asyncio.Future()
        asyncio.async(self.stream.run(), loop=self.loop)
