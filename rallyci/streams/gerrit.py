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
import time
import subprocess
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


def get_key(raw_event):
    return raw_event["change"]["project"] + raw_event["patchSet"]["ref"]


class Event:
    def __init__(self, stream, project, raw_event):
        self.id = utils.get_rnd_name("EVNT", length=10)
        self.stream = stream
        self.root = stream.root
        self.raw_event = raw_event
        self.project = project
        self.jobs = {}
        self.jobs_list = []
        self.cfg = self.root.config.data["project"][self.project]
        env = self._get_env()
        if raw_event["type"] == "ref-updated":
            for job_name in self.cfg.get("on-ref-updated", []):
                job = Job(self, job_name)
                job.env.update(env)
                self.jobs_list.append(job)
            return
        for job_name in self.cfg.get("jobs", []):
            job = Job(self, job_name)
            job.env.update(env)
            self.jobs_list.append(job)
        for job_name in self.cfg.get("non-voting-jobs", []):
            job = Job(self, job_name)
            job.env.update(env)
            job.voting = False
            self.jobs_list.append(job)

    def _get_env(self):
        env = self.stream.cfg.get("env")
        r = {}
        if not env:
            return {}
        for k, v in env.items():
            value = dict(self.raw_event)
            try:
                for key in v.split("."):
                    value = value[key]
                r[k] = value
            except KeyError:
                pass
        return r

    @asyncio.coroutine
    def run_jobs(self):
        for job in self.jobs_list:
            future = asyncio.async(job.run(), loop=self.root.loop)
            self.jobs[future] = job
        while self.jobs:
            done, pending = yield from asyncio.\
                    wait(self.jobs.keys(), return_when=futures.FIRST_COMPLETED)
            for future in done:
                LOG.debug("Finished %s" % self.jobs[future])
                job = self.jobs[future]
                del(self.jobs[future])
                LOG.debug("getting ex")
                ex = future.exception()
                LOG.debug("got %s" % ex)
                if ex:
                    LOG.info("Failed %s with exception" % (job, future.exception()))
                    job.set_status("ERROR")
                del(job)
                LOG.debug("JOBS: %s" % self.jobs.keys())
        LOG.debug("Finished jobs fro task %s" % self)
        key = get_key(self.raw_event)
        self.stream.tasks.remove(key)
        if not self.stream.cfg.get("silent"):
            try:
                yield from self.publish_results()
            except:
                LOG.exception("Failed to publish results for task %s" % self)

    @asyncio.coroutine
    def publish_results(self):
        LOG.debug("Publishing results for task %s" % self)
        comment_header = self.stream.cfg.get("comment-header")
        if not comment_header:
            LOG.warning("No comment-header configured. Can't publish.")
            return
        cmd = ["gerrit", "review"]
        fail = any([j.error for j in self.jobs_list if j.voting])
        if self.stream.cfg.get("vote"):
            cmd.append("--verified=-1" if fail else "--verified=+1")
        succeeded = "failed" if fail else "succeeded"
        summary = comment_header.format(succeeded=succeeded)
        tpl = self.stream.cfg["comment-job-template"]
        for job in self.jobs_list:
            success = job.status + "" if job.voting else " (non-voting)"
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
        subject = self.raw_event.get("change", {}).get("subject", "#####")
        data["subject"] = cgi.escape(subject)
        data["project"] = cgi.escape(self.project)
        # TODO: remove hardcode
        if "patchSet" in self.raw_event:
            uri = self.raw_event["patchSet"]["ref"].split("/", 3)[-1]
            data["url"] = "https://review.openstack.org/#/c/%s" % uri
        else:
            data["url"] = "https://github.com/%s/commit/%s" % (
                    self.project, self.raw_event["refUpdate"]["newRev"])
        return data


class Class:

    def __init__(self, **kwargs):
        self.cfg = kwargs
        self.name = kwargs["name"]
        self.tasks = set()
        self.stop = False

    def start(self, root):
        self.root = root
        self.config = root.config
        fake_stream = self.cfg.get("fake-stream")
        if fake_stream:
            self.future = asyncio.async(self.run_fake(fake_stream),
                                                      loop=root.loop)
        else:
            if "port" not in self.cfg["ssh"]:
                self.cfg["ssh"]["port"] = 29418
            self.ssh = asyncssh.AsyncSSH(cb=self._handle_line, **self.cfg["ssh"])
            self.future = asyncio.async(self.run(), loop=root.loop)

    def stop(self):
        self.stop = True
        self.future.cancel()

    def _get_event(self, raw_event):

        project = raw_event.get("change", {}).get("project")
        if not project:
            project= raw_event.get("refUpdate", {}).get("project")
            if not project:
                LOG.debug("No project name %s" % raw_event)
                return

        if project not in self.config.data["project"]:
            return
        event_type = raw_event["type"]

        if event_type == "patchset-created":
            LOG.debug("Patchset for %s" % project)
            key = get_key(raw_event)
            if key in self.tasks:
                LOG.warning("Duplicate change %s" % key)
            else:
                LOG.debug("Key %s not found in %s" % (key, self.tasks))
                self.tasks.add(key)
                return Event(self, project, raw_event)

        if event_type == "comment-added":
            r = self.cfg.get("recheck-regexp", "^rally-ci recheck$")
            m = re.search(r, raw_event["comment"], re.MULTILINE)
            if m:
                LOG.debug("Recheck for %s" % project)
                key = get_key(raw_event)
                if key in self.tasks:
                    LOG.debug("Task is running already %s" % key)
                else:
                    LOG.debug("Key %s not found in %s" % (key, self.tasks))
                    self.tasks.add(key)
                    return Event(self, project, raw_event)

        if event_type == "ref-updated":
            return Event(self, project, raw_event)

    def _handle_line(self, line):
        if not (line and isinstance(line, bytes)):
            return
        line = line.decode()
        raw_event = json.loads(line)
        try:
            event = self._get_event(raw_event)
        except Exception:
            LOG.exception("Event processing error")
            return
        if event:
            self.root.handle(event)

    @asyncio.coroutine
    def run_fake(self, path):
        while 1:
            with open(path) as stream:
                for line in stream:
                    try:
                        self._handle_line(stream.readline())
                    except Exception:
                        LOG.exception("Error handlin string")
                    finally:
                        yield from asyncio.sleep(self.cfg.get("fake_stream_delay", 4))
            return

    @asyncio.coroutine
    def run(self):
        while 1:
            yield from self.ssh.run("gerrit stream-events",
                                    raise_on_error=False)
            if self.stop:
                return
            LOG.warning("Stream %s exited. Restarting" % self.name)
            asyncio.sleep(4)

    def start_client(self):
        cmd = "ssh -p %(port)d %(username)s@%(hostname)s gerrit stream-events" % \
              self.config["ssh"]
        self.pipe = subprocess.Popen(cmd.split(" "),
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)

    def generate(self):
        try:
            while True:
                for line in self._gen():
                    yield line
                time.sleep(10)
        finally:
            self.pipe.terminate()

    def _gen(self):
        self.start_client()
        with open(self.config.get("pidfile", PIDFILE), "w") as pidfile:
            pidfile.write(str(self.pipe.pid))
        for line in iter(self.pipe.stdout.readline, b''):
            if not line:
                break
            yield(json.loads(line))
