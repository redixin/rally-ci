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

import abc


class Runner:
    __metaclass__ = abc.ABCMeta

    def __init__(self, config, global_config):
        self.config = config
        self.global_config = global_config

    @abc.abstractmethod
    def setup(self, **kwargs):
        pass

    def boot(self):
        pass

    @abc.abstractmethod
    def build(self, stdout_cb):
        """Build VM/Container to run job.

        Raise exception if build failed.
        """
        pass

    @abc.abstractmethod
    def run(self, cmd, stdout_callback, stdin=None, env=None):
        """Run command.

        :param cmd: string command
        :param stdout_callback: callback to be called for every out/err string
        :param env: environment variables dict
        """
        pass

    @abc.abstractmethod
    def cleanup(self):
        pass
