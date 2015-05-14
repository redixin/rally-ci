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
import copy
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
        self.stream_number = 0

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
        self.stream_number += 1
        self.current_stream = "%02d-%s.txt" % (self.stream_number, _get_valid_filename(status))
        self.status = status
        self.cr.config.root.handle_job_status(self)

    @asyncio.coroutine
    def run(self):
        LOG.debug("Started job %s" % self)
        try:
            self.set_status("env building")
            for env in self.envs:
                env.build(self)
            LOG.debug("Built env: %s" % self.env)
            self.runner = self.cr.config.init_obj_with_local("runners", self.cfg["runner"])
            self.runner.job = self
            LOG.debug("Runner initialized %r" % self.runner)
            future = asyncio.async(self.runner.run(), loop=asyncio.get_event_loop())
            future.add_done_callback(self.cleanup)
            result = yield from asyncio.wait_for(future, None)
            return result
        except Exception:
            LOG.exception("Unhandled exception in job %s" % self.name)
            return 254

    def cleanup(self, future):
        f = asyncio.async(self.runner.cleanup(), loop=self.cr.config.root.loop)
        self.cr.config.root.cleanup_tasks.append(f)
        f.add_done_callback(self.cr.config.root.cleanup_tasks.remove)
