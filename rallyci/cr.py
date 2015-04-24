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
    def __init__(self, config, cfg, event):
        self.event = event
        self.envs = []
        self.env = {}
        self.config = config
        self.cfg = cfg
        self.status = 255
        self.logers = []
        for env in cfg.get("envs"):
            env = config.init_class_with_local("environments", env)
            self.envs.append(env)

    @asyncio.coroutine
    def run(self):
        LOG.debug("Started job %s" % self)
        for env in self.envs:
            env.build(self)
        LOG.debug("Built env: %s" % self.env)
        runner = self.config.init_class_with_local("runners", self.cfg["runner"])
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
        self.handler = self.get_handler()

    def get_handler(self):
        event_type = self.event["type"]
        LOG.debug("New event. Type: %s" % event_type)
        if self.project:
            if event_type == "patchset-created":
                return self.handle_patchset_created
            else:
                LOG.debug("Unknown event type: %s" % self.event["type"])
        else:
            LOG.debug("Unknown project %s" % self.project_name)

    @asyncio.coroutine
    def run(self):
        return self.handler()

    @property
    def project_name(self):
        print(self.event)
        if self.event["type"] == "ref-updated":
            print(self.event)
            return self.event["ref"]["project"]
        return self.event["change"]["project"]

    @property
    def project(self):
        return self.config.projects.get(self.project_name)

    def job_finished_callback(self, job):
        LOG.debug("Completed job: %r" % job)

    def handle_patchset_created(self):
        self.jobs = []
        futures = []
        coroutines = []
        for job in self.project["jobs"]:
            cfg = self.config.jobs[job]
            job = Job(self.config, cfg, self.event)
            self.jobs.append(job)
        for job in self.jobs:
            future = asyncio.async(job.run(), loop=self.config.root.loop)
            future.add_done_callback(self.job_finished_callback)
            futures.append(future)
        results = yield from asyncio.gather(*futures, return_exceptions=True)
        return results
