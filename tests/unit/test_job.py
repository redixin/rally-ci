import unittest
import mock

from rallyci import job


class JobTestCase(unittest.TestCase):

    @mock.patch("rallyci.job.Job.__init__", return_value=None)
    def test_human_time(self, m_init):
        j = job.Job()
        j.seconds = 3124144
        self.assertEqual(j.human_time, "36days 3h 49m 4s")
