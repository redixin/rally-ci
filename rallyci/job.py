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
from concurrent import futures
import time
import os
import string

from rallyci import utils

import logging
LOG = logging.getLogger(__name__)

SAFE_CHARS = string.ascii_letters + string.digits + "_"
INTERVALS = [1, 60, 3600, 86400]
NAMES = [('s', 's'),
         ('m', 'm'),
         ('h', 'h'),
         ('day', 'days')]


def _get_valid_filename(name):
    name = name.replace(" ", "_")
    return "".join([c for c in name if c in SAFE_CHARS])


class Job:

    def __init__(self, event, name):
        self.voting = True
        self.error = 254 # FIXME
        self.queued_at = time.time()
        self.event = event
        self.name = name
        self.root = event.root
        self.config = event.root.config.data["job"][name]
        self.timeout = self.config.get("timeout", 180) * 60
        self.id = utils.get_rnd_name("JOB", length=10)
        self.env = self.config.get("env", {}).copy()
        self.status = "__init__"
        self.log_path = os.path.join(self.event.id, self.name)
        LOG.debug("Job %s initialized." % self.id)

    def __str__(self):
        return "<Job %s [%s]>" % (self.name, self.id)

    def set_status(self, status):
        self.status = status
        self.root.job_updated(self)

    @asyncio.coroutine
    def run(self):
        LOG.info("Starting %s (timeout: %s)" % (self, self.timeout))
        self.set_status("queued")
        self.started_at = time.time()
        runner_local_cfg = self.config["runner"]
        runner_cfg = self.root.config.data["runner"][runner_local_cfg["name"]]
        self.runner = self.root.config.get_instance(runner_cfg, self,
                                                    runner_local_cfg)

        fut = asyncio.async(self.runner.run())
        try:
            error = yield from asyncio.wait_for(fut, timeout=self.timeout)
            self.set_status("FAILURE" if error else "SUCCESS")
        except asyncio.TimeoutError:
            self.set_status("TIMEOUT")
            LOG.info("Timed out %s" % self)
        finally:
            self.finished_at = time.time()
        try:
            yield from self.runner.cleanup()
        except:
            LOG.exception("Failed to clean up %s" % self)

    def to_dict(self):
        return {"id": self.id,
                "name": self.name,
                "status": self.status,
                "seconds": int(time.time()) - self.queued_at,
                }
