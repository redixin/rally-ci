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
from concurrent.futures import ALL_COMPLETED
import time
import os
import string

from rallyci import utils


class Job:

    voting = False
    finished_at = None
    _vms = []

    def __init__(self, task, config):
        """
        :param Task task:
        :param dict config: job config
        """
        self.config = config
        self.task = task

        self.root = task.root
        self.log = task.root.log
        self.timeout = self.config.get("timeout", 90) * 60
        self.id = utils.get_rnd_name("job_", length=10)
        self.env = config.get("env", {}).copy()
        self.status = "__init__"
        self.log_path = os.path.join(self.task.id, config["name"])
        self.log.debug("Job %s initialized." % self.id)
        Job.BOOT_LOCK = asyncio.Lock(loop=task.root.loop)

    def __repr__(self):
        return "<Job %s(%s) [%s]>" % (self.config["name"],
                                      self.status, self.id)

    def set_status(self, status):
        self.status = status
        self.root.job_updated(self)

    @asyncio.coroutine
    def _run(self):
        """
        :param dict conf: vm item from job config
        """
        provider = self.root.providers[self.config["provider"]]
        vms = {}
        for vm in self.config["vms"]:
            fut = asyncio.async(provider.get_vm(vm["name"], self),
                                loop=self.root.loop)
            vms[fut] = vm
        with (yield from Job.BOOT_LOCK):
            done, pending = yield from asyncio.wait(list(vms.keys()),
                                                    return_when=ALL_COMPLETED)
        for fut in done:
            fut.result()

        #TODO

    @asyncio.coroutine
    def run(self):
        self.log.info("Starting %s (timeout: %s)" % (self, self.timeout))
        self.set_status("queued")
        self.started_at = time.time()
        fut = asyncio.async(self._run(), loop=self.root.loop)
        try:
            self.error = yield from asyncio.wait_for(fut, timeout=self.timeout)
            self.set_status("FAILURE" if self.error else "SUCCESS")
        except asyncio.TimeoutError:
            self.set_status("TIMEOUT")
            self.log.info("Timed out %s" % self)
        except asyncio.CancelledError:
            self.set_status("CANCELLED")
            self.log.info("Cancelled %s" % self)
        except Exception:
            self.set_status("ERROR")
            self.log.exception("Error running %s" % self)

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
                "seconds": int(time.time()) - self.task.started_at,
                }
