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
from rallyci.common.ssh import SSH


class Provider(base.Provider):

    def __init__(self, root, *args, **kwargs):
        super().__init__(root, *args, **kwargs)
        self._ready = asyncio.Event(loop=root.loop)
        self._get_cluster_lock = asyncio.Lock()
        self._vms_semaphore = asyncio.Semaphore(self.config["max_vms"])

    async def start(self):
        self.access_net = self.config["ssh"]["access_net"]
        self.ssh_keys = [self.config["ssh"]["private_key_path"]]
        self.jumphost = self.config["ssh"].get("jumphost")
        if self.jumphost:
            self.jumphost = SSH(self.root.loop, keys=self.ssh_keys, **self.jumphost)
            await self.jumphost.wait()
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

        self._ready.set()

    async def delete_cluster(self, cluster):
        for vm in cluster.vms.values():
            await self.client.delete_server(vm.uuid, wait=True)
            self._vms_semaphore.release()
        for uuid in cluster.networks.values():
            await self.client.delete_network(uuid)

    async def _get_vm_ip(self, uuid):
        data = await self.client.wait_server(uuid, delay=4, status="ACTIVE", error_statuses=["ERROR"])
        access_net = data["server"]["addresses"].get(self.access_net)
        if access_net:
            return access_net[0]["addr"]

    async def _create_server(self, server_name, image_id, flavor_id,
                             networks, ssh_key_name):
        await self._vms_semaphore.acquire()
        server = await self.client.create_server(
            server_name, image_id, flavor_id, networks, ssh_key_name)
        return server

    async def get_cluster(self, name):
        async with self._get_cluster_lock:
            return await self._get_cluster(name)

    async def _get_cluster(self, name):
        await self._ready.wait()
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
                        cluster.networks[if_name] = uuid
                else:
                    uuid = self.network_ids[if_name]
                networks.append({"uuid": uuid})
            server = await self._create_server(
                vm_name, self.image_ids[vm_conf["image"]],
                self.flavor_ids[vm_conf["flavor"]],
                networks, self.config["ssh"]["key_name"])
            cluster.vms[vm_name] = VM(server["server"]["id"])
        for vm in cluster.vms.values():
            ip = await self._get_vm_ip(vm.uuid)
            if ip is not None:
                vm.ssh = SSH(self.root.loop, ip,
                             self.config["ssh"]["default_username"],
                             keys=self.ssh_keys,
                             jumphost=self.jumphost)
        return cluster


class VM(base.SSHVM):

    def __init__(self, uuid):
        self.uuid = uuid

    def __str__(self):
        return "<OpenStack VM %s (%s)>" % (self.uuid, self.ssh)

    async def publish_path(self, src, dst):
        pass

    __unicode__ = __repr__ = __str__
