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


import urllib
from urllib import request

from tests.integrated import base


class MetadataServiceTestCase(base.IntegrationTest):

    def _get_config(self):
        port = base.get_free_port()
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
        return ([conf], (port,))

    def test_metadata(self):
        r = request.urlopen(self.url + "openstack/latest/user_data")
        self.assertEqual(b"userdata", r.read())

    def test_metadata_404(self):
        self.assertRaises(urllib.error.HTTPError,
                          request.urlopen,
                          self.url + "none")
