import unittest
import urllib
from urllib import request
import socket
import time
import subprocess
import tempfile
import os

import yaml

from tests.integrated import base

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


class MetadataServiceTestCase(unittest.TestCase):

    def test_metadata(self):
        r = request.urlopen(self.url + "openstack/latest/user_data")
        self.assertEqual(b"userdata", r.read())

    def test_metadata_404(self):
        self.assertRaises(urllib.error.HTTPError,
                          request.urlopen,
                          self.url + "none")

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="rci_t_metadata")
        port = get_free_port()
        self.url = "http://localhost:%s/" % port
        conf = {
                "provider": {
                    "name": "virsh",
                    "module": "rallyci.providers.virsh",
                    "nodes": [],
                    "hosts": [],
                    "metadata_server": {
                        "listen_addr": "localhost",
                        "listen_port": port,
                        "user_data": "userdata",
                    },
                }
        }
        conf = base.get_config(conf)
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
