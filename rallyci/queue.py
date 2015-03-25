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

import threading
import logging
import Queue

LOG = logging.getLogger(__name__)


class Handler(object):
    def __init__(self, queue):
        self.queue = queue
        self.threads = {}

    def join_threads(self, block=False):
        for cid, t in self.threads.items():
            if block or not t.is_alive():
                LOG.debug("Joining thread %r" % t)
                t.join()
                del(self.threads[cid])

    def run(self):
        threading.currentThread().setName("QueueManager")
        while True:
            try:
                cr = self.queue.get(timeout=4)
                LOG.debug("Got CR from queue")
            except Queue.Empty:
                self.join_threads()
            else:
                if cr is None:
                    LOG.info("No more CRs in queue. Exiting.")
                    self.queue.task_done()
                    LOG.debug("Joining remainig threads.")
                    self.join_threads(block=True)
                    LOG.debug("No more threads.")
                    return
                cid = "%s/%s" % (cr.event["change"]["id"],
                                 cr.event["patchSet"]["number"])
                if cid in self.threads:
                    LOG.info("Task for change %s already running." % cid)
                    self.queue.task_done()
                    continue
                LOG.debug("Starting jobs for %s" % cid)
                t = threading.Thread(target=cr.run_jobs)
                self.threads[cid] = t
                t.start()
                self.queue.task_done()
