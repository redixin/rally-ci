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

        self.voting = config.get("voting", voting)
        self.root = task.root
        self.log = task.root.log
        self.timeout = self.config.get("timeout", 90) * 60
        self.id = utils.get_rnd_name(length=10)
        self.env = copy.deepcopy(self.task.event.env)
        self.env.update(config.get("env", {}))
        self.status = "__init__"
        self.log_path = os.path.join(self.task.id, config["name"])
        self.log.debug("Job %s initialized." % self.id)
        self.vms = []
        self.console_listeners = []
        self.name = config["name"]

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
        return

        for vm_conf in self.config["vms"]:
            vm = await self.provider.get_vm(vm_conf["name"], self)
            self.vms.append((vm, vm_conf))

        pub_dir = self.root.config.get_value("pub-dir", "/tmp/rally-pub")
        self.path = os.path.join(pub_dir, self.task_id, self.config["name"])
        os.makedirs(self.path)
        path = self.path + "/console.log"
        self.console_log = open(path, "wb")
        self.started_at = time.time()
        fut = self._run_scripts("scripts")
        return (await asyncio.wait_for(fut, self.timeout,
                                            loop=self.root.loop))

    def get_script(self, script_name):
        return self.root.config.get_script(script_name,
                                           self.task_local_config)

    async def _run_scripts(self, key, update_status=True):
        for vm, conf in self.vms:
            for script in conf.get(key, []):
                if update_status:
                    self.set_status(script)
                script = self.root.config.get_script(script,
                                                     self.task_local_config)
                ssh = await vm.get_ssh(script.get("user", "root"))
                cmd = script.get("interpreter", "/bin/bash -xe -s")
                self.root.log.debug("Running cmd %s" % cmd)
                e = await ssh.run(cmd, stdin=script["data"], env=self.env,
                                       stdout=partial(self._data_cb, 1),
                                       stderr=partial(self._data_cb, 2),
                                       check=False)
                self.root.log.debug("DONE")
                if e:
                    return e

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
            state = "failure" if self else "success"
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
