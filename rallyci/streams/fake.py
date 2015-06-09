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
import random

from rallyci.streams import gerrit

LOG = logging.getLogger(__name__)


class Class(gerrit.Class):

    def __init__(self, **kwargs):
        self.cfg = kwargs

    @asyncio.coroutine
    def run(self):
        while 1:
            try:
                for line in open(self.cfg["path"], encoding="utf-8"):
                    sleep = self.cfg.get("sleep", (1, 2))
                    self._handle_line(line)
                    yield from asyncio.sleep(random.randint(*sleep))
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("Stream error.")
