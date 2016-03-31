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

import abc
import asyncio
from concurrent import futures
import os

class BaseVM(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def get_ssh(self, username="root"):
        pass

    @abc.abstractmethod
    def run_script(self):
        pass

    @abc.abstractmethod
    def destroy(self):
        pass


class BaseProvider(metaclass=abc.ABCMeta):

    def __init__(self, root, config):
        """
        :param Root root:
        :param dict config: full provider config
        """
        self.root = root
        self.config = config

    @abc.abstractmethod
    def start(self):
        pass

    @abc.abstractmethod
    def get_vms(self, job):
        """Return Host instance.

        :param job: Job instance
        :returns: list of VM instances
        """
        pass


class BaseHost(metaclass=abc.ABCMeta):

    def __init__(self, cfg, provider):
        """
        :param dict cfg: provider.hosts item
        """
        self.cfg = cfg
        self.provider = provider


class BaseVM(metaclass=abc.ABCMeta):

    @asyncio.coroutine
    def run_scripts(self, key, out_cb, err_cb, script_cb=None):
        for script_name in self.cfg[key]:
            if script_cb:
                script_cb(script_name)
            e = yield from self.run_script(script_name, out_cb, err_cb)
            if e:
                return e

    @asyncio.coroutine
    def publish(self, path):
        ssh = yield from self.get_ssh()
        for src, dst in self.cfg.get("publish", []):
            yield from ssh.get(src, os.path.join(path, dst), recurse=True)

    @abc.abstractmethod
    def get_ssh(self, username="root"):
        pass

    @asyncio.coroutine
    def run_script(self, name, out_cb, err_cb):
        script = self.job.task.get_script(name)
        cmd = script.get("interpreter", "/bin/bash -xe -s")
        username = script.get("username", "root")
        ssh = yield from self.get_ssh(username=username)
        e = yield from ssh.run(cmd, stdin=script["data"],
                               env=self.job.env,
                               stdout=out_cb,
                               stderr=err_cb,
                               check=False)
        return e

class BaseEvent(metaclass=abc.ABCMeta):
    """Represent event."""

    @abc.abstractmethod
    def __init__(self, cfg, raw_event):
        """Wrap raw_event.

        should define properties:
            env: environment variables to be added to env to vms
            project: project name
            commit: id of commit
            cr: id of change request
            url: url to change request or merged patch
            cfg_url: url to fetch rally-ci config of project
            key: key

        :param dict cfg: service config section
        :param dict raw_event: event data decoded from json
        """
        pass


class ObjRunnerMixin:

    _running_objs = {}
    _running_cleanups = {}

    @asyncio.coroutine
    def _wait_objs(self, lst):
        if not lst:
            return
        yield from asyncio.wait(lst, return_when=futures.ALL_COMPLETED,
                                loop=self.loop)

    @asyncio.coroutine
    def wait_objs(self):
        yield from self._wait_objs(self._running_objs.keys())

    @asyncio.coroutine
    def wait_cleanups(self):
        yield from self._wait_objs(self._running_cleanups.keys())

    def cancel_objs(self):
        for obj in self._running_objs.keys():
            obj.cancel()

    def _cleanup_done_cb(self, fut):
        obj = self._running_cleanups.pop(fut)
        try:
            result = fut.result()
            self.log.info("Finished cleanup %s (%s)" % (obj, result))
        except asyncio.CancelledError:
            self.log.info("Cancelled cleanup %s" % obj)
        except:
            self.log.exception("Exception in cleanup %s:" % obj)

    def _obj_done_cb(self, fut):
        obj = self._running_objs.pop(fut)
        if hasattr(obj, "cleanup"):
            cl = self.loop.create_task(obj.cleanup())
            cl.add_done_callback(self._cleanup_done_cb)
            self._running_cleanups[cl] = obj
        try:
            result = fut.result()
            self.log.info("Finished %s (%s)" % (obj, result))
        except asyncio.CancelledError:
            self.log.info("Cancelled %s" % obj)
        except:
            self.log.exception("Exception in %s:" % obj)

    def start_obj(self, obj):
        fut = self.loop.create_task(obj.run())
        self._running_objs[fut] = obj
        fut.add_done_callback(self._obj_done_cb)
        return fut
