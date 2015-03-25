
import mock
import unittest

from rallyci.runners import docker


class DockerTestCase(unittest.TestCase):

    @mock.patch("rallyci.runners.docker.sshutils")
    def test_build_cache_hit(self, m_ssh):
        ssh = mock.Mock()
        ssh.execute.side_effect = [(0, 0, 0), (0, 0, 0)]
        m_ssh.SSH.return_value = ssh
        config = {"ssh": {"user": "root"}}
        global_config = mock.Mock()
        r = docker.Runner(config, global_config)
        r.setup("~/fake/path/")
        r._run = mock.Mock()
        r.build(mock.Mock())
        expected = []
        self.assertEqual(expected, r._run.mock_calls)

    @mock.patch("rallyci.runners.docker.utils.get_rnd_name")
    @mock.patch("rallyci.runners.docker.sshutils")
    @mock.patch("rallyci.runners.docker.open", create=True)
    def test_build_cahce_miss(self, m_open, m_ssh, m_rnd):
        m_rnd.return_value = "fake_rnd"
        m_open.return_value = "fake_file"
        ssh = mock.Mock()
        ssh.execute.side_effect = [(1, 0, 0), (0, 0, 0)]
        m_ssh.SSH.return_value = ssh
        config = {"ssh": {"user": "root"}}
        global_config = mock.Mock()
        r = docker.Runner(config, global_config)
        r.setup("~/fake/path/")
        r._run = mock.Mock()
        r.build("fake_stdout_callback")
        r._run.assert_called_once_with(["docker", "build", "--no-cache",
                                        "-t", "rallyci:__fake_path_",
                                        "/tmp/fake_rnd"],
                                       "fake_stdout_callback")
        expected = [mock.call("mkdir /tmp/fake_rnd"),
                    mock.call("cat > /tmp/fake_rnd/Dockerfile",
                              stdin="fake_file")]
        self.assertEqual(expected, ssh.run.mock_calls)
