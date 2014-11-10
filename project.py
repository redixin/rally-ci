
from log import logging
LOG = logging.getLogger(__name__)


class Job(object):

    def __init__(self, job, event, config, logger):
        self.job = job
        self.event = event
        self.config = config
        self.logger = logger
        self.errors = []
        self.name = job["name"]

        print config.drivers
        print job["driver"]
        driver_conf = config.drivers[job["driver"]]
        driver = __import__(driver_conf["driver"]).Driver
        self.driver = driver(driver_conf, job["name"], *job["driver-args"])
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
            return self.driver.run(cmd, stdout, stdin=open(script["path"], "rb"))
        else:
            for cmd in script["commands"]:
                return self.driver.run(cmd, stdout)

    def run(self):

        stdout = self.logger.stdout(self.job)
        for build_script in self.job.get("build-scripts", []):
            self.build_error = self.run_script(
                    self.config.scripts[build_script], self.event, stdout)
        for test_cmd in self.job.get("test-commands", []):
            self.errors.append(self.driver.run(test_cmd, stdout))
        self.driver.cleanup()
        self.error = any(self.errors)


class Project(object):

    def __init__(self, project, event, config):
        self.project = project
        self.event = event
        self.config = config
        self.jobs = []
        logger = self.config.logs["driver"]
        self.logger = __import__(logger).Driver(self.config.logs, self.event)

    def run_jobs(self):
        for job_config in self.project["jobs"]:
            job = Job(job_config, self.event, self.config, self.logger)
            LOG.debug("Running job: %s (Project: %s)" % (job.name, self.project["name"]))
            job.run()
            self.jobs.append(job)
        self.logger.publish_summary(self.jobs)
