
import subprocess
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
        self.config = config
        self.listener = EventListener(**config.stream)
        self.handlers = {
                "patchset-created": self._handle_patchset_created,
        }

    def _handle_patchset_created(self, event):
        LOG.debug("Patchset created")
        project_config = self.config.projects.get(event["change"]["project"])
        if project_config:
            LOG.debug("Handling patchset %s" % event["change"]["id"])
            project = Project(project_config, event, self.config)
            project.run_jobs()
        else:
            LOG.debug("Unknown project '%s'" % event["change"]["project"])

    def loop(self):
        for event in self.listener.events():
            handler = self.handlers.get(event["type"])
            if handler:
                handler(event)
            else:
                LOG.debug("Unknown event: %s" % event["type"])
