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
import time
import logging

LOG = logging.getLogger(__name__)


class Runner:

    def __init__(self, cfg, job, local_cfg):
        self.cfg = cfg
        self.job = job
        self.local_cfg = local_cfg

    @asyncio.coroutine
    def boot(self):
        sleep = self.cfg.get("sleep-build", (1, 2))
        yield from asyncio.sleep(random.randint(*sleep))

    @asyncio.coroutine
    def build(self):
        sleep = self.cfg.get("sleep-build", (1, 2))
        LOG.debug("Sleeping %s" % str(sleep))
        yield from asyncio.sleep(random.randint(*sleep))

    @asyncio.coroutine
    def run(self):
        self.job.started_at = time.time()
        sleep = self.cfg.get("sleep-run", (1, 2))
        yield from asyncio.sleep(random.randint(*sleep))

    @asyncio.coroutine
    def run_script(self, script):
        sleep = self.cfg.get("sleep-run", (1, 2))
        LOG.debug("Sleeping %s" % str(sleep))
        yield from asyncio.sleep(random.randint(*sleep))

    @asyncio.coroutine
    def cleanup(self):
        sleep = self.cfg.get("sleep-cleanup", (2, 4))
        LOG.debug("Sleeping %s" % str(sleep))
        yield from asyncio.sleep(random.randint(*sleep))
