
import logging

import base
import paramiko

from mako.template import Template


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
        success = not any([job.error for job in jobs])
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

    def publish_line(self, stream, line):
        pass

    def check_config(config):
        #  TODO
        pass
