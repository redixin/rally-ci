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
import json
import re
import time
import subprocess
import logging

from rallyci.common import asyncssh
from rallyci.job import Job
from rallyci import task
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


class Class:

    def __init__(self, root, **kwargs):
        self.root = root
        self.cfg = kwargs
        self.name = kwargs["name"]
        self.tasks = set()
        self.config = self.root.config

    def _get_task(self, event):
        project = event.get("change", {}).get("project")
        if not project:
            project= event.get("refUpdate", {}).get("project")
            if not project:
                LOG.debug("No project name %s" % event)
                return
        LOG.debug("Project: %s" % project)

        if project not in self.config.data["project"]:
            return
        event_type = event["type"]

        if event_type == "patchset-created":
            LOG.debug("Patchset for %s" % project)
            key = task.get_key(event)
            if key in self.tasks:
                LOG.warning("Duplicate change %s" % key)
            else:
                LOG.debug("Key %s not found in %s" % (key, self.tasks))
                self.tasks.add(key)
                return task.Task(self, project, event)

        if event_type == "comment-added":
            r = self.cfg.get("recheck-regexp", "^rally-ci recheck$")
            m = re.search(r, event["comment"], re.MULTILINE)
            if m:
                LOG.debug("Recheck for %s" % project)
                key = task.get_key(event)
                if key in self.tasks:
                    LOG.debug("Task is running already %s" % key)
                else:
                    LOG.debug("Key %s not found in %s" % (key, self.tasks))
                    self.tasks.add(key)
                    return task.Task(self, project, event)

        if event_type == "ref-updated":
            return task.Task(self, project, event)

    def _handle_line(self, line):
        LOG.debug("Handling line %s..." % line[:16])
        if not (line and isinstance(line, bytes)):
            LOG.warning("Bad line type %s" % type(line))
            return
        line = line.decode()
        event = json.loads(line)
        try:
            task = self._get_task(event)
            if task:
                self.root.handle(task)
        except Exception:
            LOG.exception("Event processing error")

    @asyncio.coroutine
    def cleanup(self):
        yield from asyncio.sleep(0)

    @asyncio.coroutine
    def run(self):
        fake_stream = self.cfg.get("fake-stream")
        if fake_stream:
            LOG.info("Entering fake_stream loop")
            while 1:
                with open(fake_stream, 'rb') as fs:
                    for line in fs:
                        yield from asyncio.sleep(2)
                        self._handle_line(line)
        else:
            if "port" not in self.cfg["ssh"]:
                self.cfg["ssh"]["port"] = 29418
            self.ssh = asyncssh.AsyncSSH(cb=self._handle_line, **self.cfg["ssh"])
            yield from self.ssh.run("gerrit stream-events", cb=self._handle_line)
