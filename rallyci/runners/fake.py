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
