
import os.path
import threading
import re
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
        self.runner_modules = {}
        self.config = config
        self.handlers = {
                "patchset-created": self._handle_patchset_created,
                "change-merged": self._handle_change_merged,
                "comment-added": self._handle_comment_added,
        }
        self.recheck_regexp = self.config.glob.get("recheck-regexp")

        stream_module = importlib.import_module(config.stream["module"])
        self.stream = stream_module.Stream(config.stream)

        if self.recheck_regexp:
            self.recheck_regexp = re.compile(self.recheck_regexp, re.MULTILINE)

        for runner_name, runner_conf in self.config.runners.items():
            module = runner_conf["module"]
            self.runner_modules[module] = importlib.import_module(module)

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
        if not self.recheck_regexp:
            return
        m = self.recheck_regexp.search(event["comment"])
        if m:
            LOG.debug("Recheck requested")
            return self.enqueue_job(event)

    def loop(self):
        handler = Handler(self.queue)
        thread = threading.Thread(target=handler.run)
        thread.start()
        try:
            for event in self.stream.generate():
                handler = self.handlers.get(event["type"])
                if handler:
                    handler(event)
                else:
                    LOG.debug("Unknown event: %s" % event["type"])
        except KeyboardInterrupt:
            LOG.info("Interrupted.")
        except:
            LOG.error("Exception during stream handling.", exc_info=True)
        LOG.info("Stream finished. Finalizing queue.")
        self.queue.put(None)
        self.queue.join()
        thread.join()
        LOG.info("All done. Exiting loop")
