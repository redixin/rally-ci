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
import time
import os.path
import string

from rallyci import utils

import logging
LOG = logging.getLogger(__name__)

SAFE_CHARS = string.ascii_letters + string.digits + "_"
INTERVALS = [1, 60, 3600, 86400]
NAMES = [('s', 's'),
         ('m', 'm'),
         ('h', 'h'),
         ('day', 'days')]


def _get_valid_filename(name):
    name = name.replace(" ", "_")
    return "".join([c for c in name if c in SAFE_CHARS])


class Job:
    def __init__(self, event, name):
        self.voting = True
        self.error = 254 # FIXME
        self.queued_at = time.time()
        self.event = event
        self.name = name
        self.root = event.root
        self.config = event.root.config.data["job"][name]
        self.id = utils.get_rnd_name(prefix="", length=10)
        self.stream_number = 0
        self.env = {}
        self.log_path = os.path.join(self.event.id, self.id)
        self.loggers = []
        for logger in self.root.config.get_instances("logger"):
            logger.job = self
            self.loggers.append(logger)
        self.status = "queued"
        LOG.debug("Job %s initialized." % self.id)

    def logger(self, data):
        """Process script stdout+stderr."""
        for logger in self.loggers:
            logger.log(self.current_stream, data)

    def set_status(self, status):
        self.stream_number += 1
        self.current_stream = "%02d-%s.txt" % (self.stream_number,
                                               _get_valid_filename(status))
        self.status = status
        self.root.job_updated(self)

    @asyncio.coroutine
    def run(self):
        try:
            self.started_at = time.time()
            yield from self._run()
        except Exception:
            LOG.exception("Error running job %s" % self.id)
            self.error = 254
        finally:
            self.finished_at = time.time()

    @asyncio.coroutine
    def _run(self):
        self.set_status("queued")
        for env_conf in self.config.get("envs", []):
            env = self.root.config.get_instance("env", env_conf["name"])
            env.setup(**env_conf)
            env.build(self)
            LOG.debug("New env: %s" % self.env)
        self.runner = self.root.config.\
            get_class_with_local("runner", self.config["runner"])
        LOG.debug("Runner initialized %r for job %r" % (self.runner, self))
        try:
            self.error = yield from self.runner.run(self)
        except:
            LOG.exception("Unhandled exception in job %s" % self)
            self.error = 1
        self.finished_at = int(time.time())
        LOG.debug("Finished job %s." % self)
        LOG.debug("Starting cleanup for job %s" % self)
        yield from self.runner.cleanup()
        LOG.debug("Finished cleanup for job %s" % self)

    def to_dict(self):
        return {"id": self.id,
                "name": self.name,
                "status": self.status,
                "seconds": int(time.time()) - self.queued_at,
                }
