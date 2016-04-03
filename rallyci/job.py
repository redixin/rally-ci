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
from rallyci import base

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
        self.provider = self.task.root.providers[self.config["provider"]]
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
        pub_dir = self.root.config.get_value("pub-dir", "/tmp/rally-pub")
        self.path = os.path.join(pub_dir, self.task_id, self.config["name"])
        os.makedirs(self.path)

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

    def _out_cb(self, data):
        self._data_cb(1, data)

    def _err_cb(self, data):
        self._data_cb(2, data)

    @asyncio.coroutine
    def _run(self):
        """
        :param dict conf: vm item from job config
        """
        self.provider = self.root.providers[self.config["provider"]]
        yield from self.provider.get_vms(self)
        path = self.path + "/console.log"
        self.console_log = open(path, "wb")
        self.started_at = time.time()
        for vm in self.vms:
            result = yield from vm.run_scripts("scripts",
                                               script_cb=self.set_status,
                                               out_cb=self._out_cb,
                                               err_cb=self._err_cb)
            if result:
                return result

    @asyncio.coroutine
    def cleanup(self):
        if hasattr(self, "console_log"):
            self.console_log.close()
        self.console_log = open(self.path + "/post.log", "wb")
        # TODO: do this in parallel
        for vm in self.vms:
            yield from vm.run_scripts("post", out_cb=self._out_cb, err_cb=self._err_cb)
            yield from vm.publish(self.path)
            yield from vm.force_off() # destroy in any case
            yield from vm.destroy()
        #
        for cb in self.root.job_end_handlers:
            cb(self)  # TODO: move it to root

    @asyncio.coroutine
    def run(self):
        self.log.info("Starting %s (timeout: %s)" % (self, self.timeout))
        self.set_status("queued")
        try:
            self.error = yield from self._run()
            self.set_status("FAILURE" if self.error else "SUCCESS")
        except asyncio.TimeoutError:
            self.set_status("TIMEOUT")
            self.log.info("Timed out %s" % self)
            raise
        except asyncio.CancelledError:
            self.set_status("CANCELLED")
            self.log.info("Cancelled %s" % self)
            raise
        except Exception:
            self.set_status("ERROR")
            self.log.exception("Error running %s" % self)
            raise
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
