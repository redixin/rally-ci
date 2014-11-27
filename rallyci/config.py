
import os

import yaml
import importlib

import logging
LOG = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class Config(object):

    def __init__(self):
        self.stream = {}
        self.daemon = {}
        self.publisher = {}
        self.publishers = []
        self.glob = {}
        self.env_drivers = {}
        self.projects = {}
        self.publisher_modules = {}

    def init(self):
        self._init_publishers()
        self._init_publishers_()
        self._init_environments()

    def _init_publishers_(self):
        for p in self.publishers:
            if p["module"] not in self.publisher_modules:
                self.publisher_modules[p["module"]] = importlib.\
                        import_module(p["module"])
        LOG.debug("Imported publisher modules: %r" % self.publisher_modules)

    def get_publishers(self, event):
        for p in self.publishers:
            yield self.publisher_modules[p["module"]].Publisher(event, p)

    def _init_publishers(self):
        self.publisher_class = importlib.import_module(
                self.publisher["driver"]).Driver
        error = self.publisher_class.check_config(self.publisher)
        if error:
            raise ConfigError(error)

    def _init_environments(self):
        for name, env in self.environments.items():
            drv = env["driver"]
            if drv not in self.env_drivers:
                self.env_drivers[drv] = importlib.import_module(drv)

    def load_items(self, name, items):
        if not hasattr(self, name):
            setattr(self, name, {})
        target = getattr(self, name)
        for item in items:
            if name in target:
                msg = "Duplicate %s %s" % item_name, item["name"]
                LOG.error(msg)
                raise ConfigError(msg)
            target[item["name"]] = item

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
        self.stream.update(data.get("stream", {}))
        self.publisher.update(data.get("publisher", {}))
        self.publishers += data.get("publishers", [])
        self.glob.update(data.get("global", {}))
        self.daemon.update(data.get("daemon", {}))
        self.load_items("environments", data.get("environments", []))
        self.load_items("drivers", data.get("drivers", []))
        self.load_items("scripts", data.get("scripts", []))
        self.load_items("job_templates", data.get("job-templates", []))
        self.load_projects(data.get("projects", []))

    def get_env(self, env_name):
        env = self.environments[env_name]
        return self.env_drivers[env["driver"]].Env(self, env)

    def get_publisher(self, event):
        return self.publisher_class(self.publisher, event)

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
