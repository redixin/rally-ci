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

import logging
import paramiko
from mako.template import Template

from rallyci.publishers import base

LOG = logging.getLogger(__name__)


class Publisher(base.Publisher):

    def __init__(self, *args, **kwargs):
        super(Publisher, self).__init__(*args, **kwargs)
        template_file = self.config.get("template_file")
        if template_file:
            self.template = Template(filename=template_file)
        else:
            self.template = Template(self.config["template"])

    def publish_summary(self, jobs):
        success = not any([(job.error and job.config.get("voting", True))
                           for job in jobs])
        summary = self.template.render(jobs=jobs, event=self.event,
                                       success=success, run_id=self.run_id)
        cmd_template = """gerrit review -m '{summary}' {verified} {id}"""
        verified = ""
        if self.config.get("vote"):
            verified = "--verified=-1" if not success else "--verified=+1"
        commit_id = self.event["patchSet"]["revision"]
        cmd = cmd_template.format(summary=summary, id=commit_id,
                                  verified=verified)
        LOG.debug("Sending to gerrit: %s" % cmd)
        if not self.config.get("fake"):
            c = paramiko.SSHClient()
            c.load_system_host_keys()
            c.connect(**self.config["ssh"])
            c.exec_command(cmd)
            c.close()

    def publish_line(self, job_name, stream, line):
        pass

    def check_config(config):
        #  TODO
        pass
