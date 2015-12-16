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

from rallyci.services import gerrit


class GerritTestCase(unittest.TestCase):

    def test__get_project_name(self):
        event = {"change": {"project": "spam/eggs"}}
        self.assertEqual("spam/eggs", gerrit._get_project_name(event))
        event = {"refUpdate": {"project": "spam/eggs"}}
        self.assertEqual("spam/eggs", gerrit._get_project_name(event))

    def test__get_env(self):
        cfg = {
            "VAL1": "key1.subkey1.value1",
            "VAL2": "key2.nonexistent",
        }
        event = {
            "key1": {
                "subkey1": {
                    "value1": "spam"
                }
            }
        }
        env = {"VAL1": "spam"}
        self.assertEqual(env, gerrit._get_env(event, cfg))

    def test_handle_stdout(self):
        expected_calls = []
        g = gerrit.Service(mock.Mock(), **{"name": "eggs", "ssh": {}})
        g._handle_event = he = mock.Mock()

        g._handle_stdout("12")
        self.assertEqual(expected_calls, he.mock_calls)

        g._handle_stdout("3\n")
        expected_calls += [mock.call("123")]
        self.assertEqual(expected_calls, he.mock_calls)

        g._handle_stdout("456\n789")
        expected_calls += [mock.call("456")]
        self.assertEqual(expected_calls, he.mock_calls)

        g._handle_stdout("\n0ab\n")
        expected_calls += [mock.call("789"), mock.call("0ab")]
        self.assertEqual(expected_calls, he.mock_calls)
