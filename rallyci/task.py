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
        :param Event event:
        """
        self.root = root
        self.event = event

        self.local_config = None
        self.jobs = []
        self.finished_at = None
        self.started_at = time.time()
        self.id = utils.get_rnd_name("task_", length=10)
        self._finished = asyncio.Event(loop=root.loop)
        self._job_futures = {}

    def __repr__(self):
        return "<Task %s %s>" % (self.event.project, self.id)

    @asyncio.coroutine
    def _get_local_config(self, url):
        self.root.log.debug("Trying to get config %s" % url)
        r = yield from aiohttp.get(url)
        if r.status == 200:
            local_cfg = yield from r.text()
            try:
                local_cfg = yaml.safe_load(local_cfg)
            except Exception as ex:
                local_cfg = []
                self.summary += "Error loading local config: %s" % ex
        else:
            self.root.log.debug("No local cfg for %s" % self)
            self.root.log.debug("Response %s" % r)
            local_cfg = []
        r.close()
        return local_cfg

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

        if self.event.event_type == "change-merged":
            for cfg in cfg_gen(self.event.project, "merged-jobs",
                               self.local_config):
                self._start_job(cfg)
                return

        for cfg in cfg_gen(self.event.project, "jobs", self.local_config):
            self._start_job(cfg, voting=True)

        for cfg in cfg_gen(self.event.project, "non-voting-jobs", None):
            self._start_job(cfg)

    @asyncio.coroutine
    def run(self):
        if self.event.cfg_url:
            self.local_config = yield from self._get_local_config(
                    self.event.cfg_url)
        self._start_jobs()
        for cb in self.root.task_start_handlers:
            cb(self)
        while not self._finished.is_set():
            try:
                yield from self._finished.wait()
                self.finished_at = time.time()
            except asyncio.CancelledError:
                self.root.log.info("Cancelled %s" % self)
                for fut in self._job_futures:
                    fut.cancel()
                return

    @asyncio.coroutine
    def cleanup(self):
        for fut, job in self._job_futures.items():
            if not fut.cancelled():
                fut.cancel()
        yield from self._finished.wait()
        # self.jobs = []

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
