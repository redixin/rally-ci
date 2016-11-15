# Copyright 2016: Mirantis Inc.
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


class Service(abc.ABCMeta):

    def __init__(self, rci, name, config, secrets):
        """
        :param rallyci.rci.RCI rci:
        :param str name:
        :param dict config: service config section
        :param dict secrets: secrets section for current service
        """
        self.rci = rci
        self.name = name
        self.config = config
        self.secrets = secrets

    @abc.abstractmethod
    async def run(self):
        pass
