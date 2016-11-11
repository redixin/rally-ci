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
from functools import partial
import time
import os
import weakref

from rallyci import utils


class Job:
    finished_at = None

    def __init__(self, task, config, voting=False):
        """
        :param Task task:
        :param dict config: job config
        """
        self.config = config
        self._task = weakref.ref(task)

        self.task_id = task.id
        self.task_started_at = task.started_at
        self.task_local_config = task.local_config
        self.error = 256

        self.name = config["name"]
        self.voting = config.get("voting", voting)
        self.root = task.root
        self.log = task.root.log
        self.timeout = self.config.get("timeout", 90) * 60
        self.id = self.task_id + "/" + self.name
        self.env = copy.deepcopy(self.task.event.env)
        self.env.update(config.get("env", {}))
        self.status = "__init__"
        self.log_path = os.path.join(self.root.config.core["jobs-logs"],
                                     self.task.id, self.name)
        self.vms = []
        self.console_listeners = []

        os.makedirs(self.log_path)
        self.log.debug("Job %s initialized." % self.id)

    @property
    def task(self):
        return self._task()

    def __repr__(self):
        return "<Job %s(%s) [%s]>" % (self.config["name"],
                                      self.status, self.id)

    def set_status(self, status):
        self.status = status
        self.root.job_updated(self)

    def _data_cb(self, fd, data):
        for cb in self.console_listeners:
            try:
                cb((fd, data))
            except Exception:
                self.root.log.exception("")
        self.console_log.write(data.encode("utf-8"))
        self.console_log.flush()

    async def _run(self):
        """
        :param dict conf: vm item from job config
        """
        self.provider = self.root.providers[self.config["provider"]]
        self.cluster = await self.provider.get_cluster(self.config["cluster"])
        self.console_log = open(os.path.join(self.log_path, "console.log"), "wb")
        self.started_at = time.time()
        console_cb = lambda data: self.console_log.write(data.encode("utf8"))
        for vm, scripts in self.config["scripts"].items():
            vm = self.cluster.vms[vm]
            for script in scripts:
                script = self.root.config.get_script(script)
                self.root.log.debug("%s: running script: %s", self, script)
                await vm.ssh.wait()
                error = await vm.run_script(script, self.env, console_cb, console_cb)
                if error:
                    self.root.log.debug("%s error in script %s", self, script)
                    return error
        self.root.log.debug("%s all scripts success", self)
        # TODO: run scripts in parallel

    def get_script(self, script_name):
        return self.root.config.get_script(script_name,
                                           self.task_local_config)

    async def cleanup(self):
        await self.provider.delete_cluster(self.cluster)
        return
        try:
            await self._run_scripts("post", update_status=False)
        except Exception:
            self.log.exception("Error while running post scripts")
        try:
            for vm, conf in self.vms:
                for src, dst in conf.get("publish", []):
                    ssh = await vm.get_ssh()
                    await ssh.scp_get(src, os.path.join(self.path, dst))
                    ssh.close()
        except Exception:
            self.log.exception("Error while publishing %s" % self)
        await self.provider.cleanup(self)
        for cb in self.root.job_end_handlers:
            cb(self)  # TODO: move it to root

    async def run(self):
        self.log.info("Starting %s (timeout: %s)" % (self, self.timeout))
        self.set_status("queued")
        await self.task.event.job_started_cb(self)
        try:
            self.error = await self._run()
            self.set_status("FAILURE" if self.error else "SUCCESS")
            state = "failure" if self.error else "success"
            await self.task.event.job_finished_cb(self, state)
        except asyncio.TimeoutError:
            self.set_status("TIMEOUT")
            self.log.info("Timed out %s" % self)
            await self.task.event.job_finished_cb(self, "error")
        except asyncio.CancelledError:
            self.set_status("CANCELLED")
            self.log.info("Cancelled %s" % self)
            await self.task.event.job_finished_cb(self, "error")
        except Exception:
            self.set_status("ERROR")
            self.log.exception("Error running %s" % self)
            await self.task.event.job_finished_cb(self, "error")
        finally:
            self.finished_at = time.time()
        self.set_status(self.status)  # TODO: fix cleanup in http status

    def to_dict(self):
        return {"id": self.id,
                "name": self.config["name"],
                "status": self.status,
                "task": self.task_id,
                "finished_at": self.finished_at,
                "seconds": int(time.time()) - self.task_started_at,
                }

    def __del__(self):
        print("DEL %s" % self)
