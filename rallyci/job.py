
import time
import threading
import os.path
import StringIO

import logging
LOG = logging.getLogger(__name__)

INTERVALS = [1, 60, 3600, 86400]
NAMES = [('s', 's'),
         ('m', 'm'),
         ('h', 'h'),
         ('day', 'days')]


class Job(object):

    def __init__(self, config, job_config, event, publishers, runner):
        self.envs = []
        self.env = {}
        self.config = config
        self.job_config = job_config
        self.event = event
        self.publishers = publishers
        self.errors = []
        self.error = True
        self.seconds = 0
        self.name = job_config["name"]
        self.runner = runner

    @property
    def human_time(self):
        result = []
        seconds = self.seconds
        for i in range(len(NAMES) - 1, -1, -1):
            a = seconds // INTERVALS[i]
            if a > 0:
                result.append((a, NAMES[i][1 % a]))
                seconds -= a * INTERVALS[i]
        return ' '.join(''.join(str(x) for x in r) for r in result)

    def prepare_environment(self, env_name):
        LOG.debug("Preparing env: %s" % env_name)
        env = self.config.get_env(env_name)
        env.build()
        self.env.update(env.env)
        self.envs.append(env)

    def run_script(self, script, event):
        LOG.debug("Running script %r" % script)
        cmd = script["interpreter"]
        for arg in script["args"]:
            value = dict(event)
            for key in arg.split('.'):
                value = value[key]
            cmd += " %s" % value
        path = script.get("path")
        if path:
            if path.startswith("~"):
                path = os.path.expanduser(path)
            stdin = open(path, "rb")
        else:
            stdin = StringIO.StringIO(script["data"])
        return self.runner.run(cmd, lambda x: x, stdin=stdin, env=self.env)

    def run(self):
        job_id = "%s-%s-%s" % (self.event["change"]["id"],
                               self.event["patchSet"]["number"],
                               self.name)
        threading.currentThread().setName(job_id)
        LOG.info("Started thread for job %s" % job_id)
        start = time.time()

        for env_name in self.job_config.get("environments", []):
            self.prepare_environment(env_name)

        for build_script in self.job_config.get("build-scripts", []):
            self.build_error = self.run_script(
                    self.config.scripts[build_script],
                    self.event)

        for test_cmd in self.job_config.get("test-commands", []):
            self.errors.append(self.runner.run(test_cmd, lambda x: x, env=self.env))

        self.runner.cleanup()
        self.seconds = int(time.time() - start)
        self.error = any(self.errors)

        for env in getattr(self, "envs", []):
            env.cleanup()


class CR(object):

    def __init__(self, project_config, config, event):
        self.project_config = project_config
        self.config = config
        self.event = event
        self.jobs = []
        self.run_id = "fake_unique_id"

    def run_jobs(self):
        threads = []
        change_full_id = "%s-%s" % (self.event["change"]["id"],
                                    self.event["patchSet"]["number"])
        threading.currentThread().setName(change_full_id)
        publishers = list(self.config.get_publishers(self.run_id, self.event))
        for job_config in self.project_config["jobs"]:
            runner = self.config.get_runner(job_config["runner"])
            runner.init(**job_config["runner-args"])
            job = Job(self.config, job_config, self.event, publishers, runner)
            self.jobs.append(job)
            t = threading.Thread(target=job.run)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        LOG.info("Completed jobs for %s" % self.event["change"]["id"])
        LOG.debug("Publishing in all publishers...")
        for p in publishers:
            LOG.debug("Publishing %r" % p)
            try:
                p.publish_summary(self.jobs)
            except Exception as e:
                LOG.warning("Publishing failed", exc_info=True)
        LOG.debug("Done with publishing")
