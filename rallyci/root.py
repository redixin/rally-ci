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
import importlib
import logging
import yaml

from rallyci import cr

LOG = logging.getLogger(__name__)


class Config:
    def __init__(self, root, filename):
        self._modules = {}
        self.projects = {}
        self.root = root
        self.data = yaml.safe_load(open(filename, "rb"))
        self.stream = self.init_obj(self.data["stream"])
        sections = list(self.data.keys())
        sections.remove("stream")

        for section in sections:
            LOG.debug("Processing section '%s'" % section)
            setattr(self, section, {})
            for obj in self.data[section]:
                getattr(self, section)[obj["name"]] = obj

    def _get_module(self, name):
        """Get module by name.

        Import module if it is not imported.
        """
        module = self._modules.get(name)
        if not module:
            module = importlib.import_module(name)
            self._modules[name] = module
        return module

    def init_class_with_local(self, section, local):
        cfg = getattr(self, section)[local["name"]]
        return self._get_module(cfg["module"]).Class(self, cfg, local)

    def init_obj(self, cfg):
        return self._get_module(cfg["module"]).Class(self, cfg)

class Root:
    def __init__(self, loop):
        self.tasks = []
        self.loop = loop

    def load_config(self, filename):
        self.config = Config(self, filename)
        self.init_stream(self.config.stream)

    def task_done(self, task):
        LOG.debug("Completed task: %r" % task)

    def handle(self, event):
        task = cr.CR(self.config, event)
        if task.handler and task.project:
            self.tasks.append(task)
            future = asyncio.async(task.run())
            future.add_done_callback(self.task_done)

    def init_stream(self, stream):
        self.stream = stream
        self.stream_status = asyncio.Future()
        asyncio.async(self.stream.run(), loop=self.loop)
