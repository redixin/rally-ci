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
import base64
from collections import defaultdict
import functools
import json
import dbm
import os

from rallyci import base
from rallyci.task import Task

from aiogh import github
from aiohttp import web
import yaml


class Event(base.Event):

    def __init__(self, root, raw_event, event_type, client):
        self.root = root
        self.raw_event = raw_event
        self.client = client

        pr = raw_event["pull_request"]
        self.project = pr["head"]["repo"]["full_name"]
        self.head = pr["head"]["sha"]
        self.url = pr["url"]
        self.event_type = event_type
        self.env = {
            "GITHUB_REPO": self.project,
            "GITHUB_HEAD": self.head,
        }

    async def job_started_cb(self, job):
        data = {
            "state": "pending",
            "context": job.name,
            "description": "pending...",
            "target_url": self.root.config.core["logs-url"] + job.id,
        }
        await self.client.post("/repos/:repo/statuses/:sha",
                               self.project, self.head, **data)

    async def job_finished_cb(self, job, state):
        data = {
            "state": state,
            "description": state,
            "target_url": self.root.config.core["logs-url"] + job.id,
            "context": job.name,
        }
        await self.client.post("/repos/:repo/statuses/:sha",
                               self.project, self.head, **data)


def session_resp(handler):
    @functools.wraps(handler)
    async def wrapper(self, request):
        response = await handler(self, request)
        session = request.get("session")
        if session is not None:
            session.set_cookie(response)
            session.save()
        return response
    return wrapper


class Session:

    def __init__(self, ss, sid):
        self.ss = ss
        self.sid = sid
        data = self.ss.store.get(self.sid)
        self.data = json.loads(data.decode("ascii")) if data else dict()

    def set_cookie(self, response):
        response.set_cookie(self.ss.cookie_name, self.sid)

    def save(self):
        self.ss.store[self.sid] = json.dumps(self.data)


class SessionStore:

    def __init__(self, store, cookie_name):
        self.store = store
        self.cookie_name = cookie_name

    def session(self, request):
        sid = request.cookies.get(self.cookie_name)
        if sid is None:
            sid = base64.b64encode(os.urandom(15)).decode('ascii')
        self.sid = sid
        session = Session(self, sid)
        request["session"] = session
        return session


class Service:

    def __init__(self, root, **kwargs):
        self.root = root
        self.cfg = kwargs
        self.url = url = kwargs.get("url", "/github/")
        self.root.http.add_route("GET", url + "oauth2", self._handle_oauth2)
        self.root.http.add_route("GET", url + "login", self._handle_registraion)
        self.root.http.add_route("GET", url + "settings", self._handle_settings)
        self.root.http.add_route("POST", url + "webhook", self._handle_webhook)
        self.root.http.add_route("POST", url + "add_org_webhook", self._handle_add_org_webhook)
        self.oauth = github.OAuth(**root.config.secrets[self.cfg["name"]])
        store = kwargs["data-path"]
        os.makedirs(store, exist_ok=True)
        self.tokens = dbm.open(os.path.join(store, "tokens.db"), "cs")
        self.orgs = dbm.open(os.path.join(store, "orgs.db"), "cs")
        session_store = dbm.open(os.path.join(store, "sessions.db"), "cs")
        self.ss = SessionStore(session_store, kwargs.get("cookie_name", "ghs"))

    @staticmethod
    async def check_config(config, service_name):
        """
        :param rallyci.config.Config config:
        :param str service_name:
        """
        pass

    async def _webhook_push(self, request, data):
        print(data)

    async def _webhook_pull_request(self, request, data):
        if data["action"] in ("opened", "synchronize"):
            self.root.log.info("Emiting event")
            owner = str(data["repository"]["owner"]["id"]).encode("ascii")
            client = github.Client(self.tokens[owner].decode("ascii"))
            task = Task(self.root, Event(self.root, data, "cr", client))
            self.root.start_task(task)
        else:
            self.root.log.debug("Skipping event %s" % data["action"])

    async def _handle_webhook(self, request):
        event = request.headers["X-Github-Event"]
        handler = getattr(self, "_webhook_%s" % event, None)
        if handler is None:
            self.root.log.debug("Unknown event")
            self.root.log.debug(str(request.headers))
            return web.Response(text="ok")
        self.root.log.info("Event: %s" % event)
        await handler(request, await request.json())
        return web.Response(text="ok")

    def _get_client(self, request):
        session = self.ss.session(request)
        token = session.data.get("token")
        if token:
            return github.Client(token)

    @session_resp
    async def _handle_oauth2(self, request):
        client = await self.oauth.oauth(request.GET["code"], request.GET["state"])
        user_data = await client.get("user")
        session = self.ss.session(request)
        self.tokens[str(user_data["id"])] = client.token
        session.data["token"] = client.token
        response = web.HTTPFound(self.url + "/settings")
        return response

    async def _handle_settings(self, request):
        import jinja2
        import pkgutil
        template = jinja2.Template(
                pkgutil.get_data("rallyci.services",
                                 "github_settings.html").decode("utf8"))
        client = self._get_client(request)
        if client is None:
            return web.HTTPUnauthorized(text="fail")
        orgs = []
        for org in (await client.get("user/orgs")):
            orgs.append(org)
        return web.Response(text=template.render(orgs=orgs), content_type="text/html")

    async def _handle_add_org_webhook(self, request):
        await request.post()
        data = {
            "name": "web",
            "active": True,
            "events": ["*"],
            "config": {
                "url": self.root.config.core["url"] + self.url + "webhook",
                "content_type": "json"
            },
        }
        client = self._get_client(request)
        resp = await client.post("/orgs/:org/hooks", request.POST["org"], **data)
        return web.Response(text=str(resp))

    async def _handle_registraion(self, request):
        url = self.oauth.generate_request_url(
            ("repo:status", "write:repo_hook", "admin:org_hook", "read:org"))
        return web.HTTPFound(url)

    async def handle_pr(self, request):
        await asyncio.sleep(1)

    async def run(self):
        await asyncio.Event(loop=self.root.loop).wait()
