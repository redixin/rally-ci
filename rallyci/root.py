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

        self.nodepools = {}
        for name, cfg in self.data["nodepools"].items():
            self.nodepools[name] = self.get_class(cfg)(self.root, cfg)


    def _get_module(self, name):
        """Get module by name.

        Import module if it is not imported.
        """
        module = self._modules.get(name)
        if not module:
            module = importlib.import_module(name)
            self._modules[name] = module
        return module

    def get_class(self, cfg):
        return self._get_module(cfg["module"]).Class

    def init_obj_with_local(self, section, local):
        cfg = self.data[section][local["name"]]
        return self.get_class(cfg)(self, cfg, local)

    def init_obj(self, cfg):
        return self._get_module(cfg["module"]).Class(self, cfg)


class WebSocket:
    def __init__(self, root):
        self.root_path = "/ws/"
        self.root = root
        self.root_listeners = []

    def send(self, listeners, data):
        for client in listeners:
            asyncio.async(client.send(json.dumps(data)), loop=self.root.loop)

    def cr_started(self, cr):
        data = {"type": "task-started", "task": cr.to_dict()}
        self.send(self.root_listeners, data)

    def cr_finished(self, cr):
        data = {"type": "task-finished", "id": cr.id}
        self.send(self.root_listeners, data)

    def job_status(self, job):
        data = {"type": "job-status-update", "job": job.to_dict()}
        self.send(self.root_listeners, data)

    def send_all_tasks(self, client):
        data = [c.to_dict() for c in self.root.crs.values()]
        asyncio.async(client.send(
            json.dumps({"type": "all-tasks", "tasks": data})), loop=self.root.loop)

    def new_line(self, job, line):
        pass

    def on_data(self, data):
        LOG.debug("Received data: %r" % data)

    def accept(self, client, path):
        LOG.debug("New WS connection %r, %s" % (client, path))
        self.send_all_tasks(client)
        if path == self.root_path:
            self.root_listeners.append(client)

        while True:
            data = yield from client.recv()
            if data is None:
                break
            self.on_data(data)

        if path == self.root_path:
            LOG.debug("Removed root listener %r" % client)
            self.root_listeners.remove(client)

    def start(self, host, port):
        import websockets
        self.future = websockets.serve(self.accept, host, port)
        return asyncio.async(self.future, loop=self.root.loop)


class Root:
    def __init__(self, loop):
        self.cleanup_tasks = []
        self.crs = {}
        self.loop = loop
        self.ws = WebSocket(self)
        self.ws_future = self.ws.start("0.0.0.0", 8000)

    def load_config(self, filename):
        self.config = Config(self, filename)
        self.init_stream(self.config.stream)

    def cr_done(self, future):
        LOG.debug("Completed cr: %r" % future)
        self.ws.cr_finished(self.crs[future])
        del(self.crs[future])

    def handle(self, event):
        LOG.debug("Creating cr instance.")
        try:
            cr_instance = cr.CR(self.config, event)
        except Exception as e:
            LOG.exception("Failed to create cr instance.")
            return
        LOG.debug("Instance created %r" % cr_instance)
        if cr_instance.jobs:
            future = asyncio.async(cr_instance.run())
            self.crs[future] = cr_instance
            future.add_done_callback(self.cr_done)
            self.ws.cr_started(cr_instance)
        else:
            LOG.debug("No jobs. Skipping event.")
            del(cr_instance)

    def handle_job_status(self, job):
        self.ws.job_status(job)

    def handle_end_of_stream(self, future):
        LOG.info("Stream exited. Restarting in 4 seconds.")
        self.loop.call_later(4, self.init_stream, self.stream)

    def init_stream(self, stream):
        LOG.info("Starting stream.")
        self.stream = stream
        self.stream_future = asyncio.async(self.stream.run(), loop=self.loop)
        self.stream_future.add_done_callback(self.handle_end_of_stream)

    def stop(self):
        self.stream_future.remove_done_callback(self.handle_end_of_stream)
        self.stream_future.cancel()
        self.ws_future.cancel()
        tasks = list(self.crs.keys())
        LOG.info("Interrupted. Waiting for tasks %r." % tasks)
        yield from asyncio.gather(*tasks, return_exceptions=True)
        LOG.info("All tasks finished. Waiting for cleanup tasks %r." % self.cleanup_tasks)
        yield from asyncio.gather(*self.cleanup_tasks, return_exceptions=True)
        LOG.info("All cleanup tasks finished. Stopping loop.")
        self.loop.stop()
