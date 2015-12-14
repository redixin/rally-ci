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
import functools
import re
import json

from rallyci.common.ssh import SSH
from rallyci import base
from rallyci import utils
from rallyci import task


EVENT_TYPES = {
    "patchset-created": "patchset-created",
    "ref-updated": "change-merged",
}

class Event(base.BaseEvent):

    def __init__(self, cfg, raw_event):
        """
        :param cfg: service config section
        """
        self.raw_event = raw_event
        self.env = _get_env(raw_event, cfg.get("env", {}))
        self.project = _get_project_name(raw_event)
        self.event_type = EVENT_TYPES.get(raw_event["type"], "unknown")
        if "patchSet" in raw_event:
            template = cfg.get("cr-url-template", "")
            self.cr = raw_event["change"]["id"]
            self.commit = raw_event["patchSet"]["revision"]
        else:
            template = cfg.get("merged-url-template", "")
            self.commit = raw_event["refUpdate"]["newRev"]
            self.cr = ""
        self.url = template.format(commit=self.commit, project=self.project)
        cfg_url = cfg.get("cfg-url-template", "")
        self.cfg_url = cfg_url.format(commit=self.commit, project=self.project)
        self.key = self.project + self.commit
        self.subject = raw_event.get("change", {}).get("subject", "*****")


class Service:
    data = ""
    tasks = {}

    def __init__(self, root, **kwargs):
        self.root = root
        self.log = root.log
        self.loop = root.loop
        self.cfg = kwargs
        self.handler_map = {
            "comment-added": self._handle_comment_added,
            "patchset-created": self._start_task,
            "ref-updated": self._start_task,
        }

    def _start_task(self, raw_event):
        event = Event(self.cfg, raw_event)
        self.root.start_task(task.Task(self.root, event))

    def _handle_comment_added(self, raw_event):
        r = self.cfg.get("recheck-regexp", "^rally-ci recheck$")
        m = re.search(r, raw_event["comment"], re.MULTILINE)
        if m:
            self.log.info("Recheck for %s" % _get_project_name(raw_event))
            self._start_task(raw_event)

    def _handle_event(self, event):
        event = json.loads(event)
        project = _get_project_name(event)
        self.log.debug("Event '%s' for project '%s'" % (event["type"],
                                                        project))
        if project:
            if not self.root.config.is_project_configured(project):
                return
            handler = self.handler_map.get(event["type"])
            if handler:
                handler(event)
            else:
                self.log.warning("Unknown event type %s" % event["type"])
        else:
            self.log.warning("No project name")

    def _handle_stderr(self, data):
        self.log.warning("Error message from gerrit: %s" % data)

    def _handle_stdout(self, data):
        self.data += data
        while "\n" in self.data:
            line, self.data = self.data.split("\n", 1)
            try:
                self._handle_event(line)
            except:
                self.log.exception("Error handling data %s" % self.data)

    @asyncio.coroutine
    def run(self):
        fake_stream = self.cfg.get("fake-stream")
        if fake_stream:
            while True:
                with open(fake_stream) as fs:
                    for line in fs:
                        self._handle_stdout(line)
                        yield from asyncio.sleep(3)
                self.log.info("Stream ended. Starting from beginning.")
            return
        if "port" not in self.cfg["ssh"]:
            self.cfg["ssh"]["port"] = 29418

        self.cfg["ssh"]["keys"] = self.root.config.get_ssh_keys(keytype="private")
        self.ssh = SSH(self.loop, **self.cfg["ssh"])
        self.root.task_end_handlers.append(self._handle_task_end)
        reconnect_delay = self.cfg.get("reconnect_delay", 5)
        while True:
            try:
                status = yield from self.ssh.run("gerrit stream-events",
                                                 stdout=self._handle_stdout,
                                                 stderr=self._handle_stderr)
                self.log.info("Gerrit stream was closed with status %s" % status)
            except asyncio.CancelledError:
                self.log.info("Stopping gerrit")
                self.root.task_end_handlers.remove(self._handle_task_end)
                del self.ssh
                return
            except:
                self.log.exception("Error listening gerrit events")
            self.log.info("Reconnect in %s seconds" % reconnect_delay)
            yield from asyncio.sleep(reconnect_delay)

    def _handle_task_end(self, task):
        return
        self.root.start_coro(self.publish_results(task))

    @asyncio.coroutine
    def publish_results(self, task):
        if self.cfg.get("silent"):
            yield from asyncio.sleep(0)
            return
        self.log.debug("Publishing results for task %s" % self)
        comment_header = self.cfg.get("comment-header")
        if not comment_header:
            self.log.warning("No comment-header configured. Can't publish.")
            return
        cmd = ["gerrit", "review"]
        fail = any([j.error for j in task.jobs if j.voting])
        if self.cfg.get("vote"):
            cmd.append("--verified=-1" if fail else "--verified=+1")
        succeeded = "failed" if fail else "succeeded"
        summary = comment_header.format(succeeded=succeeded)
        tpl = self.cfg["comment-job-template"]
        for job in self.jobs_list:
            success = job.status + ("" if job.voting else " (non-voting)")
            time = utils.human_time(job.finished_at - job.started_at)
            summary += tpl.format(success=success,
                                  name=job.config["name"],
                                  time=time,
                                  log_path=job.log_path)
            summary += "\n"
        cmd += ["-m", '"%s"' % summary, self.event["patchSet"]["revision"]]
        yield from self.ssh.run(cmd)


def _get_project_name(e):
    return e.get("change", {}).get("project",
                                   e.get("refUpdate", {}).get("project"))

def _get_env(event, cfg):
    """Get event environment.

    :param dict cfg: service.env section
    :param dict event:
    """
    env = {}
    for k, v in cfg.items():
        value = dict(event)
        try:
            for key in v.split("."):
                value = value[key]
            env[k] = value
        except KeyError:
            pass
    return env
