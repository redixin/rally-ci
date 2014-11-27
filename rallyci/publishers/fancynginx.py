
import gzip
import os
import errno
import base

from mako.template import Template

import logging
LOG = logging.getLogger(__name__)


def mkdir(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        LOG.warning("mkdir: directory exist (%s)" % path)


class Publisher(base.Publisher):

    @staticmethod
    def check_config(config):
        tpls = ["header-template", "job-template", "summary-template"]
        fails = []
        for tpl in tpls:
            filename = config[tpl]
            if not os.access(filename, os.F_OK | os.R_OK):
                fails.append(filename)
        if fails:
            return "Fancynginx: can't open template(s) %s" % ','.join(fails)

    def __init__(self, *args, **kwargs):
        super(Publisher, self).__init__(*args, **kwargs)
        self.streams = {}
        self.path = os.path.join(self.config["dir"], self.run_id)
        mkdir(self.path)
        header = os.path.join(self.path, self.config["header-filename"])
        self._render(header, "header-template", event=self.event)

    def publish_line(self, stream, line):
        if stream not in self.streams:
            fname = os.path.join(self.path, stream + ".txt.gz")
            mkdir(os.path.dirname(fname))
            self.streams[stream] = gzip.open(fname, "wb")
        self.streams[stream].write(line[1])

    def publish_summary(self, jobs):
        index = os.path.join(self.path, "index.html")
        for stream in self.streams.values():
            stream.close()
        self._render(index, "summary-template", jobs=jobs, event=self.event)

    def _render(self, filename, template_name, **kwargs):
        template = Template(filename=self.config[template_name])
        with open(filename, "wb") as f:
            f.write(template.render(**kwargs))
