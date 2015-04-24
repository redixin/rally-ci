#!/usr/bin/env python
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import asyncio
import logging

import json


LOG = logging.getLogger(__name__)

class Job:
    def __init__(self, cr, name, cfg, event):
        self.cr = cr
        self.name = name
        self.event = event
        self.envs = []
        self.env = {}
        self.cfg = cfg
        self.status = 255
        self.logers = []
        for env in cfg.get("envs"):
            env = self.cr.config.init_obj_with_local("environments", env)
            self.envs.append(env)

    def to_dict(self):
        return {"id": id(self), "name": self.name}

    def logger(self, data):
        """Process script stdout+stderr."""
        print(data)

    @asyncio.coroutine
    def run(self):
        LOG.debug("Started job %s" % self)
        for env in self.envs:
            env.build(self)
        LOG.debug("Built env: %s" % self.env)
        runner = self.cr.config.init_obj_with_local("runners", self.cfg["runner"])
        LOG.debug("Runner initialized %r" % runner)
        self.status = runner.run(self)
        return self.status


class CR:
    def __init__(self, config, event):
        """Represent Change Request

        :param config: Config instance
        :param event: dict decoded from gerrit event json
        """

        self.config = config
        self.event = event
        self.jobs = []

        event_type = event["type"]
        LOG.debug("New event %s" % event_type)
        if event_type == "ref-updated":
            #TODO
            return

        project_name = self.event["change"]["project"]
        self.project = self.config.data["projects"].get(project_name)

        if not self.project:
            return

        if event_type == "patchset-created":
            self.prepare_jobs()

    def to_dict(self):
        return {"id": id(self), "jobs": [j.to_dict() for j in self.jobs]}

    def job_finished_callback(self, job):
        LOG.debug("Completed job: %r" % job)

    def prepare_jobs(self):
        for job_name in self.project["jobs"]:
            cfg = self.config.data["jobs"][job_name]
            job = Job(self, job_name, cfg, self.event)
            self.jobs.append(job)

    @asyncio.coroutine
    def run(self):
        futures = []
        coroutines = []
        for job in self.jobs:
            future = asyncio.async(job.run(), loop=self.config.root.loop)
            future.add_done_callback(self.job_finished_callback)
            futures.append(future)
        results = yield from asyncio.gather(*futures, return_exceptions=True)
        return results
