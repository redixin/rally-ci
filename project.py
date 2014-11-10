
from log import logging
LOG = logging.getLogger(__name__)


class Job(object):

    def __init__(self, job, event, config, logger):
        self.job = job
        self.event = event
        self.config = config
        self.logger = logger

        driver = __import__(job["driver"]).Driver
        self.driver = driver(job["name"], *job["driver-args"])
        self.driver.build(logger.stdout(job, "build.txt.gz"))

    def run_script(self, script, event, stdout):
        interpreter = script.get("interpreter")
        if interpreter:
            cmd = interpreter
            for arg in script["args"]:
                value = dict(event)
                for key in arg.split('.'):
                    value = value[key]
                cmd += " %s" % value
            self.driver.run(cmd, stdout, stdin=open(script["path"], "rb"))
        else:
            for cmd in script["commands"]:
                self.driver.run(cmd, stdout)

    def run(self):

        stdout = self.logger.stdout(self.job)
        for build_script in self.job.get("build-scripts", []):
            self.run_script(self.config.scripts[build_script], self.event, stdout)
        for test_cmd in self.job.get("test-commands", []):
            self.driver.run(test_cmd, stdout)
        self.driver.cleanup()


class Project(object):

    def __init__(self, project, event, config):
        self.project = project
        self.event = event
        self.config = config
        logger = self.config.logs["driver"]
        self.logger = __import__(logger).Driver(self.config.logs)
        self.logger.mkdir(self.event)

    def run_jobs(self):
        for job_config in self.project["jobs"]:
            job = Job(job_config, self.event, self.config, self.logger)
            job.run()
