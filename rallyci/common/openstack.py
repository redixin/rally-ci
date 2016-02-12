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
import json

import aiohttp


class OpenStack:
    def __init__(self, credentials, ssh_keypair):
        self.ssh_keypair = ssh_keypair
        self.credentials = credentials

    @asyncio.coroutine
    def login(self):
        pass

    @asyncio.coroutine
    def get_vm(self, name, job):
        pass


class Client:
    def __init__(self, auth_url, credentials, log=None):
        self.auth_url = auth_url
        self.credentials = credentials
        self.log = log
        self.headers = {"content-type": "application/json", "accept": "application/json"}

    async def login(self):
        async with aiohttp.post(self.auth_url + "/auth/tokens",
                                data=json.dumps(self.credentials),
                                headers=self.headers) as r:
            self.token_data = await r.json()
            self.headers["X-Auth-Token"] = r.headers["X-Subject-Token"]
        self.project_id = self.token_data["token"]["project"]["id"]

    async def list_images(self):
        url = self.get_endpoint("image")
        async with self.get(url + "/v1/images") as r:
            return(await r.json())

    async def list_flavors(self):
        url = self.get_endpoint("compute") + "/flavors"
        async with self.get(url) as r:
            return await r.json()

    async def boot_server(self, name, image, flavor):
        images = await self.list_images()
        for i in images["images"]:
            if i["name"] == image:
                image = i["id"]
                break
        flavors = await self.list_flavors()
        for f in flavors["flavors"]:
            if f["name"] == flavor:
                flavor = f["links"][0]["href"]
                break
        url = self.get_endpoint("compute") + "/servers"
        payload = {
            "server": {
                "name": name,
                "imageRef": image,
                "flavorRef": flavor,
            }
        }
        async with self.post(url, payload) as r:
            server = await r.json()
        server_id = server["server"]["id"]
        server = await self.wait_server(server_id, "ACTIVE", [])
        print(server["server"]["addresses"])
        return server

    async def get_server(self, server_id):
        url = self.get_endpoint("compute")
        async with self.get(url + "/servers/%s" % server_id) as r:
            data = await r.json()
        return data

    async def delete_server(self, server_id):
        url = self.get_endpoint("compute")
        async with self.delete(url + "/servers/%s" % server_id) as r:
            data = await r.json()
        return data

    async def wait_server(self, server_id, status, error_statuses, delay=1):
        while True:
            await asyncio.sleep(delay)
            server = await self.get_server(server_id)
            current_status = server["server"]["status"]
            if current_status == status:
                return server
            if current_status in error_statuses:
                raise Exception("Error status %s" % current_status)

    def delete(self, url):
        print("DELETE", url)
        return aiohttp.delete(url, headers=self.headers)

    def get(self, url):
        print("GET", url)
        return aiohttp.get(url, headers=self.headers)

    def post(self, url, payload):
        print("POST", url)
        return aiohttp.post(url, headers=self.headers,
                            data=json.dumps(payload))

    def get_endpoint(self, service_type):
        for item in self.token_data["token"]["catalog"]:
            if item["type"] == service_type:
                return item["endpoints"][0]["url"]
