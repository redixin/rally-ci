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
import cgi
import time

import aiohttp
import yaml

from rallyci.job import Job
from rallyci import utils


class Task:
    summary = ""

    def __init__(self, root, event):
        """
        :param Root root:
        :param rallyci.base.Event event:
        """
        self.root = root
        self.event = event

        self.local_config = None
        self.jobs = []
        self.finished_at = None
        self.started_at = time.time()
        self.id = utils.get_rnd_name(length=10)
        self._finished = asyncio.Event(loop=root.loop)
        self._job_futures = {}

    def __repr__(self):
        return "<Task %s %s>" % (self.event.project, self.id)

    def _job_done_cb(self, fut):
        job = self._job_futures.pop(fut)
        self.root.log.info("Finished job %s" % job)
        if not self._job_futures:
            self._finished.set()

    def _start_job(self, config, voting=False):
        job = Job(self, config, voting)
        self.jobs.append(job)
        fut = self.root.start_obj(job)
        self._job_futures[fut] = job
        fut.add_done_callback(self._job_done_cb)

    def _start_jobs(self):
        cfg_gen = self.root.config.get_jobs

        if self.event.event_type == "push":
            for cfg in cfg_gen(self.event.project, "jobs-push",
                               self.local_config):
                self._start_job(cfg)
            return

        if self.event.event_type == "cr":
            for cfg in cfg_gen(self.event.project, "jobs-cr", self.local_config):
                self._start_job(cfg, voting=True)
            for cfg in cfg_gen(self.event.project, "jobs-cr-non-voting", None):
                self._start_job(cfg)

    async def run(self):
        self.root.log.info("Starting task %s" % self)
        self.local_config = await self.event.get_local_config()
        self._start_jobs()
        if not self.jobs:
            # TODO
            self._finished.set()
            return
        for cb in self.root.task_start_handlers:
            cb(self)
        while not self._finished.is_set():
            try:
                await self._finished.wait()
                self.finished_at = time.time()
            except asyncio.CancelledError:
                self.root.log.info("Cancelled %s" % self)
                for fut in self._job_futures:
                    fut.cancel()
                return

    async def cleanup(self):
        for fut, job in self._job_futures.items():
            if not fut.cancelled():
                fut.cancel()
        await self._finished.wait()

    def to_dict(self):
        return {
            "id": self.id,
            "jobs": [j.to_dict() for j in self.jobs],
            "finished_at": self.finished_at,
            "subject": cgi.escape(self.event.subject),
            "project": cgi.escape(self.event.project),
            "url": self.event.url,
        }

    def __del__(self):
        print("DEL %s" % self)
