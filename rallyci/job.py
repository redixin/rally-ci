# Copyright 2015: Mirantis Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import copy
import time
import threading
import os.path
import StringIO
import random
import string

import logging
LOG = logging.getLogger(__name__)

INTERVALS = [1, 60, 3600, 86400]
NAMES = [('s', 's'),
         ('m', 'm'),
         ('h', 'h'),
         ('day', 'days')]


class Job(object):

    def __init__(self, config, cr, publishers, runner):
        self.ok = 1
        self.envs = []
        self.env = copy.deepcopy(config.get("env", {}))
        self.config = config
        self.cr = cr
        self.publishers = publishers
        self.errors = []
        self.error = True
        self.seconds = 0
        self.name = config["name"]
        self.runner = runner
        setattr(self.runner, "job", self)

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
        env = self.cr.config.get_env(env_name, self)
        env.build()
        self.env.update(env.env)
        self.envs.append(env)
        LOG.debug("New env vars %r" % env.env)
        LOG.debug("Resulting env (%r) %r" % (self, self.env))

    def run_script(self, script):
        LOG.debug("Running script %r" % script)
        name = script["name"]

        def stdout_callback(line):
            for p in self.publishers:
                # kinda dirty hack: stream_name = file_name
                # so file name will be actually directory/file
                p.publish_line(os.path.join(self.name, name), line)

        cmd = script["interpreter"]
        path = script.get("path")
        if path:
            if path.startswith("~"):
                path = os.path.expanduser(path)
            stdin = open(path, "rb")
        else:
            stdin = StringIO.StringIO(script["data"])
        LOG.debug("(%r) calling runner.run with env (%d) %r" % (
            self, id(self.env), self.env))
        return self.runner.run(cmd, stdout_callback, stdin=stdin, env=self.env)

    def run(self):
        start = time.time()
        threading.currentThread().setName("%s-%s" % (self.cr.run_id,
                                                     self.name))
        LOG.info("Started job thread")

        def stdout_callback(line):
            for p in self.publishers:
                # kinda dirty hack: stream_name = file_name
                # so file name will be actually directory/file
                p.publish_line(os.path.join(self.name, "00_build"), line)

        try:
            try:
                self.runner.build(stdout_callback)
            except:
                self.errors.append("Build failed.")
                raise
            for env_name in self.config.get("environments", []):
                self.prepare_environment(env_name)
            self.runner.boot()
            for script in ("build-scripts", "test-scripts", "scripts"):
                LOG.debug("Scripts found %r" % self.config.get(script, []))
                for s in self.config.get(script, []):
                    LOG.debug("Starting script %r" % s)
                    self.errors.append(self.run_script(
                        self.cr.config.scripts[s]))
        except Exception as e:
            # TODO: fix exceptions hadling
            LOG.error("Failed to build.")
            LOG.debug("Exception while building:", exc_info=True)
            self.errors.append(e)
        finally:
            self.seconds = int(time.time() - start)
            self.error = any(self.errors)

            try:
                LOG.debug("Publishing files")
                if hasattr(self.runner, "publish_files"):
                    self.runner.publish_files(self)
            except Exception:
                LOG.error("Failed to publish files", exc_info=True)

            self.runner.cleanup()
            while self.envs:
                env = self.envs.pop()
                env.cleanup()

        LOG.debug("Done with publishing files")


class CR(object):

    def __init__(self, project_config, config, event):
        self.project_config = project_config
        self.config = config
        self.event = event
        self.jobs = []
        self.run_id = "".join(random.sample(string.letters, 16))

    def run_jobs(self):
        threads = []
        threading.currentThread().setName(self.run_id)
        publishers = list(self.config.get_publishers(self.run_id, self.event))
        for job_config in self.project_config["jobs"]:
            event = self.event["type"]
            events = job_config.get("events", ["patchset-created",
                                               "comment-added"])
            if event not in events:
                LOG.debug("%s: skipping job %s" % (event, job_config["name"]))
                continue
            runner = self.config.get_runner(job_config["runner"])
            runner.setup(**job_config["runner-args"])
            job = Job(job_config, self, publishers, runner)
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
            except Exception:
                LOG.warning("Publishing failed", exc_info=True)
        LOG.debug("Done with publishing")
