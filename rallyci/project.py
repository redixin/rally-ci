
import time
import threading
import os.path
import StringIO

import logging
LOG = logging.getLogger(__name__)

INTERVALS = [1, 60, 3600, 86400]
NAMES = [('s', 's'),
         ('m', 'm'),
         ('h',   'h'),
         ('day',    'days')]


class Job(object):

    def __init__(self, config, event, project_config, publisher, driver):
        self.config = config
        self.event = event
        self.project_config = project_config
        self.publisher = publisher
        self.errors = []
        self.error = True
        self.seconds = 0
        self.name = config["name"]
        self.driver = driver
        stdout = publisher.stdout(config, "build.txt.gz")
        self.driver.build(stdout)

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
            path = script.get("path")
            if path:
                if path.startswith("~"):
                    path = os.path.expanduser(path)
                    stdin=open(path, "rb")
            else:
                stdin = StringIO.StringIO(script["data"])
            return self.driver.run(cmd, stdout, stdin=stdin)
        else:
            for cmd in script["commands"]:
                return self.driver.run(cmd, stdout)

    def run(self):
        job_id = "%s-%s-%s" % (self.event["change"]["id"],
                               self.event["patchSet"]["number"],
                               self.name)
        threading.currentThread().setName(job_id)
        LOG.info("Started thread for job %s" % job_id)
        start = time.time()
        stdout = self.publisher.stdout(self.config)
        for build_script in self.config.get("build-scripts", []):
            self.build_error = self.run_script(
                    self.project_config.scripts[build_script],
                    self.event, stdout)
        for test_cmd in self.config.get("test-commands", []):
            self.errors.append(self.driver.run(test_cmd, stdout))
        self.driver.cleanup()
        self.seconds = int(time.time() - start)
        self.error = any(self.errors)


class CR(object):

    def __init__(self, project, event, config, drivers):
        self.drivers = drivers
        self.project = project
        self.event = event
        self.config = config
        self.jobs = []

    def run_jobs(self):
        threads = []
        change_full_id = "%s-%s" % (self.event["change"]["id"],
                                    self.event["patchSet"]["number"])
        threading.currentThread().setName(change_full_id)
        publisher = self.config.get_publisher(self.event)
        for job_config in self.project["jobs"]:

            driver_conf = self.config.drivers[job_config["driver"]]
            driver_class = self.drivers[driver_conf["driver"]].Driver
            driver = driver_class(**driver_conf)

            driver.setup(**job_config["driver-args"])
            job = Job(job_config, self.event, self.config, publisher, driver)
            self.jobs.append(job)
            t = threading.Thread(target=job.run)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        LOG.info("Completed jobs for %s" % self.event["change"]["id"])
        publisher.publish_summary(self.jobs)
