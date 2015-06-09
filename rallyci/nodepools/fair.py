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
import logging

from rallyci.common import asyncssh


LOG = logging.getLogger(__name__)


class Class:
    def __init__(self, **kwargs):
        self.cfg = kwargs
        self.tasks_per_node = kwargs["tasks_per_node"]
        self.futures = dict([(tuple(c.items()), []) for c in kwargs["nodes"]])
        self.nodes = {}

    def job_done_callback(self, future):
        node = self.nodes.pop(future)
        self.futures[node].remove(future)
        LOG.debug("Deleted future %s from node %s" % (future, node))

    @asyncio.coroutine
    def get_ssh(self, job):
        while True:
            node, tasks = min(self.futures.items(), key=lambda x: len(x[1]))
            if len(tasks) < self.tasks_per_node:
                self.nodes[job.future] = node
                self.futures[node].append(job.future)
                job.future.add_done_callback(self.job_done_callback)
                LOG.debug("New busy node %s" % str(node))
                return asyncssh.AsyncSSH(cb=job.logger, **dict(node))
            LOG.debug("No nodes available. Waiting for any node to release.")
            yield from asyncio.wait(list(self.nodes.keys()),
                                    return_when=FIRST_COMPLETED)
