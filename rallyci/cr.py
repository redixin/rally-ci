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
import cgi
import re
import logging

import json

from rallyci import utils
from rallyci.job import Job

LOG = logging.getLogger(__name__)


class CR:
    def __init__(self, config, event):
        """Represent Change Request

        :param config: Config instance
        :param event: dict decoded from gerrit event json
        """

        self.config = config
        self.event = event
        self.jobs = []

        self.id = utils.get_rnd_name(prefix="", length=10)

        event_type = event["type"]
        LOG.debug("New event %s" % event_type)
        if event_type == "ref-updated":
            LOG.debug("Ref updated.")
            #TODO
            return

        project_name = self.event["change"]["project"]
        self.project = self.config.data["projects"].get(project_name)

        if not self.project:
            LOG.debug("Unknown project %s" % project_name)
            return

        if event_type == "patchset-created":
            LOG.debug("Patchset created for project %s" % self.project)
            self.prepare_jobs()
            return

        if event_type == "comment-added":
            regexp = self.config.data.get("recheck", {}).get("regexp")
            if not regexp:
                return
            LOG.debug("Matching comment with pattern '%s'" % regexp)
            m = re.search(regexp, event["comment"], re.MULTILINE)
            if m:
                LOG.info("Recheck requested.")
                self.prepare_jobs()
            else:
                LOG.debug("Ignoring comment '%s'" % event["comment"])
        LOG.debug("Unknown event-type %s" % event_type)

    def to_dict(self):
        data = {"id": self.id, "jobs": [j.to_dict() for j in self.jobs]}
        subject = self.event.get("change", {}).get("subject", "")
        project = self.event.get("change", {}).get("project", "")
        data["subject"] = cgi.escape(subject)
        data["project"] = cgi.escape(project)
        return data

    def job_finished_callback(self, job):
        LOG.debug("Completed job: %r" % job)

    def _prepare_job(self, job_name, voting=True):
        cfg = self.config.data["jobs"][job_name]
        LOG.debug("Preparing job %s" % job_name)
        job = Job(self, job_name, cfg, self.event)
        job.voting = voting
        LOG.debug("Prepared job %r" % job)
        self.jobs.append(job)

    def prepare_jobs(self):
        for job_name in self.project.get("jobs", []):
            self._prepare_job(job_name, voting=True)
        for job_name in self.project.get("non-voting-jobs", []):
            self._prepare_job(job_name, voting=False)
        LOG.debug("Prepared jobs: %r" % self.jobs)

    @asyncio.coroutine
    def run(self):
        futures = []
        coroutines = []
        for job in self.jobs:
            future = asyncio.async(job.run(), loop=self.config.root.loop)
            job.future = future
            future.add_done_callback(self.job_finished_callback)
            futures.append(future)
        results = yield from asyncio.gather(*futures, return_exceptions=True)
        publisher_cfg = self.config.data.get("publisher")
        if publisher_cfg:
            publisher = self.config.init_obj(publisher_cfg)
            publisher.publish(self)
        return results
