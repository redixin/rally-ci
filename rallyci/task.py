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
from concurrent import futures
import time

import aiohttp
from functools import partial
import yaml

from rallyci.job import Job
from rallyci import utils
from rallyci import base

class Task(base.ObjRunnerMixin):

    def __init__(self, root, event, local_config):
        """
        :param Root root:
        :param Event event:
        """
        self.root = root
        self.event = event
        self.local_config = local_config

        self.loop = root.loop
        self.log = root.log
        self.local_config = None
        self.jobs = []
        self.finished_at = None
        self.started_at = time.time()
        self.id = utils.get_rnd_name(length=10)

        cfg_gen = self.root.config.get_jobs
        if event.event_type == "change-merged":
            for cfg in cfg_gen(event.project, "merged-jobs",
                               self.local_config):
                self.jobs.append(Job(self, cfg, voting=True))
            return
        for cfg in cfg_gen(event.project, "jobs", self.local_config):
            self.jobs.append(Job(self, cfg, voting=True))
        for cfg in cfg_gen(event.project, "non-voting-jobs",
                           self.local_config):
            self.jobs.append(Job(self, cfg, voting=False))

    @asyncio.coroutine
    def run(self):
        for job in self.jobs:
            self.start_obj(job)
        try:
            yield from self.wait_objs()
        except asyncio.CancelledError:
            self.cancel_objs()
            yield from self.wait_objs()
        yield from asyncio.shield(self.wait_cleanups(), loop=self.loop)

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

    def __repr__(self):
        return "<Task %s %s>" % (self.event.project, self.id)
