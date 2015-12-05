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

import copy
import unittest
from unittest import mock

from rallyci.task import Task


class TaskTestCase(unittest.TestCase):

    def test__start_jobs(self):
        global_cfg = {
            "script": {
                "s1": "script1",
                "s2": "script2",
                "s3": "script3",
            },
            "job": {
                "j1": "job1",
                "j2": "job2",
                "j3": "job3",
            },
            "matrix": {
                "tox-jobs": {
                    "projects": ["p1", "p2"],
                    "jobs": ["j1", "j2"],
                },
            },
        }
        local_cfg = [
            {"script": {"name": "s1"}},
            {"job": {"name": "j4"}},
            {"matrix": {
                "name": "m1",
                "projects": ["p3"],
                "jobs": ["j1", "j3"],
            }}
        ]
        mixed_cfg = copy.deepcopy(global_cfg)
        mixed_cfg["script"]["s1"] = local_cfg[0]["script"]
        mixed_cfg["job"]["j4"] = local_cfg[1]["job"]
        mixed_cfg["matrix"]["m1"] = local_cfg[2]["matrix"]
        mock_root = mock.Mock()
        mock_root.config.data = global_cfg
        task = Task(mock_root, "p3", {}, {}, "")
        task._start_job = mock.Mock()
        task._start_jobs(local_cfg)
        expected = [
            mock.call("j1"),
            mock.call("j3"),
        ]
        self.assertEqual(mixed_cfg, task.config)
        self.assertEqual(expected, task._start_job.mock_calls)
