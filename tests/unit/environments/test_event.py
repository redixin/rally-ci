
import mock
import unittest

from rallyci.environments import event

class EventTestCase(unittest.TestCase):
    def test_build(self):
        job = mock.Mock()
        job.cr.event = {
                "key1": "val1",
                "key2": "val2",
                "subdict1": {"subkey1": "subval1"},
            }
        config = {
                "export-event": {
                    "VAL1": "key1",
                    "VAL2": "key2",
                    "SUBVAL": "subdict1.subkey1"}
                }
        e = event.Environment({}, config, job)
        e.build()
        expected = {
                "SUBVAL": "subval1",
                "VAL1": "val1",
                "VAL2": "val2"}
        self.assertEqual(expected, e.env)
