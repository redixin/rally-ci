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

from rallyci import config

import os
import unittest
import json


class ConfigTestCase(unittest.TestCase):

    def test___init__(self):
        dirname = os.path.dirname(os.path.realpath(__file__))
        filename = os.path.join(dirname, "../../etc/sample-config.yaml")
        c = config.Config(filename)
        print(json.dumps(c.data, indent=2))
