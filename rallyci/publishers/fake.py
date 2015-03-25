
from rallyci.publishers import base

import logging
LOG = logging.getLogger(__name__)


class Publisher(base.Publisher):

    @staticmethod
    def check_config(config):
        pass

    def publish_line(self, stream, line):
        LOG.debug("Publishing line %s in stream %s" % (line, stream))
        pass

    def publish_summary(self, jobs):
        LOG.debug("Publishing summary for jobs %r" % jobs)
        pass
