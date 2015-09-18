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
import pkgutil
import logging
import os.path

import json
import rallyci.common.periodictask as ptask
import aiohttp
import json
from aiohttp import web

from  rallyci.common import periodictask

LOG = logging.getLogger(__name__)


class Class:
    def __init__(self, **config):
        self.config = config
        self.clients = []

    @asyncio.coroutine
    def index(self, request):
        LOG.debug("Index requested: %s" % request)
        text = pkgutil.get_data(__name__, "index.html").decode("utf-8")
        return web.Response(text=text, content_type="text/html")

    @asyncio.coroutine
    def ws(self, request):
        LOG.debug("Websocket connected %s" % request)
        ws = web.WebSocketResponse()
        ws.start(request)
        self.clients.append(ws)

        if not self.stats_sender.active:
            self.stats_sender.start()

        try:
            tasks = [t.to_dict() for t in self.root.tasks.values()]
            ws.send_str(json.dumps({"type": "all-tasks",
                                    "tasks": tasks}))
            while True:
                msg = yield from ws.receive()
                LOG.debug("Websocket received: %s" % str(msg))
                if msg.tp == web.MsgType.close:
                    break
        except aiohttp.errors.ClientDisconnectedError:
            LOG.info("WS %s disconnected" % ws)

        self.clients.remove(ws)
        if not self.clients and self.stats_sender.active:
            self.stats_sender.stop()

        return ws

    def _send_all(self, data):
        for c in self.clients:
            c.send_str(json.dumps(data))

    def _task_started_cb(self, event):
        self._send_all({"type": "task-started", "task": event.to_dict()})

    def _job_status_cb(self, job):
        self._send_all({"type": "job-status-update", "job": job.to_dict()})

    def _task_finished_cb(self, event):
        self._send_all({"type": "task-finished", "id": event.id})

    def _send_daemon_statistic(self):
        stat = self.root.get_daemon_statistics()
        LOG.debug(stat)
        self._send_all(stat)

    @asyncio.coroutine
    def run(self):
        self.app = web.Application(loop=self.loop)
        self.app.router.add_route("GET", "/", self.index)
        self.app.router.add_route("GET", "/ws/", self.ws)
        addr, port = self.config.get("listen", ("localhost", 8080))
        self.handler = self.app.make_handler()
        self.srv = yield from self.loop.create_server(self.handler, addr, port)
        LOG.debug("HTTP server started at %s:%s" % (addr, port))

    def start(self, root):
        self.loop = root.loop
        self.root = root
        self.stats_sender = periodictask.PeriodicTask(
            self.config.get("stats-interval", 60),
            self._send_daemon_statistic,
            loop=self.loop)
        asyncio.async(self.run(), loop=self.loop)
        root.task_start_handlers.append(self._task_started_cb)
        root.task_end_handlers.append(self._task_finished_cb)
        root.job_update_handlers.append(self._job_status_cb)

    @asyncio.coroutine
    def _stop(self, timeout=1.0):
        for c in self.clients:
            yield from c.close()
        yield from self.handler.finish_connections(timeout)
        self.srv.close()
        yield from self.srv.wait_closed()
        yield from self.app.finish()

    def stop(self):
        self.root.task_start_handlers.remove(self._task_started_cb)
        self.root.task_end_handlers.remove(self._task_finished_cb)
        self.root.job_update_handlers.remove(self._job_status_cb)
        return asyncio.async(self._stop(), loop=self.loop)
