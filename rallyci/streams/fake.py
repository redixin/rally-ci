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
import random

import json

from rallyci import base



class Class(base.Class):

    @asyncio.coroutine
    def run(self):
        while True:
            for line in open(self.cfg["path"]):
                yield from asyncio.sleep(random.randint(2, 4))
                event = json.loads(line)
                self.config.root.handle(event)
