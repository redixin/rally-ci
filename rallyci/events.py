
import os.path
import threading
import subprocess
import re
import json
import Queue
import importlib

from rallyci.project import CR
from rallyci.queue import Handler

import logging
LOG = logging.getLogger(__name__)


class EventListener(object):
    """Listen for gerrit events.

    ssh -p 29418 USERNAME@review.openstack.org gerrit stream-events
    """

    def __init__(self, driver, **kwargs):
        self.driver = driver
        self.config = kwargs
        self.drivers = {
                "ssh": self._stream_generator_ssh,
                "fake": self._stream_generator_fake,
        }
        self.projects = {}

    def _stream_generator_ssh(self, host, username, port=22, **kwargs):
        cmd = "ssh -p %d %s@%s gerrit stream-events" % (port,
                                                        username,
                                                        host)
        pipe = subprocess.Popen(cmd.split(" "),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        for line in iter(pipe.stdout.readline, b''):
            event = json.loads(line)
            yield(event)

    def _stream_generator_fake(self, fake_stream_path, **kwargs):
        if fake_stream_path.startswith("~"):
            fake_stream_path = os.path.expanduser(fake_stream_path)
        with open(fake_stream_path, "rb") as stream:
            for line in stream:
                yield json.loads(line)

    def events(self):
        return self.drivers[self.driver](**self.config)


class EventHandler(object):
    def __init__(self, config):
        self.queue = Queue.Queue()
        self.threads = {}
        self.drivers = {}
        self.config = config
        self.listener = EventListener(**config.stream)
        self.handlers = {
                "patchset-created": self._handle_patchset_created,
                "comment-added": self._handle_comment_added,
        }
        self.recheck_regexp = self.config.glob.get("recheck-regexp")
        if self.recheck_regexp:
            self.recheck_regexp = re.compile(self.recheck_regexp, re.MULTILINE)
        for driver_name, driver_conf in self.config.drivers.items():
            driver = driver_conf["driver"]
            self.drivers[driver] = importlib.import_module(driver)

    def enqueue_job(self, event):
        project_config = self.config.projects.get(event["change"]["project"])
        if project_config:

            cr = CR(project_config, event, self.config, self.drivers)
            LOG.info("Enqueue jobs (project %s)" % event["change"]["project"])
            self.queue.put(cr)
        else:
            LOG.debug("Unknown project '%s'" % event["change"]["project"])

    def _handle_patchset_created(self, event):
        LOG.debug("Patchset created")
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
            for event in self.listener.events():
                handler = self.handlers.get(event["type"])
                if handler:
                    handler(event)
                else:
                    LOG.debug("Unknown event: %s" % event["type"])
        except KeyboardInterrupt:
            LOG.info("Exiting.")
        except:
            LOG.error("Exception during stream handling.", exc_info=True)
        LOG.info("Stream finished. Finalizing queue.")
        self.queue.put(None)
        self.queue.join()
        thread.join()
        LOG.info("All done. Exiting loop")
