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

from aiohttp import web
import logging


class HTTP:

    def __init__(self, loop, listen):
        self.loop = loop
        self.listen = listen
        self.app = web.Application(loop=self.loop)

    def add_route(self, *args, **kwargs):
        self.app.router.add_route(*args, **kwargs)

    async def start(self):
        self.handler = self.app.make_handler(logger=logging.getLogger(__name__))
        self.srv = await self.loop.create_server(self.handler, *self.listen)

    def stop(self):
        self.srv.close()

    async def wait_closed(self):
        await self.handler.finish_connections(8)
        await self.srv.wait_closed()
        await self.app.finish()
