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

import json

from rallyci import base


LOG = logging.getLogger(__name__)

class Class(base.Class):

    @asyncio.coroutine
    def run(self):
        try:
            for line in open(self.cfg["path"], encoding="utf-8"):
                yield from asyncio.sleep(random.randint(1, 2))
                event = json.loads(line)
                self.config.root.handle(event)
        except Exception:
            LOG.exception("Stream error.")
