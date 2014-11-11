import unittest
import mock

from rallyci import project

class JobTestCase(unittest.TestCase):

    @mock.patch("rallyci.project.__import__", create=True)
    @mock.patch("rallyci.project.Job.__init__", return_value=None)
    def test_human_time(self, m_init, m_import):
        job = project.Job()
        job.seconds = 3124144
        self.assertEqual(job.human_time, "36days 3h 49m 4s")
