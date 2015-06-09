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

    def log(self, stream, data):
        """Log data.

        :param stream: stream name, e.g. build.sh or run.sh
        :param data: data to be logged
        """
        fileobj = self.streams.get(stream)
        if not fileobj:
            self.log_root = os.path.join(self.cfg["path"], self.job.log_path)
            utils.makedirs(self.log_root)
            fileobj = open(os.path.join(self.log_root,
                                        stream + ".txt"), "wb")
            self.streams[stream] = fileobj
        if not data:
            fileobj.flush()
        else:
            os.write(fileobj.fileno(), data)
