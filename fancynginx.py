
import gzip
import os, errno
import re

from mako.template import Template

from log import logging
LOG = logging.getLogger(__name__)


def mkdir(path):
    try:
        os.mkdir(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        LOG.warning("mkdir: directory exist (%s)" % path)


class Driver(object):

    def __init__(self, config):
        self.config = config

    def mkdir(self, event):
        change_id = event["change"]["id"]
        self.cr_dir = os.path.join(self.config["dir"], change_id)
        mkdir(self.cr_dir)
        template = Template(filename=self.config["cr-template"])
        header_filename = os.path.join(self.cr_dir, self.config["header-filename"])
        with open(header_filename, "wb") as head:
            head.write(template.render(event=event))
        self.ps_dir = os.path.join(self.cr_dir, event["patchSet"]["number"])
        mkdir(self.ps_dir)
        template = Template(filename=self.config["ps-template"])
        header_filename = os.path.join(self.ps_dir, self.config["header-filename"])
        with open(header_filename, "wb") as head:
            head.write(template.render(event=event))

    def stdout(self, job, name="log.txt.gz"):
        dirname = os.path.join(self.ps_dir, job["name"])
        filename = os.path.join(dirname, name)
        mkdir(dirname)
        template = Template(filename=self.config["job-template"])
        header_filename = os.path.join(dirname, self.config["header-filename"])
        with open(header_filename, "wb") as head:
            head.write(template.render(job=job))
        return gzip.open(filename, "wb")
