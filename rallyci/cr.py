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


LOG = logging.getLogger(__name__)

class Job:
    def __init__(self, cr, name, cfg, event):
        self.cr = cr
        self.name = name
        self.event = event
        self.envs = []
        self.loggers = []
        self.status = "queued"
        self.env = {}
        self.cfg = cfg
        self.id = utils.get_rnd_name(prefix="", length=10)
        self.current_stream = "__none__"

        for env in cfg.get("envs"):
            env = self.cr.config.init_obj_with_local("environments", env)
            self.envs.append(env)

        for name, cfg in self.cr.config.data.get("loggers", []).items():
            self.loggers.append(self.cr.config.get_class(cfg)(self, cfg))

    def to_dict(self):
        return {"id": self.id, "name": self.name, "status": self.status}

    def logger(self, data):
        """Process script stdout+stderr."""
        for logger in self.loggers:
            logger.log(self.current_stream, data)

    def set_status(self, status):
        self.status = status
        self.cr.config.root.handle_job_status(self)

    @asyncio.coroutine
    def run(self):
        LOG.debug("Started job %s" % self)
        self.set_status("env building")
        for env in self.envs:
            env.build(self)
        LOG.debug("Built env: %s" % self.env)
        runner = self.cr.config.init_obj_with_local("runners", self.cfg["runner"])
        LOG.debug("Runner initialized %r" % runner)
        self.current_stream = "build"
        self.set_status("building")
        status = yield from runner.build(self)
        if status:
            return status
        statuses = []
        for script_name in self.cfg["scripts"]:
            self.set_status("running %s" % script_name)
            script = self.cr.config.data["scripts"][script_name]
            self.current_stream = script_name
            status = yield from runner.run(script)
            statuses.append(status)
        task = asyncio.async(runner.cleanup(), loop=self.cr.config.root.loop)
        self.cr.config.root.cleanup_tasks.append(task)
        task.add_done_callback(self.cr.config.root.cleanup_tasks.remove)
        self.set_status("failed" if any(statuses) else "success")
        return any(statuses)


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
            m = re.search(regexp, event["comment"], re.MULTILINE)
            if m:
                LOG.info("Recheck requested.")
                self.prepare_jobs()
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

    def prepare_jobs(self):
        for job_name in self.project["jobs"]:
            cfg = self.config.data["jobs"][job_name]
            LOG.debug("Preparing job %s" % job_name)
            job = Job(self, job_name, cfg, self.event)
            LOG.debug("Prepared job %r" % job)
            self.jobs.append(job)
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
        return results
