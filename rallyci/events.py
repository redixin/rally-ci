
import threading
import subprocess
import re
import json

from project import Project

from log import logging
LOG = logging.getLogger(__name__)


class EventListener(object):
    """Listen for gerrit events.

    ssh -p 29418 USERNAME@review.openstack.org gerrit stream-events
    """

    def __init__(self, username, host, port, driver):
        self.username = username
        self.host = host
        self.port = port
        self.driver = driver
        self.drivers = {
                "ssh": self._stream_generator_ssh,
                "fake": self._stream_generator_fake,
        }
        self.projects = {}

    def _stream_generator_ssh(self):
        cmd = "ssh -p %d %s@%s gerrit stream-events" % (self.port,
                                                        self.username,
                                                        self.host)
        pipe = subprocess.Popen(cmd.split(" "),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        for line in iter(pipe.stdout.readline, b''):
            event = json.loads(line)
            yield(event)

    def _stream_generator_fake(self):
        with open("gerrit-sample-stream.json", "rb") as stream:
            for line in stream:
                yield json.loads(line)

    def events(self):
        return self.drivers[self.driver]()


class EventHandler(object):
    def __init__(self, config):
        self.threads = {}
        self.config = config
        self.listener = EventListener(**config.stream)
        self.handlers = {
                "patchset-created": self._handle_patchset_created,
                "comment-added": self._handle_comment_added,
        }
        self.recheck_regexp = self.config.glob.get("recheck-regexp")
        if self.recheck_regexp:
            self.recheck_regexp = re.compile(self.recheck_regexp, re.MULTILINE)

    def run_job(self, event):
        project_config = self.config.projects.get(event["change"]["project"])
        if project_config:
            project_name = project_config["name"]
            if project_name in self.threads:
                LOG.debug("Job for project %s is already running" % project_name)
            LOG.debug("Running jobs for patchset %s" % event["change"]["id"])
            project = Project(project_config, event, self.config)
            project.init_jobs()
            t = threading.Thread(target=project.run_jobs)
            t.start()
            self.threads[project_config["name"]] = t
            LOG.debug("Starting thread %r" % t)
        else:
            LOG.debug("Unknown project '%s'" % event["change"]["project"])

    def _handle_patchset_created(self, event):
        LOG.debug("Patchset created")
        return self.run_job(event)

    def _handle_comment_added(self, event):
        if not self.recheck_regexp:
            return
        m = self.recheck_regexp.search(event["comment"])
        if m:
            LOG.debug("Recheck requested")
            return self.run_job(event)

    def _join_threads(self):
        completed = []
        for project, t in self.threads.items():
            if not t.isAlive():
                t.join()
                completed.append(project)
        for project in completed:
            del(self.threads[project])

    def loop(self):
        for event in self.listener.events():
            self._join_threads()
            handler = self.handlers.get(event["type"])
            if handler:
                handler(event)
            else:
                LOG.debug("Unknown event: %s" % event["type"])
