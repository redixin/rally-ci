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
import logging

LOG = logging.getLogger(__name__)


class Class:

    def __init__(self, config, cfg):
        """Constructor of generic RallyCI object

        :param config: Config object
        :param cfg: section from config file
        """
        self.config = config
        self.cfg = cfg


class ClassWithLocal:

    def __init__(self, config, cfg, local):
        """

        :param config: Config object
        :param cfg: section from config file
        :param local: local config
        """
        self.config = config
        self.cfg = cfg
        self.local = local


class GenericRunnerMixin:
    """Generic runner with build and run_script methods."""

    @asyncio.coroutine
    def run(self, job):
        self.job = job
        job.set_status("building")
        try:
            yield from self.build()
        except Exception:
            LOG.exception("Failed to build.")
            job.set_status("build failed")
            return True
        job.set_status("booting")
        try:
            yield from self.boot()
        except:
            LOG.exception("Failed to boot.")
            job.set_status("boot failed")
            return True
        for script_name in self.local["scripts"]:
            job.set_status("running %s" % script_name)
            script = self.config.data["scripts"][script_name]
            try:
                yield from self.run_script(script)
            except:
                LOG.exception("Failed to run %s" % script_name)
                job.set_status("failed %s" % script_name)
                return True
        job.set_status("success")
