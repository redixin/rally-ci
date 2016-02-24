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
import collections
import functools
import re
import time

from rallyci import base
from rallyci.common.ssh import SSH
from rallyci import utils

COMMON_OPTS = (("-B", "backingstore"), )
CREATE_OPTS = (("--zfsroot", "zfsroot"), )

RE_LXC_IP = re.compile(r"IP:\s+([\d\.]+)$")


class Provider(base.BaseProvider):

    def __init__(self, root, cfg):
        """
        :param dict cfg: provider config
        """
        self.root = root
        self.cfg = cfg
        self.name = cfg["name"]
        self._building_images = collections.defaultdict(
                functools.partial(asyncio.Lock, loop=root.loop))

        self._opts = [] # sum(self._get_opts(COMMON_OPTS), [])
        self._create_opts = [] # sum(self._get_opts(CREATE_OPTS), [])
        self._create_opts += self._opts
        self._hosts = [SSH(loop=self.root.loop, **cfg)
                       for cfg in cfg.get("hosts")]
        self.pubkey = root.config.data["ssh-key"]["default"]["public"]
        self.privkey = root.config.data["ssh-key"]["default"]["private"]

    @asyncio.coroutine
    def _get_host(self):
        import random
        return random.choice(self._hosts)

    def _get_opts(self, opts):
        for opt, name in opts:
            opt_value = self.cfg.get(name)
            if opt_value:
                yield [opt, opt_value]

    @asyncio.coroutine
    def _upload_ssh_key(self, host, image):
        dst = "/var/lib/lxc/%s/rootfs/root/.ssh" % image
        yield from host.run(["mkdir", "-p", dst])
        dst += "/authorized_keys"
        cmd = "cat >> %s" % dst
        with open(self.pubkey) as pk:
            yield from host.run(cmd, stdin=pk, stdout=print)
        cmd = ["sed", "-i",
               "s|PermitRootLogin.*|PermitRootLogin yes|",
               "/var/lib/lxc/%s/rootfs/etc/ssh/sshd_config" % image]
        yield from host.run(cmd, stderr=print)

    @asyncio.coroutine
    def _build_image(self, host, image, job):
        image_cfg = self.cfg["vms"][image]
        cmd = ["lxc-create", "--name", image] + self._create_opts
        cmd += ["-t", image_cfg["template"],
                "--", image_cfg.get("args", "")]
        with (yield from self._building_images[image]):
            check_cmd = ["lxc-info", "--name", image]
            not_exist = yield from host.run(check_cmd, check=False)
            if not not_exist:
                return
            yield from host.run(cmd, stderr=print)
            yield from self._upload_ssh_key(host, image)
            cmd = ["lxc-start", "-d", "--name", image]
            yield from host.run(cmd, stderr=print)
            ip = yield from self._get_ip(host, image)
            vm = VM(self, host, job, ip, image)
            for script in self.cfg["vms"][image].get("build-scripts", []):
                yield from vm.run_script(script)
            cmd = ["lxc-stop", "-n", image]
            yield from host.run(cmd)

    @asyncio.coroutine
    def _get_ip(self, host, name, timeout=60):
        _start = time.time()
        cmd = ["lxc-info", "-n", name]
        data = []
        while True:
            yield from asyncio.sleep(1)
            yield from host.run(cmd, stdout=data.append)
            for line in "".join(data).splitlines():
                m = RE_LXC_IP.match(line)
                if m:
                    return m.group(1)
            if time.time() > (_start + timeout):
                raise Exception("Timeout waiting for %s" % name)

    @asyncio.coroutine
    def get_vm(self, image, job):
        host = yield from self._get_host()
        yield from self._build_image(host, image, job)
        name = utils.get_rnd_name()
        cmd = ["lxc-clone", "-o", image, "-n", name] + self._opts
        yield from host.run(cmd, stderr=print)
        cmd = ["lxc-start", "-d", "-n", name]
        yield from host.run(cmd, stderr=print)
        ip = yield from self._get_ip(host, name)
        vm = VM(self, host, job, ip, name)
        return vm

    @asyncio.coroutine
    def start(self):
        yield from asyncio.sleep(0)

    @asyncio.coroutine
    def boot(self, name):
        pass

    @asyncio.coroutine
    def cleanup(self, job):
        pass

    @asyncio.coroutine
    def stop(self):
        pass


class VM(base.BaseVM):

    def __init__(self, provider, host, job, ip, name):
        self.provider = provider
        self.host = host
        self.job = job
        self.ip = ip
        self.name = name

    @asyncio.coroutine
    def run_script(self, script_name):
        script = self.job.get_script(script_name)
        ssh = yield from self.get_ssh(username=script.get("username", "root"))
        cmd = script.get("interpreter", "/bin/bash -xe -s")
        e = yield from ssh.run(cmd, stdin=script["data"], env=self.job.env,
                               stdout=print,
                               stderr=print,
                               check=False)
        return e

    @asyncio.coroutine
    def get_ssh(self, username="root"):
        ssh = SSH(self.provider.root.loop, self.ip,
                  username=username, keys=[self.provider.privkey])
        yield from ssh.wait()
        return ssh

    @asyncio.coroutine
    def destroy(self):
        cmd = ["lxc-destroy", "-n", self.name]
        yield from self.host.run(cmd)
