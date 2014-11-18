
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

    def run(self):
        while True:
            LOG.debug("Getting CR from queue")
            try:
                cr = self.queue.get(timeout=1)
            except Queue.Empty:
                self.join_threads()

            LOG.debug("Got CR")

            if cr is None:
                LOG.info("No more CRs in queue. Exiting.")
                self.queue.task_done()
                break

            cid = cr.event["change"]["id"]
            if cid in self.threads:
                LOG.info("Task for CI %s is already running." % cid)
                self.queue.task_done()
                continue

            t = threading.Thread(target=cr.run_jobs)
            self.threads[cid] = t
            t.start()
            self.queue.task_done()
        LOG.debug("Joining remainig threads.")
        self.join_threads(block=True)
        LOG.debug("No more threads.")
