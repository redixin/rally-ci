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
import json
import re
import logging

from rallyci.common import asyncssh
from rallyci.job import Job
from rallyci import utils

LOG = logging.getLogger(__name__)

INTERVALS = [1, 60, 3600, 86400]
NAMES = [('s', 's'),
         ('m', 'm'),
         ('h', 'h'),
         ('day', 'days')]

"""
{
    'type': 'ref-updated',
    'refUpdate': {
        'newRev': '1a8c2369ed141a50ac5c109c53cf5fde68375afc',
        'refName': 'master',
        'oldRev': '0fc633318d0103e81af00840679661d3df0534aa',
        'project': 'stackforge/stackalytics'
    }
}
"""


def human_time(seconds):
    seconds = int(seconds)
    result = []
    for i in range(len(NAMES) - 1, -1, -1):
        a = seconds // INTERVALS[i]
        if a > 0:
            result.append((a, NAMES[i][1 % a]))
            seconds -= a * INTERVALS[i]
    return ' '.join(''.join(str(x) for x in r) for r in result)


class Event:
    def __init__(self, stream, raw_event):
        self.id = utils.get_rnd_name(prefix="", length=10)
        self.stream = stream
        self.root = stream.root
        self.raw_event = raw_event
        self.project_name = self.get_project_name(raw_event)
        self.jobs = {}
        self.jobs_list = []
        self.cfg = self.root.config.data["project"][self.project_name]
        for job_name in self.cfg["jobs"]:
            self.jobs_list.append(Job(self, job_name))
        for job_name in self.cfg["non-voting-jobs"]:
            job = Job(self, job_name)
            job.voting = False
            self.jobs_list.append(job)

    @asyncio.coroutine
    def run_jobs(self):
        for job in self.jobs_list:
            future = asyncio.async(job.run(), loop=self.root.loop)
            job.future = future  # FIXME: this used by nodepool
            self.jobs[future] = job
        while self.jobs:
            done, pending = yield from asyncio.\
                    wait(self.jobs.keys(), return_when=futures.FIRST_COMPLETED)
            for future in done:
                LOG.debug("Finished job %s" % self.jobs[future])
                del(self.jobs[future])
        yield from self.publish_results()

    def get_project_name(self, raw_event):
        return raw_event["change"]["project"]

    @asyncio.coroutine
    def publish_results(self):
        comment_header = self.stream.cfg.get("comment-header")
        if not comment_header:
            return
        cmd = ["gerrit", "review"]
        fail = any([j.error for j in self.jobs_list if j.voting])
        if self.stream.cfg.get("vote"):
            cmd.append("--verified=-1" if fail else "--verified=+1")
        succeeded = "failed" if fail else "succeeded"
        summary = comment_header.format(succeeded=succeeded)
        tpl = self.stream.cfg["comment-job-template"]
        for job in self.jobs_list:
            success = "FAILURE" if job.error else "SUCCESS"
            success += "" if job.voting else " (non-voting)"
            time = human_time(job.finished_at - job.started_at)
            summary += tpl.format(success=success,
                                  name=job.config["name"],
                                  time=time,
                                  log_path=job.log_path)
            summary += "\n"
        cmd += ["-m", "'%s'" % summary, self.raw_event["patchSet"]["revision"]]
        yield from asyncssh.AsyncSSH(**self.stream.cfg["ssh"]).run(cmd)

    def to_dict(self):
        data = {"id": self.id, "jobs": [j.to_dict() for j in self.jobs_list]}
        subject = self.raw_event.get("change", {}).get("subject", "")
        project = self.project_name
        data["subject"] = cgi.escape(subject)
        data["project"] = cgi.escape(project)
        uri = self.raw_event["patchSet"]["ref"].split("/", 3)[-1]
        # TODO: remove hardcode
        data["url"] = "https://review.openstack.org/%s" % uri
        return data


class Class:

    def __init__(self, **kwargs):
        self.cfg = kwargs
        self.name = kwargs["name"]
        if "port" not in kwargs["ssh"]:
            kwargs["ssh"]["port"] = 29418
        self.ssh = asyncssh.AsyncSSH(cb=self._handle_line, **kwargs["ssh"])

    def start(self, root):
        self.root = root
        self.config = root.config
        self.future = asyncio.async(self.run(), loop=root.loop)

    def stop(self):
        self.future.cancel()

    def _get_event(self, raw_event):
        project_name = raw_event.get("change", {}).get("project")
        if not project_name:
            LOG.debug("No project name %s" % raw_event)
            return
        if project_name not in self.config.data["project"]:
            LOG.debug("Unknown project %s" % project_name)
            return
        event_type = raw_event["type"]
        if event_type == "patchset-created":
            LOG.debug("Patchset for project %s" % project_name)
            return Event(self, raw_event)
        if event_type == "comment-added":
            r = self.cfg.get("recheck-regexp", "^rally-ci recheck$")
            m = re.search(r, raw_event["comment"], re.MULTILINE)
            if m:
                LOG.debug("Recheck for project %s" % project_name)
                return Event(self, raw_event)

    def _handle_line(self, line):
        try:
            if isinstance(line, bytes):
                line = line.decode()
            raw_event = json.loads(line)
        except Exception:
            LOG.exception("Unable to decode string: %s" % line)
            return
        try:
            event = self._get_event(raw_event)
        except Exception:
            LOG.exception("Event processing error")
            return
        if event:
            self.root.handle(event)

    @asyncio.coroutine
    def run(self):
        while 1:
            yield from self.ssh.run("gerrit stream-events",
                                    raise_on_error=False)
            LOG.warning("Stream %s exited. Restarting" % self.name)
            asyncio.sleep(4)
