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
import signal
import resource
import time

from rallyci.config import Config


class Root:
    def __init__(self, loop, filename, verbose):
        self._running_objects = {}
        self._running_cleanups = []

        self.filename = filename
        self.verbose = verbose

        self.tasks = {}
        self.task_set = set()
        self.loop = loop
        self.providers = {}
        self.task_start_handlers = []
        self.task_end_handlers = []
        self.job_update_handlers = []
        self.stop_event = asyncio.Event(loop=loop)
        self.reload_event = asyncio.Event(loop=loop)

    def stop(self):
        self.loop.remove_signal_handler(signal.SIGINT)
        self.loop.remove_signal_handler(signal.SIGHUP)
        self.stop_event.set()

    @asyncio.coroutine
    def run_obj(self, obj):
        yield from self.run_coro(obj.run())

    @asyncio.coroutine
    def run_coro(self, coro):
        try:
            yield from coro
        except asyncio.CancelledError:
            self.log.info("Cancelled %s" % coro)
        except Exception:
            self.log.exception("Exception running %s" % coro)

    def start_task(self, task):
        if task.event.key in self.task_set:
            self.log.warning("Task '%s' is already running" % task.event.key)
            return
        self.task_set.add(task.event.key)
        for cb in self.task_start_handlers:
            cb(task)
        fut = self.start_obj(task)
        self.tasks[fut] = task
        fut.add_done_callback(self.task_done_cb)

    def task_done_cb(self, fut):
        self.tasks_set.remove(fut)
        task = self.tasks.pop(fut)
        self.tasks_set.remove(task.event.key)
        for handler in self.task_start_handlers:
            try:
                handler(task)
            except Exception:
                self.log.exception(
                    "Exception in task end handler %s %s" % (task, cb))

    def start_coro(self, coro):
        fut = asyncio.async(self.run_coro(obj), loop=self.loop)
        return fut

    def start_obj(self, obj):
        fut = asyncio.async(self.run_obj(obj), loop=self.loop)
        obj.fut = fut
        self._running_objects[fut] = obj
        if hasattr(obj, "cleanup"):
            fut.add_done_callback(self.schedule_cleanup)
        else:
            fut.add_done_callback(self._running_objects.pop)
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
        for service in self.config.iter_instances("service", "Service"):
            self.start_obj(service)

    def _load_config(self):
        self.config = Config(self, self.filename, self.verbose)
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
                config = Config(self, self.filename, self.verbose)
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
        self._load_config()
        self.start_services()
        for prov in self.config.iter_providers():
            self.providers[prov.name] = prov
            prov.start()
        reload_fut = asyncio.async(self.reload(), loop=self.loop)
        yield from self.stop_event.wait()
        self.log.info("Interrupted.")
        reload_fut.cancel()
        yield from reload_fut
        for obj in self._running_objects:
            obj.cancel()
        yield from self.wait_fs(self._running_objects)
        if self._running_cleanups:
            yield from asyncio.wait(self._running_cleanups,
                                    return_when=futures.ALL_COMPLETED)
        for provider in self.providers.values():
            yield from prov.stop()

    def job_updated(self, job):
        for cb in self.job_update_handlers:
            cb(job)

    def get_daemon_statistics(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {"type": "daemon-statistics", "memory-used": getattr(usage, "ru_maxrss")}
