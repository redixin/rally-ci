# Copyright 2016: Mirantis Inc.
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

import asyncio

from rallyci import base
from rallyci.common import openstack


class Provider(base.Provider):

    async def start(self):
        secrets = self.root.config.secrets[self.name]
        self.client = openstack.Client(secrets["auth_url"],
                                       secrets["username"],
                                       secrets["tenant"],
                                       cafile=secrets["cafile"])
        await self.client.login(password=secrets["password"])
        self.network_ids = {}
        self.image_ids = {}
        self.flavor_ids = {}
        for network in (await self.client.list_networks())["networks"]:
            self.network_ids[network["name"]] = network["id"]

        for image in (await self.client.list_images())["images"]:
            self.image_ids[image["name"]] = image["id"]

        for item in (await self.client.list_flavors())["flavors"]:
            self.flavor_ids[item["name"]] = item["id"]

        print(self.network_ids, self.image_ids, self.flavor_ids)
        print(await self.get_cluster("test_cluster"))

    async def get_cluster(self, name):
        cluster = base.Cluster()
        for vm_name, vm_conf in self.config["clusters"][name].items():
            networks = []
            for if_type, if_name in vm_conf["interfaces"]:
                if if_type == "dynamic":
                    uuid = cluster.networks.get(if_name)
                    if uuid is None:
                        network = await self.client.create_network(if_name)
                        uuid = network["network"]["id"]
                        subnet = await self.client.create_subnet(uuid)
                        print(subnet)
                        cluster.networks[if_name] = uuid
                else:
                    uuid = self.network_ids[if_name]
                networks.append({"uuid": uuid})
            server = await self.client.create_server(
                vm_name, self.image_ids[vm_conf["image"]],
                self.flavor_ids[vm_conf["flavor"]],
                networks)
            print(server)
        return cluster
