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
import unittest
import mock

from rallyci import root


class RootTestCase(unittest.TestCase):

    def set_timeout(self, timeout):
        if hasattr(self, "_timeout"):
            self._timeout.cancel()
        self._timeout = self.loop.call_later(timeout, self.loop.stop)

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.set_timeout(1)

    def tearDown(self):
        self._timeout.cancel()
        self.loop.stop()
        self.loop.close()
