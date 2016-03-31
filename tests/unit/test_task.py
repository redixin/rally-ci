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

import unittest
from unittest import mock

from rallyci.task import Task


class TaskTestCase(unittest.TestCase):

    @mock.patch("rallyci.task.Task.__del__")
    @mock.patch("rallyci.task.asyncio")
    def test___init__(self, mock_asyncio, mock_del):
        return
        root = mock.Mock()
        event = mock.Mock()
        t = Task(root, event)
        self.assertEqual([], t.jobs)
