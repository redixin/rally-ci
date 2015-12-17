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
from unittest import mock


class ConfigTestCase(unittest.TestCase):

    def setUp(self):
        self.root = mock.Mock()
        dirname = os.path.dirname(os.path.realpath(__file__))
        cf = os.path.join(dirname, "test_config.yaml")
        with mock.patch("rallyci.config.Config.configure_logging"):
            self.config = config.Config(self.root, cf, False)

    def test_ssh_keys(self):
        self.assertEqual("/keys/test.pub", self.config.get_ssh_key())
        self.assertEqual("/keys/test", self.config.get_ssh_key("private"))

    def test_get_jobs(self):
        jobs = list(self.config.get_jobs("openstack/rally"))
        expected = [{"env": {"TOX_ENV": "pep8"},
                     "name": "tox-pep8",
                     "provider": "my_virsh",
                     "vms": [{"name": "ubuntu-1404-dev",
                              "scripts": ["git_checkout", "run_tests"]}]}]
        self.assertEqual(expected, jobs)

    def test_get_jobs_local(self):
        job = {"name": "spam", "scripts": ["eggs"]}
        local_config = [{"job": job}]
        jobs_gen = self.config.get_jobs("openstack/rally", "jobs",
                                        local_config)
        self.assertIn(job, list(jobs_gen))

    def test_get_jobs_local_override(self):
        job = {"name": "tox-pep8", "scripts": ["eggs"]}
        local_config = [{"job": job}]
        jobs_gen = self.config.get_jobs("openstack/rally", "jobs",
                                        local_config)
        self.assertEqual([job], list(jobs_gen))

    def test_get_script(self):
        s = self.config.get_script("show_env")
        expected = {"name": "show_env", "user": "rally", "data": "env"}
        self.assertEqual(expected, s)

    def test_get_script_local(self):
        local_config = [{"script": {"name": "test", "data": "ok"}}]
        s = self.config.get_script("test", local_config)
        self.assertEqual(local_config[0]["script"], s)

    def test_get_script_local_override(self):
        local_config = [{"script": {"name": "show_env", "data": "ok"}}]
        s = self.config.get_script("show_env", local_config)
        self.assertEqual(local_config[0]["script"], s)
