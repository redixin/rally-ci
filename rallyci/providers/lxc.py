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

from rallyci import base
from rallyci.common import ssh
from rallyci import utils

COMMON_OPTS = (("-B", "backingstore"), )
CREATE_OPTS = (("--zfsroot", "zfsroot"), )


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

        self._opts = sum(self._get_opts(COMMON_OPTS), [])
        self._create_opts = sum(self._get_opts(CREATE_OPTS), [])
        self._create_opts += self._opts
        self._hosts = [ssh.Client(loop=self.root.loop, **cfg) for cfg in cfg.get("hosts")]
        self._public_key = root.config.data["ssh-key"]["default"]["public"]

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
        with open(self._public_key) as pk:
            yield from host.run(cmd, stdin=pk, stdout=print)
        cmd = ["sed", "-i",
               "s|PermitRootLogin.*|PermitRootLogin yes|",
               "/var/lib/lxc/%s/rootfs/etc/ssh/sshd_config" % image]
        yield from host.run(cmd, stderr=print)

    @asyncio.coroutine
    def _build_image(self, host, image):
        image_cfg = self.cfg["images"][image]
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

    @asyncio.coroutine
    def get_vm(self, image, job):
        host = yield from self._get_host()

        yield from self._build_image(host, image)
        cmd = ["lxc-start-ephemeral", "-o", image, "-d",
               "--storage-type", self.cfg.get("ephemeral-storage-type", "tmpfs"),
               "--union-type", self.cfg.get("ephemeral-union-type", "aufs"),
        ]
        chunks = []
        yield from host.run(cmd, stdout=chunks.append)
        print(chunks)
        for line in "\n".join(chunks).splitlines():
            for word in line.split(" "):
                if word.startswith(image):
                    vm_name = word.strip()
        print(repr(vm_name))
        yield from host.run(["lxc-stop", "-n", vm_name], stderr=print)

    @asyncio.coroutine
    def start(self):
        yield from asyncio.sleep(0)

    @asyncio.coroutine
    def boot(self, name):
        pass

    @asyncio.coroutine
    def cleanup(self, vms):
        for vm in vms:
            pass
