
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
            try:
                LOG.debug("Getting CR from queue")
                cr = self.queue.get(timeout=1)
            except Queue.Empty:
                self.join_threads()


            if cr is None:
                LOG.info("No more CRs in queue. Exiting.")
                self.queue.task_done()
                break

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
        LOG.debug("Joining remainig threads.")
        self.join_threads(block=True)
        LOG.debug("No more threads.")
