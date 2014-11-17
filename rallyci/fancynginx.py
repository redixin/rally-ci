
import gzip
import os, errno
import re

from mako.template import Template

import logging
LOG = logging.getLogger(__name__)


def mkdir(path):
    try:
        os.mkdir(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        LOG.warning("mkdir: directory exist (%s)" % path)


class Driver(object):
    """Job results publisher."""

    def __init__(self, config, event):
        """Constructor.

        Config is global config object.
        """
        self.config = config
        self.event = event
        change_id = event["change"]["id"]
        self.cr_dir = os.path.join(self.config["dir"], change_id)
        self.mkdir()

    def mkdir(self):
        mkdir(self.cr_dir)
        header = os.path.join(self.cr_dir, self.config["header-filename"])
        self.render(header, "cr-template", event=self.event)
        self.ps_dir = os.path.join(self.cr_dir, self.event["patchSet"]["number"])
        mkdir(self.ps_dir)
        header = os.path.join(self.ps_dir, self.config["header-filename"])
        self.render(header, "ps-template", event=self.event)

    def stdout(self, job, name="log.txt.gz"):
        dirname = os.path.join(self.ps_dir, job["name"])
        filename = os.path.join(dirname, name)
        mkdir(dirname)
        header = os.path.join(dirname, self.config["header-filename"])
        self.render(header, "job-template", job=job)
        return gzip.open(filename, "wb")

    def publish_summary(self, jobs):
        index = os.path.join(self.ps_dir, "index.html")
        self.render(index, "summary-template", jobs=jobs, event=self.event)

    def render(self, filename, template_name, **kwargs):
        template = Template(filename=self.config[template_name])
        with open(filename, "wb") as f:
            f.write(template.render(**kwargs))
