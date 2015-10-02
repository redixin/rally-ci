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


class Root:
    def __init__(self, loop):
        self.tasks = {}
        self.loop = loop
        self.services = []
        self.providers = {}
        self.task_start_handlers = []
        self.task_end_handlers = []
        self.job_update_handlers = []
        self.stop_event = asyncio.Event()

    @asyncio.coroutine
    def run_service(self, service):
        try:
            yield from service.run()
        except asyncio.CancelledError:
            self.log.info("Stopped %s" % service)
        except Exception:
            self.log.exception("Exception in %s" % service)
        try:
            yield from asyncio.shield(service.cleanup())
        except asyncio.CancelledError:
            pass
        except Exception:
            self.log.exception("Exception while cleanup %s" % service)

    def start_services(self):
        for service in self.config.iter_instances("service"):
            fut = asyncio.async(self.run_service(service), loop=self.loop)
            self.services.append(fut)
            fut.add_done_callback(self.services.remove)

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
        while fs:
            done, pending = yield from asyncio.wait(
                    list(fs.keys()), return_when=futures.FIRST_COMPLETED)
            for fut in done:
                self.log.debug("Finished %s" % fs[fut])
                del(fs[fut])

    @asyncio.coroutine
    def run(self):
        self.start_services()
        for prov in self.config.iter_providers():
            self.providers[prov.name] = prov
            prov.start()
        yield from self.stop_event.wait()
        self.log.info("Interrupted.")
        self.stop_services()
        if self.tasks:
            for fut in self.tasks.keys():
                self.log.debug("Cancelling task %s" % self.tasks[fut])
                fut.cancel()
            yield from asyncio.shield(self.wait_fs(self.tasks))
        self.loop.stop()

    def reload(self):
        try:
            new_config = Config(self.filename)
        except Exception:
            self.log.exception("Error loading new config")
            return
        self.stop_services()
        self.config = new_config
        self.start()

    def task_done(self, fut):
        self.log.info("Task done %s" % fut)
        task = self.tasks[fut]
        for cb in self.task_end_handlers:
            cb(task)

    def job_updated(self, job):
        for cb in self.job_update_handlers:
            cb(job)

    def handle(self, task):
        self.log.debug("Starting task %s" % task)
        fut = asyncio.async(task.run_jobs(), loop=self.loop)
        self.tasks[fut] = task
        fut.add_done_callback(self.task_done)
        for cb in self.task_start_handlers:
            cb(task)

    def get_daemon_statistics(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {"type": "daemon-statistics", "memory-used": getattr(usage, "ru_maxrss")}
