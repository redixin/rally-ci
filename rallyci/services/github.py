# Copyright 2015: Mirantis Inc.
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

from aiogh import github
from aiohttp import web
import yaml


class Event(base.BaseEvent):

    def __init__(self, cfg, raw_event):
        self.cfg = cfg
        self.raw_event = raw_event

        pr = raw_event["pull_request"]
        self.project_name = pr["head"]["repo"]["full_name"]
        self.commit = pr["head"]["sha"]
        self.url = pr["url"]
        self.key = self.commit

        self.env = {
            "GITHUB_REPO": self.project_name,
            "GITHUB_COMMIT": self.commit,
        }


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
        urls = kwargs.get("urls", {})
        self.root.http.add_route("GET", urls.get("oauth2", "/oauth2/"), self._handle_oauth2)
        self.root.http.add_route("GET", urls.get("register", "/reg/"), self._handle_registraion)
        self.root.http.add_route("GET", urls.get("settings", "/settings/"), self._handle_settings)
        self.root.http.add_route("POST", urls.get("webhook", "/webhook"), self._handle_webhook)
        secrets = yaml.safe_load(open(self.cfg["secrets"]))
        self.oauth = github.OAuth(**secrets)
        store = kwargs["data-path"]
        os.makedirs(store, exist_ok=True)
        self.tokens = dbm.open(os.path.join(store, "tokens.db"), "cs")
        self.orgs = dbm.open(os.path.join(store, "orgs.db"), "cs")
        session_store = dbm.open(os.path.join(store, "sessions.db"), "cs")
        self.ss = SessionStore(session_store, kwargs.get("cookie_name", "ghs"))

    async def _webhook_push(self, request, data):
        self.root.log.info("Push")

    async def _webhook_pull_request(self, request, data):
        self.root.log.info("Pull request")
        if data["action"] in ("opened", "synchronized"):
            self.root.log.info("Emiting event")
            event = Event(self.cfg, data)

    async def _handle_webhook(self, request):
        event = request.headers["X-Github-Event"]
        handler = getattr(self, "_webhook_%s" % event, None)
        if handler is None:
            self.root.log.debug("Unknown event")
            self.root.log.debug(str(request.headers))
            return web.Response(text="ok")
        self.root.log.debug("Event: %s" % event)
        data = json.loads((await request.read()).decode("utf-8"))
        await handler(request, data)
        return web.Response(text="ok")

    def _get_client(self, request):
        session = self.ss.session(request)
        return github.Client(session.data["token"])

    @session_resp
    async def _handle_oauth2(self, request):
        client = await self.oauth.oauth(request.GET["code"], request.GET["state"])
        user_data = await client.get("user")
        orgs = await client.get("user/orgs")
        session = self.ss.session(request)
        self.tokens[str(user_data["id"])] = client.token
        session.data["token"] = client.token
        response = web.Response(text="ok")
        return response

    async def _handle_settings(self, request):
        return web.Response(text="ok")
        client = self._get_client(request)
        orgs = await client.get("user/orgs")
        #repos = await client.get("user/repos")
        data = {
            "name": "web",
            "active": True,
            "events": ["*"],
            "config": {
                "url": "http://sc.r-ci.tk/webhook",
                "content_type": "json"},
        }
        for org in orgs:
            url = "/orgs/"
            resp = await client.post("/orgs/:org/hooks", org["login"], **data)
        return web.Response(text="ok")

    async def _handle_registraion(self, request):
        url = self.oauth.generate_request_url(
            ("repo:status", "write:repo_hook", "admin:org_hook", "read:org"))
        return web.HTTPFound(url)

    async def handle_pr(self, request):
        await asyncio.sleep(1)

    async def run(self):
        await asyncio.Event(loop=self.root.loop).wait()
