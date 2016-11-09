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
import ssl

import aiohttp


class OpenStackError(Exception):
    pass


class OverQuota(OpenStackError):
    pass


class NeutronError(OpenStackError):
    pass


class Forbidden(OpenStackError):
    pass


NEUTRON_EXCEPTION_MAP = {
    "OverQuota": OverQuota,
}


def neutron_exception_factory(r, json):
    error_type = json["NeutronError"]["type"]
    message = json["NeutronError"].get("message")
    exception = NEUTRON_EXCEPTION_MAP.get(error_type)
    if exception:
        return exception(message)
    return NeutronException(message)


def forbidden_exceotion_factory(r, json):
    message = json["forbidden"].get("message")
    if message:
        if "exceeded" in message:
            return OverQuota(message)
        else:
            return Forbidden(message)
    return Forbidden(str(json))


EXCEPTION_FACTORY_MAP = {
    "NeutronError": neutron_exception_factory,
    "forbidden": forbidden_exceotion_factory,
}


async def _process_response(r):
    if r.headers["Content-Type"].startswith("application/json"):
        json = await r.json()
        print(json)
        if len(json) > 1:
            return json
        else:
            key = list(json.keys())[0]
            exception_factory = EXCEPTION_FACTORY_MAP.get(key)
            if exception_factory:
                raise exception_factory(r, json)
            return json


class Client:

    def __init__(self, auth_url, username, tenant, loop=None, log=None,
                 cafile=None, token_renew_delay=3300):
        self.auth_url = auth_url
        self.username = username
        self.tenant = tenant
        self.log = log
        self.token_renew_delay = token_renew_delay
        self.loop = loop or asyncio.get_event_loop()
        self.headers = {"content-type": "application/json",
                        "accept": "application/json"}
        if cafile:
            sslcontext = ssl.create_default_context(cafile=cafile)
            conn = aiohttp.TCPConnector(ssl_context=sslcontext)
            self.session = aiohttp.ClientSession(connector=conn, loop=self.loop)
        else:
            session = aiohttp.ClientSession(loop=self.loop)

    async def login(self, *, password=None, token=None):
        credentials = {
            "auth": {"tenantName": self.tenant}
        }
        if password:
            credentials["auth"]["passwordCredentials"] = {
                "username": self.username,
                "password": password,
            }
        else:
            credentials["auth"]["token"] = {"id": token}
        async with self.session.post(self.auth_url + "/tokens",
                                     data=json.dumps(credentials),
                                     headers=self.headers) as r:
            self.token_data = await r.json()
            self.headers["X-Auth-Token"] = self.token_data["access"]["token"]["id"]
        self.loop.call_later(self.token_renew_delay, self.loop.create_task,
                             self.login(token=self.headers["X-Auth-Token"]))

    async def list_images(self):
        url = self.get_endpoint("image")
        async with self.get(url + "/v1/images") as r:
            return(await r.json())

    async def list_networks(self):
        url = self.get_endpoint("network")
        async with self.get(url + "/v2.0/networks") as r:
            return await r.json()

    async def create_network(self, name, admin_state_up=True):
        return await self._post("network", "/v2.0/networks", {
            "network": {
                "name": name,
                "admin_state_up": admin_state_up,
            }
        })

    async def delete_network(self, network_id):
        return await self._delete("network", "/v2.0/networks/" + network_id)

    async def create_subnet(self, network_id):
        url = url = self.get_endpoint("network")
        payload = {
            "subnet": {
                "network_id": network_id,
                "gateway_ip": None,
                "cidr": "10.1.1.0/24",
                "ip_version": 4,
            }
        }
        async with self.post(url + "/v2.0/subnets", payload) as r:
            return await r.json()

    async def list_flavors(self):
        url = self.get_endpoint("compute") + "/flavors"
        async with self.get(url) as r:
            return await r.json()

    async def create_server(self, name, imageRef, flavorRef, networks, key_name):
        return await self._post("compute", "/servers", {
            "server": {
                "name": name,
                "imageRef": imageRef,
                "flavorRef": flavorRef,
                "networks": networks,
                "key_name": key_name,
            }
        })

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
        server = await self.wait_server(server_id, "ACTIVE", ["ERROR"])
        return server

    def list_servers(self):
        return self._get("compute", "/servers")

    async def get_server(self, server_id):
        url = self.get_endpoint("compute")
        async with self.get(url + "/servers/%s" % server_id) as r:
            if r.status != 200:
                raise OpenStackError(r.status)
            data = await r.json()
        return data

    async def delete_server(self, server_id, wait=False):
        url = self.get_endpoint("compute")
        async with self.delete(url + "/servers/%s" % server_id) as r:
            data = await r.json()
        if wait:
            while 1:
                try:
                    await asyncio.sleep(1)
                    server = await self.get_server(server_id)
                except OpenStackError:
                    return
        return data

    async def wait_server(self, server_id, status, error_statuses, delay=1, retries=64):
        while retries:
            await asyncio.sleep(delay)
            server = await self.get_server(server_id)
            current_status = server["server"]["status"]
            if current_status == status:
                return server
            if current_status in error_statuses:
                raise Exception("VM error %s" % server)
            else:
                print(current_status)
            retries -= 1


    async def _post(self, service, url, payload):
        async with self.session.post(self.get_endpoint(service) + url,
                                     headers=self.headers,
                                     data=json.dumps(payload)) as r:
            return await _process_response(r)

    async def _get(self, service, url):
        async with self.session.get(self.get_endpoint(service) + url,
                                    headers=self.headers) as r:
            print(service, url)
            return (await r.json())

    async def _delete(self, service, url):
        async with self.session.delete(self.get_endpoint(service) + url,
                                       headers=self.headers) as r:
            print(await r.text())
            return (await r.json())

    def delete(self, url):
        print("DELETE", url)
        return self.session.delete(url, headers=self.headers)

    def get(self, url):
        print("GET", url)
        return self.session.get(url, headers=self.headers)

    def post(self, url, payload):
        print("POST", url, payload)
        return self.session.post(url, headers=self.headers,
                                 data=json.dumps(payload))

    def get_endpoint(self, service_type):
        for item in self.token_data["access"]["serviceCatalog"]:
            if item["type"] == service_type:
                return item["endpoints"][0]["publicURL"]
