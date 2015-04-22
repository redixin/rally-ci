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

from rallyci.publishers import base

import logging
LOG = logging.getLogger(__name__)


class Publisher(base.Publisher):

    @staticmethod
    def check_config(config):
        pass

    def publish_line(self, job_name, stream, line):
        LOG.debug("Publishing line %s in stream %s (job: %s)" % (line, stream,
                                                                 job_name))
        pass

    def publish_summary(self, jobs):
        LOG.debug("Publishing summary for jobs %r" % jobs)
        pass
