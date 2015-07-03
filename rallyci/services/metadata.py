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
import logging
import os.path
import json

import aiohttp
from aiohttp import web

import pkgutil

LOG = logging.getLogger(__name__)


class Class:

    def __init__(self, **config):
        self.config = config
        self.clients = []

    @asyncio.coroutine
    def index(self, request):
        LOG.debug("Request: %s" % request)
        return web.Response(text="sup", content_type="text/html")

    @asyncio.coroutine
    def run(self):
        self.app = web.Application(loop=self.loop)
        self.app.router.add_route("GET", "/", self.index)
        addr, port = self.config.get("listen", ("localhost", 8080))
        self.handler = self.app.make_handler()
        self.srv = yield from self.loop.create_server(self.handler, addr, port)
        LOG.debug("Metadata server started at %s:%s" % (addr, port))

    def start(self, root):
        self.loop = root.loop
        self.root = root
        asyncio.async(self.run(), loop=self.loop)

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
