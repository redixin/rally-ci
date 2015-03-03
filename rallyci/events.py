
import os.path
import threading
import json
import Queue
import importlib

from rallyci.job import CR
from rallyci.queue import Handler

import logging
LOG = logging.getLogger(__name__)


class EventHandler(object):
    def __init__(self, config):
        self.queue = Queue.Queue()
        self.threads = {}
        self.config = config
        self.handlers = {
                "patchset-created": self._handle_patchset_created,
                "change-merged": self._handle_change_merged,
                "comment-added": self._handle_comment_added,
        }

    def enqueue_job(self, event):
        project_config = self.config.projects.get(event["change"]["project"])
        if project_config:
            cr = CR(project_config, self.config, event)
            LOG.info("Enqueue jobs (project %s)" % event["change"]["project"])
            self.queue.put(cr)
        else:
            LOG.debug("Unknown project '%s'" % event["change"]["project"])

    def _handle_patchset_created(self, event):
        self.enqueue_job(event)

    def _handle_change_merged(self, event):
        self.enqueue_job(event)

    def _handle_comment_added(self, event):
        m = self.config.recheck_regexp.search(event["comment"])
        if m:
            LOG.debug("Recheck requested")
            return self.enqueue_job(event)

    def loop(self):
        handler = Handler(self.queue)
        thread = threading.Thread(target=handler.run)
        thread.start()
        restart = True
        try:
            while True:
                if self.config.need_reload:
                    LOG.info("Reloading configuration.")
                    self.config.reload()
                    stream = self.config.stream.generate()
                event = stream.next()
                handler = self.handlers.get(event["type"])
                if handler:
                    handler(event)
                else:
                    LOG.debug("Unknown event: %s" % event["type"])
        except KeyboardInterrupt:
            LOG.info("Interrupted.")
        except StopIteration:
            pass
        except:
            LOG.error("Exception during stream handling.", exc_info=True)

        LOG.info("Stream finished. Finalizing queue.")
        self.queue.put(None)
        self.queue.join()
        thread.join()
        LOG.info("All done. Exiting loop")
