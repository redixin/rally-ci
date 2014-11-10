
import os, sys

import json
import yaml

from log import logging
LOG = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class Config(object):
    scripts = {}
    job_templates = {}
    projects = {}

    def load_scripts(self, scripts):
        for script in scripts:
            self._assert_new_item("script", script, self.scripts)
            self.scripts[script["name"]] = script

    def load_job_templates(self, job_templates):
        for jt in job_templates:
            self._assert_new_item("job-template", jt, self.job_templates)
            self.job_templates[jt["name"]] = jt

    def load_projects(self, projects):
        for project in projects:
            self._assert_new_item("project", project, self.projects)
            self.projects[project["name"]] = project
            common_attrs = project.get("job-common-attrs")
            if common_attrs:
                for job in project["jobs"]:
                    job.update(common_attrs)
                    for jt in job.get("templates", []):
                        jt = dict(self.job_templates[jt])
                        del(jt["name"])
                        job.update(jt)

    def load_file(self, fname):
        data = yaml.safe_load(open(fname, "rb"))
        self.stream = data.get("stream", {})
        self.logs = data.get("logs", {})
        self.load_scripts(data.get("scripts", []))
        self.load_job_templates(data.get("job-templates", []))
        self.load_projects(data.get("projects", []))

    def _assert_new_item(self, item_name, item, items):
        if item["name"] in items:
            msg = "Duplicate %s %s" % item_name, item["name"]
            LOG.error(msg)
            raise ConfigError(msg)

    def load_dir(self, d):
        for dpath, dnames, fnames in os.walk(d):
            for fname in fnames:
                filename = os.path.join(dpath, fname)
                LOG.debug("Loading configuration: %s" % filename)
                self.load_file(filename)

    def load(self, dirs):
        for d in dirs:
            if d.startswith("~"):
                d = os.path.expanduser(d)
            if os.path.isdir(d):
                self.load_dir(d)
            else:
                LOG.warning("Unable to load config from: %s" % d)
