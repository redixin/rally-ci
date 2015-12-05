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


class BaseVM(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def run_script(self, script):
        """
        :param dict script:
        """
        pass

    @abc.abstractmethod
    def destroy(self):
        pass


class BaseProvider(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def __init__(self, root, config):
        """
        :param Root root:
        :param dict config: full provider config
        """
        pass

    @abc.abstractmethod
    def get_vms(self, cfg):
        """Return list of VM instances.

        :param cfg: job.runner part of job config
        """
        pass


class BaseEvent(metaclass=abc.ABCMeta):
    """Represent event."""

    @abc.abstractmethod
    def __init__(self, cfg, raw_event):
        """Wrap raw_event.

        should define properties:
            env: environment variables to be added to env to vms
            project: project name
            commit: id of commit
            cr: id of change request
            url: url to change request or merged patch
            cfg_url: url to fetch rally-ci config of project
            key: key

        :param dict cfg: service config section
        :param dict raw_event: event data decoded from json
        """
        pass
