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

import gzip
import os
import errno
import subprocess
import logging

from rallyci.publishers import base

from mako.template import Template

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
            self.streams[stream] = gzip.open(fname, "wb", 9)
        self.streams[stream].write(line[1])

    def publish_summary(self, jobs):
        index = os.path.join(self.path, "index.html")
        for stream in self.streams.values():
            stream.close()
        self._render(index, "summary-template", jobs=jobs, event=self.event)

    def publish_files(self, ssh, src, dst):
        """Publish directory from test vm.

        :param ssh: dictionary with ssh credentials
        """
        dst = os.path.join(self.path, dst.strip("/"))
        uhp = "%s@%s:%s" % (ssh["user"], ssh["host"], src)
        port = str(ssh.get("port", 22))
        cmd = ["scp", "-B", "-o", "StrictHostKeyChecking no",
               "-r", "-P", port, uhp, dst]
        LOG.debug("Calling %r" % cmd)
        subprocess.call(cmd)

    def _render(self, filename, template_name, **kwargs):
        template = Template(filename=self.config[template_name])
        with open(filename, "wb") as f:
            f.write(template.render(**kwargs))
