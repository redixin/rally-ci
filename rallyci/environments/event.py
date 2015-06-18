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


class Class:

    def __init__(self, *args, **kwargs):
        self.cfg = kwargs

    def setup(self, *args, **kwargs):
        pass

    def build(self, job):
        for k, v in self.cfg["export-event"].items():
            value = dict(job.event.raw_event)
            for key in v.split("."):
                value = value[key]
            job.env[k] = value
