#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import socket
import unittest


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_port(port, timeout=4):
    deadline = time.time() + timeout
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        if time.time() > deadline:
            return
        e = s.connect_ex(("localhost", port))
        if e:
            time.sleep(0.1)
        else:
            s.close()
            return


class IntegrationTest(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="rci_tst_integration")
        conf = self._get_config()
        self.cf = os.path.join(self.tmpdir.name, "cf.yaml")
        with open(self.cf, "w") as cfg:
            cfg.write(yaml.dump(conf))
        self.server_out = open(os.path.join(self.tmpdir.name, "out.log"), "w+")
        self.server_err = open(os.path.join(self.tmpdir.name, "err.log"), "w+")
        self.server = subprocess.Popen(["rally-ci", self.cf],
                                       stdout=self.server_out,
                                       stderr=self.server_err)
        wait_for_port(port)

    def tearDown(self):
        self.server.terminate()
        for fd in (self.server_err, self.server_out):
            fd.seek(0)
            print(fd.read())
            fd.close()
        with open(self.cf) as cf:
            print(cf.read())
        self.tmpdir.cleanup()
