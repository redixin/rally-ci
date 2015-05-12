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
from concurrent.futures import FIRST_COMPLETED
import os.path
import logging

from rallyci import base
from rallyci import utils

LOG = logging.getLogger(__name__)
BUILDING_IMAGES = {}


class Class(base.ClassWithLocal, base.GenericRunnerMixin):

    @asyncio.coroutine
    def build(self):
        self.ssh = yield from self.config.nodepools[self.cfg["nodepool"]].get_ssh(self.job)
        self.image = self.local["image"]
        self.images = []
        self.containers = []
        build_key = (self.ssh.hostname, self.image)
        BUILDING_IMAGES.setdefault(build_key, asyncio.Lock())
        with (yield from BUILDING_IMAGES[build_key]):
            self.job.set_status("building")
            filedir = yield from self.ssh.run("mktemp -d", return_output=True)
            dockerfile = self.cfg["images"][self.image]
            yield from self.ssh.run("tee %s/Dockerfile" % filedir,
                                    stdin=dockerfile)
            yield from self.ssh.run("docker build -t %s %s" % (self.image, filedir))

    @asyncio.coroutine
    def run_script(self, script):
        name = utils.get_rnd_name()
        LOG.debug("Starting script %s" % script)
        cmd = "docker run -i --name %s" % name
        for env in self.job.env.items():
            cmd += " -e %s=%s" % (env)
        cmd += " %s %s" % (self.image, script["interpreter"])
        result = yield from self.ssh.run(cmd, stdin=script["data"])
        self.image = yield from self.ssh.run("docker commit %s" % name, return_output=True)
        self.images.append(self.image)
        self.containers.append(name)
        return result

    @asyncio.coroutine
    def cleanup(self):
        LOG.info("Starting cleanup %s" % self.job.id)
        for container in self.containers:
            yield from self.ssh.run("docker rm %s" % container)
        for image in self.images[::-1]:
            yield from self.ssh.run("docker rmi %s" % image, raise_on_error=False)
        LOG.info("Cleanup %s completed" % self.job.id)
