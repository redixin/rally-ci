
import time
import threading
import importlib

import logging
LOG = logging.getLogger(__name__)

INTERVALS = [1, 60, 3600, 86400]
NAMES = [('s', 's'),
         ('m', 'm'),
         ('h',   'h'),
         ('day',    'days')]


class Job(object):

    def __init__(self, job, event, config, logger):
        self.job = job
        self.event = event
        self.config = config
        self.logger = logger
        self.errors = []
        self.name = job["name"]
        driver_conf = config.drivers[job["driver"]]
        driver = importlib.import_module(driver_conf["driver"]).Driver
        self.driver = driver(driver_conf, job["name"], *job["driver-args"])
        self.driver.build(logger.stdout(job, "build.txt.gz"))

    @property
    def human_time(self):
        result = []
        seconds = self.seconds
        for i in range(len(NAMES)-1, -1, -1):
            a = seconds // INTERVALS[i]
            if a > 0:
                result.append( (a, NAMES[i][1 % a]) )
                seconds -= a * INTERVALS[i]
        return ' '.join(''.join(str(x) for x in r) for r in result)

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
        start = time.time()
        stdout = self.logger.stdout(self.job)
        for build_script in self.job.get("build-scripts", []):
            self.build_error = self.run_script(
                    self.config.scripts[build_script], self.event, stdout)
        for test_cmd in self.job.get("test-commands", []):
            self.errors.append(self.driver.run(test_cmd, stdout))
        self.driver.cleanup()
        self.seconds = int(time.time() - start)
        self.error = any(self.errors)


class Project(object):

    def __init__(self, project, event, config):
        self.project = project
        self.event = event
        self.config = config
        self.jobs = []
        logger = self.config.logs["driver"]
        self.logger = importlib.import_module(logger).Driver(self.config.logs, self.event)

    def init_jobs(self):
        for job_config in self.project["jobs"]:
            LOG.debug("Initializing job: %s (Project: %s)" % (job_config["name"], self.project["name"]))
            job = Job(job_config, self.event, self.config, self.logger)
            self.jobs.append(job)

    def run_jobs(self):
        threads = []
        for job in self.jobs:
            LOG.debug("Running job: %s (Project: %s)" % (job.name, self.project["name"]))
            t = threading.Thread(target=job.run)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        self.logger.publish_summary(self.jobs)
