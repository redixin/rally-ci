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
import collections
import functools
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


class Service:
    def __init__(self, root, **config):
        self.root = root
        self.loop = root.loop
        self.config = config

        self.console_listeners = {}
        self.clients = []
        self._jobs = {}
        self._finished = collections.deque(maxlen=10)

    @asyncio.coroutine
    def index(self, request):
        LOG.debug("Index requested: %s" % request)
        text = pkgutil.get_data(__name__, "status.html").decode("utf-8")
        return web.Response(text=text, content_type="text/html")

    def _con_cb(self, job_id, data):
        for cl in self.console_listeners.get(job_id, []):
            cl.send_str(json.dumps(data))

    @asyncio.coroutine
    def console(self, request):
        job = self._jobs.get(request.match_info["job_id"])
        if not job:
            return web.HTTPNotFound()
        ws = web.WebSocketResponse()
        ws.start(request)
        if job.id not in self.console_listeners:
            self.console_listeners[job.id] = []
        self.console_listeners[job.id].append(ws)
        job.console_listeners.append(functools.partial(self._con_cb, job.id))
        try:
            yield from ws.receive()
        except CancelledError:
            pass
        except Exception:
            LOG.exception("Websocket error %s" % ws)
        wss = self.console_listeners.get(job.id)
        if wss and ws in wss:
            wss.remove(ws)
        if wss is not None:
            if not wss:
                self.console_listeners.pop(job.id)
        return ws

    @asyncio.coroutine
    def close_console_listeners(self, job):
        wss = self.console_listeners.pop(job.id)
        for ws in wss:
            ws.send_str(json.dumps({"status": job.status}))
        for ws in wss:
            yield from ws.close()

    @asyncio.coroutine
    def job(self, request):
        LOG.debug("Index requested: %s" % request)
        text = pkgutil.get_data(__name__, "status_job.html").decode("utf-8")
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
                                    "tasks": tasks + list(self._finished)}))
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

    def _task_started_cb(self, task):
        self._send_all({"type": "task-started", "task": task.to_dict()})

    def _job_status_cb(self, job):
        if job.finished_at is None:
            if job.id not in self._jobs:
                self._jobs[job.id] = job
        else:
            self._jobs.pop(job.id)
            if job.id in self.console_listeners:
                self.root.start_coro(self.close_console_listeners(job))
        self._send_all({"type": "job-status-update", "job": job.to_dict()})

    def _task_finished_cb(self, task):
        self._finished.append(task.to_dict())
        self._send_all({"type": "task-finished", "id": task.id})

    def _send_daemon_statistic(self):
        stat = self.root.get_daemon_statistics()
        LOG.debug("Senging stats to websocket %s" % stat)
        self._send_all(stat)


    @asyncio.coroutine
    def run(self):
        self.stats_sender = periodictask.PeriodicTask(
            self.config.get("stats-interval", 60),
            self._send_daemon_statistic,
            loop=self.loop)
        self.root.task_start_handlers.append(self._task_started_cb)
        self.root.task_end_handlers.append(self._task_finished_cb)
        self.root.job_update_handlers.append(self._job_status_cb)
        self.app = web.Application(loop=self.loop)
        self.app.router.add_route("GET", "/", self.index)
        self.app.router.add_route("GET", "/ws/", self.ws)
        self.app.router.add_route("GET", "/jobs/{job_id}/", self.job)
        self.app.router.add_route("GET", "/console/{job_id}/", self.console)
        addr, port = self.config.get("listen", ("localhost", 8080))
        self.handler = self.app.make_handler()
        self.srv = yield from self.loop.create_server(self.handler, addr, port)
        LOG.info("HTTP server started at %s:%s" % (addr, port))
        try:
            yield from asyncio.Event(loop=self.loop).wait()
        except asyncio.CancelledError:
            pass

    @asyncio.coroutine
    def cleanup(self):
        LOG.debug("Cleanup http status")
        self.stats_sender.stop()
        self.root.task_start_handlers.remove(self._task_started_cb)
        self.root.task_end_handlers.remove(self._task_finished_cb)
        self.root.job_update_handlers.remove(self._job_status_cb)
        for c in self.clients:
            yield from c.close()
        yield from self.handler.finish_connections(8)
        self.srv.close()
        yield from self.srv.wait_closed()
        yield from self.app.finish()
        LOG.debug("Finished cleanup http status")
