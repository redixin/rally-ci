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
import copy
from concurrent.futures import ALL_COMPLETED
from functools import partial
import gzip
import time
import os
import string

from rallyci import utils


class Job:
    finished_at = None

    def __init__(self, task, config, voting=False):
        """
        :param Task task:
        :param dict config: job config
        """
        self.config = config
        self.task = task

        self.voting = config.get("voting", voting)
        self.root = task.root
        self.log = task.root.log
        self.timeout = self.config.get("timeout", 90) * 60
        self.id = utils.get_rnd_name("job_", length=10)
        self.env = copy.deepcopy(self.task.event.env)
        self.env.update(config.get("env", {}))
        self.status = "__init__"
        self.log_path = os.path.join(self.task.id, config["name"])
        self.log.debug("Job %s initialized." % self.id)
        self.vms = []
        self.console_listeners = []
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
        self.provider = self.root.providers[self.config["provider"]]
        vms = {}
        for vm in self.config["vms"]:
            fut = asyncio.async(self.provider.get_vm(vm["name"], self),
                                loop=self.root.loop)
            vms[fut] = vm
        with (yield from Job.BOOT_LOCK):
            self.set_status("boot")
            done, pending = yield from asyncio.wait(list(vms.keys()),
                                                    return_when=ALL_COMPLETED)
        for fut in done:
            self.vms.append((fut.result(), vms[fut]))

        pub_dir = self.root.config.get_value("pub-dir", "/tmp/rally-pub")
        path = os.path.join(pub_dir, self.task.id, self.config["name"])
        os.makedirs(path)
        path += "/console.log.gz"
        console_log = gzip.open(path, "wb")

        def _data(fd, data):
            for cb in self.console_listeners:
                try:
                    cb((fd, data))
                except Exception:
                    self.root.log.exception("")
            console_log.write(data.encode("utf-8"))

        for vm, conf in self.vms:
            for script in conf.get("scripts", []):
                self.set_status(script)
                script = self.root.config.data["script"][script]
                error = yield from vm.run_script(script, env=self.env,
                                                 check=False,
                                                 cb_out=partial(_data, 1),
                                                 cb_err=partial(_data, 2))
                if error:
                    console_log.close()
                    return error

        for vm, conf in self.vms:
            for script in conf.get("post", []):
                self.set_status(script)
                script = self.root.config.data["script"][script]
                error = yield from vm.run_script(script, env=self.env,
                                                 check=False,
                                                 cb_out=partial(_data, 1),
                                                 cb_err=partial(_data, 2))

        console_log.close()

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
        finally:
            self.finished_at = time.time()
        self.set_status(self.status) # TODO: fix cleanup in http status

    @asyncio.coroutine
    def cleanup(self):
        yield from self.provider.cleanup(self)

    def to_dict(self):
        return {"id": self.id,
                "name": self.config["name"],
                "status": self.status,
                "task": self.task.id,
                "finished_at": self.finished_at,
                "seconds": int(time.time()) - self.task.started_at,
                }
