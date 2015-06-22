#!/usr/bin/env python
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import os
import logging

from rallyci import utils


LOG = logging.getLogger(__name__)


class Class:

    def __init__(self, **kwargs):
        self.cfg = kwargs
        self.streams = {}

    def set_stream(self, job, stream):
        """
        :param stream: stream name, e.g. build.sh or run.sh
        """
        if hasattr(self, "fileobj"):
            self.fileobj.close()
        log_root = os.path.join(self.cfg["path"], job.log_path)
        os.makedirs(log_root, exist_ok=True)
        self.fileobj = open(os.path.join(log_root, stream + ".txt"), "wb")

    def log(self, data):
        """Log data.

        :param data: data to be logged
        """
        if data:
            os.write(self.fileobj.fileno(), data)
        else:
            self.fileobj.flush()

    def cleanup(self):
        if hasattr(self, "fileobj"):
            self.fileobj.close()
