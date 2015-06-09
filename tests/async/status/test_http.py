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
import socket
import unittest

from rallyci.status import http

import aiohttp


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class HttpTestCase(unittest.TestCase):

    def test_index(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        config = {"listen": ("localhost", get_free_port())}
        h = http.Class(config)

        @asyncio.coroutine
        def test(loop):
            url = "http://localhost:%d" % config["listen"][1]
            response = yield from aiohttp.request("GET", url, loop=loop)
            body = yield from response.read()
            self.assertIn("Rally-CI", str(body))

        asyncio.async(h.run(loop), loop=loop)
        loop.run_until_complete(test(loop))
        h.stop()
