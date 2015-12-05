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


class Job:

    def __init__(self, task, config):
        self.voting = True
        self.error = 254 # FIXME
        self.queued_at = time.time()
        self.task = task
        self.root = task.root
        self.config = config
        self.timeout = self.config.get("timeout", 90) * 60
        self.id = utils.get_rnd_name("job_", length=10)
        self.env = config.get("env", {}).copy()
        self.status = "__init__"
        self.finished_at = 0
        self.log_path = os.path.join(self.task.id, config["name"])
        LOG.debug("Job %s initialized." % self.id)

    def __str__(self):
        return "<Job %s(%s) [%s]>" % (self.config["name"],
                                      self.status, self.id)

    def __repr__(self):
        return self.__str__()

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
        self.runner = self.root.config.get_instance(runner_cfg, "Runner", self,
                                                    runner_local_cfg)
        fut = asyncio.async(self.runner.run(), loop=self.root.loop)
        try:
            self.error = yield from asyncio.wait_for(fut, timeout=self.timeout)
            self.set_status("FAILURE" if self.error else "SUCCESS")
        except asyncio.TimeoutError:
            self.set_status("TIMEOUT")
            LOG.info("Timed out %s" % self)
        except asyncio.CancelledError:
            self.set_status("CANCELLED")
            LOG.debug("Cancelled %s" % self)
        except Exception:
            self.set_status("ERROR")
            LOG.exception("Error running %s" % self)

    @asyncio.coroutine
    def cleanup(self):
        if hasattr(self, "runner"):
            yield from self.runner.cleanup()
        else:
            yield from asyncio.sleep(0)

    def to_dict(self):
        return {"id": self.id,
                "name": self.config["name"],
                "status": self.status,
                "task": self.task.id,
                "finished_at": self.finished_at,
                "seconds": int(time.time()) - self.queued_at,
                }
