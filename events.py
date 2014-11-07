
import subprocess
import json

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
    
    def run_script(self, driver, script, event, stdout):
        interpreter = script.get("interpreter")
        if interpreter:
            cmd = interpreter
            for arg in script["args"]:
                value = dict(event)
                for key in arg.split('.'):
                    value = value[key]
                cmd += " %s" % value
            driver.run(cmd, stdout, stdin=open(script["path"], "rb"))
        else:
            for cmd in script["commands"]:
                driver.run(cmd, stdout)

    def run_job(self, job, event, logger):
        driver = __import__(job["driver"]).Driver
        driver = driver(job["name"], *job["driver-args"])
        driver.build(logger.stdout(job, "build.txt.gz"))
        stdout = logger.stdout(job)
        for build_script in job.get("build-scripts", []):
            self.run_script(driver, self.config.scripts[build_script],
                            event, stdout)
        for test_cmd in job.get("test-commands", []):
            driver.run(test_cmd, stdout)
        driver.cleanup()
        return
        d = docker.Docker(job["name"], **job["deploy"]["args"])

    def process_project(self, project, event):
        logger = self.config.logs["driver"]
        logger = __import__(logger).Driver(self.config.logs)
        logger.mkdir(event)
        for job in project["jobs"]:
            self.run_job(job, event, logger)

    def _handle_patchset_created(self, event):
        LOG.debug("Patchset created")
        project = self.config.projects.get(event["change"]["project"])
        if project:
            LOG.debug("Handling patchset %s" % event["change"]["id"])
            self.process_project(project, event)
        else:
            LOG.debug("Unknown project '%s'" % event["change"]["project"])

    def loop(self):
        for event in self.listener.events():
            handler = self.handlers.get(event["type"])
            if handler:
                handler(event)
            else:
                LOG.debug("Unknown event: %s" % event["type"])
