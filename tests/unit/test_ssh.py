from rallyci.common import ssh
import unittest

class SSHTestCase(unittest.TestCase):
    def test__escape_cmd(self):
        cmd = ["one", "two"]
        self.assertEqual("'one' 'two'", ssh._escape_cmd(cmd))

    def test__escape_env(self):
        env = {"FOO": "BAR"}
        self.assertEqual("FOO='BAR' ", ssh._escape_env(env))
