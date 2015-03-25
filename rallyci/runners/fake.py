
from rallyci.runners import base

import logging
LOG = logging.getLogger(__name__)


class Runner(base.Runner):

    def build(self):
        pass

    def cleanup(self):
        pass

    def init(self, **kwargs):
        pass

    def run(self, cmd, stdout_handler, stdin=None, env=None):
        stdout_handler((1, "line1\n"))
        stdout_handler((1, "line2\n"))
        stdout_handler((2, "err1\n"))
        stdout_handler((1, "line3\n"))
