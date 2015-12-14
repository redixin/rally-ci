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
import copy
import cgi
import time

import aiohttp

from rallyci.job import Job
from rallyci import utils


class Task:

    def __init__(self, root, event):
        """
        :param Root root:
        :param Event event:
        """
        self.root = root
        self.event = event

        self.finished_at = None
        self.started_at = time.time()
        self.id = utils.get_rnd_name("task_", length=10)
        self._finished = asyncio.Event(loop=root.loop)
        self._job_futures = {}

    def __repr__(self):
        return "<Task %s %s>" % (self.event.project, self.id)

    @asyncio.coroutine
    def _get_local_cfg(self, url):
        r = yield from aiohttp.get(url)
        if r.status == 200:
            local_cfg = yield from r.text()
            local_cfg = yaml.safe_load(local_cfg)
        else:
            self.root.log.debug("No local cfg for %s" % self)
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
        fut = self.root.start_obj(job)
        self._job_futures[fut] = job
        fut.add_done_callback(self._job_done_cb)

    def _start_jobs(self, local_cfg):
        """
        :param list local_cfg: config loaded from project
        """
        cfg_gen = self.root.config.get_jobs

        if self.event.event_type == "change-merged":
            for cfg in cfg_gen(self.event.project, "merged-jobs", local_cfg):
                self._start_job(cfg)

        for cfg in cfg_gen(self.event.project, "jobs", local_cfg):
            self._start_job(cfg, voting=True)

        for cfg in cfg_gen(self.event.project, "non-voting-jobs", local_cfg):
            self._start_job(cfg)

    @asyncio.coroutine
    def run(self):
        if self.event.cfg_url:
            local_cfg = yield from self._get_local_cfg(self.event.cfg_url)
        self._start_jobs(local_cfg)
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

    def to_dict(self):
        return {
            "id": self.id,
            "jobs": [j.to_dict() for j in self._job_futures.values()],
            "finished_at": self.finished_at,
            "subject": cgi.escape(self.event.subject),
            "project": cgi.escape(self.event.project),
            "url": self.event.url,
        }
