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

from aiohttp import web

LOG = logging.getLogger(__name__)


class Class:

    def __init__(self, **config):
        self.config = config

    @asyncio.coroutine
    def index(self, request):
        LOG.debug("Index requested: %s" % request)
        path = os.path.join(os.path.realpath(os.path.dirname(__file__)),
                            "../../html/")
        with open(path + "index.html", "r") as f:
            text = f.read()
        return web.Response(text=text, content_type="text/html")

    @asyncio.coroutine
    def run(self, loop):
        self.loop = loop
        self.app = web.Application(loop=loop)
        self.app.router.add_route("GET", "/", self.index)
        addr, port = self.config.get("listen", ("localhost", 8080))
        self.handler = self.app.make_handler()
        self.srv = yield from loop.create_server(self.handler, addr, port)
        LOG.debug("HTTP server started at %s:%s" % (addr, port))

    def stop(self, timeout=1.0):
        self.loop.run_until_complete(self.handler.finish_connections(timeout))
        self.srv.close()
        self.loop.run_until_complete(self.srv.wait_closed())
        self.loop.run_until_complete(self.app.finish())
