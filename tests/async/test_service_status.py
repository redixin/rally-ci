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
import mock

from rallyci.services import status
from rallyci.utils import get_free_port

import aiohttp


class HttpTestCase(unittest.TestCase):

    def test_index(self):
        loop = asyncio.get_event_loop()
        asyncio.set_event_loop(None)
        config = {"listen": ("localhost", get_free_port())}
        root = mock.Mock(loop=loop)
        ss = status.Class(root, **config)

        @asyncio.coroutine
        def test(loop):
            url = "http://localhost:%d" % config["listen"][1]
            yield from asyncio.sleep(1, loop=loop) #  FIXME
            response = yield from aiohttp.request("GET", url, loop=loop)
            body = yield from response.read()
            self.assertIn("Rally-CI", str(body))

        fut = asyncio.async(ss.run(), loop=loop)
        loop.run_until_complete(test(loop))
        fut.cancel()
        loop.run_until_complete(fut)
        loop.run_until_complete(ss.cleanup())
