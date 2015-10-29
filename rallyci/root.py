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
        self.providers = {}
        self.task_start_handlers = []
        self.task_end_handlers = []
        self.job_update_handlers = []
        self.stop_event = asyncio.Event()
        self.reload_event = asyncio.Event()

    @asyncio.coroutine
    def run_obj(self, obj):
        try:
            self.log.debug("Running obj %s" % obj)
            yield from obj.run()
        except asyncio.CancelledError:
            self.log.info("Cancelled %s" % obj)
        except Exception:
            self.log.exception("Exception running %s" % obj)

    def start_task(self, task):
        for cb in self.task_start_handlers:
            cb(task)
        fut = self.start_obj(task)
        self.tasks[fut] = task
        fut.add_done_callback(self.tasks.pop)

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

    def load_config(self, args):
        self.args = args
        self.config = Config(self, args)
        self.config.configure_logging()
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
    def reload(self):
        """Wait for reload events and reload config when event set."""
        while 1:
            try:
                yield from self.reload_event.wait()
                self.log.info("Reloading configuration...")
            except asyncio.CancelledError:
                return
            finally:
                self.reload_event.clear()
            try:
                config = Config(self, self.args)
                self.log.debug("New config instance %s" % config)
                yield from config.validate()
                self.config = config
                self.log.info("Done")
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.log.exception("Error loading new config")

    @asyncio.coroutine
    def run(self):
        self.start_services()
        for prov in self.config.iter_providers():
            self.providers[prov.name] = prov
            prov.start()
        reload_fut = asyncio.async(self.reload(), loop=self.loop)
        yield from self.stop_event.wait()
        reload_fut.cancel()
        yield from reload_fut
        self.log.info("Interrupted.")
        for obj in self._running_objects:
            obj.cancel()
        yield from self.wait_fs(self._running_objects)
        if self._running_cleanups:
            yield from asyncio.wait(self._running_cleanups,
                                    return_when=futures.ALL_COMPLETED)

    def job_updated(self, job):
        for cb in self.job_update_handlers:
            cb(job)

    def get_daemon_statistics(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {"type": "daemon-statistics", "memory-used": getattr(usage, "ru_maxrss")}
