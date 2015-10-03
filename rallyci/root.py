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
import logging
import resource
from rallyci.config import Config
import time

class Root:
    def __init__(self, loop):
        self._running_objects = {}
        self._running_cleanups = []

        self.tasks = {}
        self.loop = loop
        self.services = {}
        self.providers = {}
        self.task_start_handlers = []
        self.task_end_handlers = []
        self.job_update_handlers = []
        self.stop_event = asyncio.Event()

    @asyncio.coroutine
    def run_obj(self, obj):
        try:
            self.log.debug("Running obj %s" % obj)
            yield from obj.run()
        except asyncio.CancelledError:
            self.log.info("Cancelled %s" % obj)
        except Exception:
            self.log.exception("Exception running %s" % obj)

    def start_obj(self, obj):
        fut = asyncio.async(self.run_obj(obj), loop=self.loop)
        fut.add_done_callback(self.schedule_cleanup)
        self._running_objects[fut] = obj
        return fut

    @asyncio.coroutine
    def run_cleanup(self, obj):
        try:
            yield from obj.cleanup()
        except Exception:
            self.log.exception("Exception in cleanup %s" % obj)

    def schedule_cleanup(self, fut):
        obj = self._running_objects.pop(fut)
        fut = asyncio.async(self.run_cleanup(obj), loop=self.loop)
        self._running_cleanups.append(fut)

    def start_services(self):
        for service in self.config.iter_instances("service"):
            self.start_obj(service)

    def stop_services(self):
        for service in self.services:
            service.cancel()

    def load_config(self, filename):
        self.filename = filename
        self.config = Config(self, filename)
        self.log = logging.getLogger(__name__)

    @asyncio.coroutine
    def wait_fs(self, fs):
        """Wait for futures.

        :param fs: dict where key is future and value is related object
        """
        self.log.debug("Waiting for %s" % fs.values())
        while fs:
            done, pending = yield from asyncio.wait(
                    list(fs.keys()), return_when=futures.FIRST_COMPLETED)
            for fut in done:
                if fut in fs:
                    del(fs[fut])

    @asyncio.coroutine
    def run(self):
        self.start_services()
        for prov in self.config.iter_providers():
            self.providers[prov.name] = prov
            prov.start()
        yield from self.stop_event.wait()
        self.log.info("Interrupted.")
        for obj in self._running_objects:
            obj.cancel()
        yield from self.wait_fs(self._running_objects)
        if self._running_cleanups:
            yield from asyncio.wait(self._running_cleanups,
                                    return_when=futures.ALL_COMPLETED)
        self.loop.stop()

    def task_done(self, fut):
        self.log.info("Task done %s" % fut)
        task = self.tasks[fut]
        task.finished_at = int(time.time())
        for cb in self.task_end_handlers:
            cb(task)
        del(self.tasks[fut])

    def job_updated(self, job):
        for cb in self.job_update_handlers:
            cb(job)

    def handle(self, task):
        self.log.debug("Starting task %s" % task)
        fut = asyncio.async(self.run_obj(task), loop=self.loop)
        self.tasks[fut] = task
        fut.add_done_callback(self.task_done)
        for cb in self.task_start_handlers:
            cb(task)

    def get_daemon_statistics(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {"type": "daemon-statistics", "memory-used": getattr(usage, "ru_maxrss")}
