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
import os.path
import re
import time

from rallyci import base
from rallyci.common.ssh import SSH
from rallyci import utils

COMMON_OPTS = (("-B", "backingstore"), )
CREATE_OPTS = (("--zfsroot", "zfsroot"), )

RE_LXC_IP = re.compile(r"IP:\s+([\d\.]+)$")


class Host:

    def __init__(self, provider, ssh):
        self.provider = provider
        self.ssh = ssh

        self.job_vm = {}
        self._building_images = collections.defaultdict(
                functools.partial(asyncio.Lock, loop=provider.root.loop))
        self._create_opts = ["-B", "btrfs"]

    @asyncio.coroutine
    def update_stats(self):
        status, out, err = yield from self.ssh.out("lxc-ls | wc -l")
        try:
            self.num_containers = int(out)
        except ValueError:
            self.num_containers = 0

    @asyncio.coroutine
    def _upload_ssh_key(self, image):
        dst = "/var/lib/lxc/%s/rootfs/root/.ssh" % image
        yield from self.ssh.run(["mkdir", "-p", dst])
        dst += "/authorized_keys"
        cmd = "cat >> %s" % dst
        with open(self.provider.pubkey) as pk:
            yield from self.ssh.run(cmd, stdin=pk, stdout=print)
        cmd = ["sed", "-i",
               "s|PermitRootLogin.*|PermitRootLogin yes|",
               "/var/lib/lxc/%s/rootfs/etc/ssh/sshd_config" % image]
        yield from self.ssh.run(cmd, stderr=print)

    @asyncio.coroutine
    def _build_image(self, vm_cfg, job):
        image = vm_cfg["name"]
        with (yield from self._building_images[image]):
            cmd = ["lxc-info", "--name", image]
            not_exist = yield from self.ssh.run(cmd, check=False)
            if not not_exist:
                return
            image_cfg = self.provider.cfg["vms"][image]
            cmd = ["lxc-create", "--name", image] + self._create_opts
            cmd += ["-t", image_cfg["template"],
                    "--", image_cfg.get("args", "")]

            yield from self.ssh.run(cmd, stderr=print)
            yield from self._upload_ssh_key(image)
            cmd = ["lxc-start", "-d", "--name", image]
            yield from self.ssh.run(cmd, stderr=print)
            ip = yield from self._get_ip(image)
            vm = VM(self, job, ip, vm_cfg, image)
            for script in self.provider.cfg["vms"][image].get("build-scripts",
                                                              []):
                yield from vm.run_script(script, out_cb=print, err_cb=print)
            cmd = ["lxc-stop", "-n", image]
            yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def _get_ip(self, name, timeout=60):
        _start = time.time()
        cmd = ["lxc-info", "-n", name]
        data = []
        while True:
            yield from asyncio.sleep(1)
            yield from self.ssh.run(cmd, stdout=data.append)
            for line in "".join(data).splitlines():
                m = RE_LXC_IP.match(line)
                if m:
                    return m.group(1)
            if time.time() > (_start + timeout):
                raise Exception("Timeout waiting for %s" % name)

    @asyncio.coroutine
    def get_vm(self, vm_cfg, job):
        """
        :param dict vm_cfg: job.vms item
        :param Job job:
        """
        yield from self._build_image(vm_cfg, job)
        name = utils.get_rnd_name("rci_")
        cmd = ["lxc-clone", "-s", "-o", vm_cfg["name"], "-n", name]
        yield from self.ssh.run(cmd, stderr=print)
        cmd = ["lxc-start", "-d", "-n", name]
        yield from self.ssh.run(cmd, stderr=print)
        ip = yield from self._get_ip(name)
        vm = VM(self, job, ip, vm_cfg, name)
        return vm


class Provider(base.BaseProvider):

    def __init__(self, root, cfg):
        """
        :param dict cfg: provider config
        """
        self.root = root
        self.cfg = cfg
        self.name = cfg["name"]

        self.pubkey = os.path.expanduser(
                root.config.data["ssh-key"]["default"]["public"])
        self.privkey = root.config.data["ssh-key"]["default"]["private"]

        self.gethost_lock = asyncio.Lock(loop=root.loop)
        self.hosts = []
        for host_cfg in cfg.get("hosts"):
            self.hosts.append(Host(self, SSH(loop=self.root.loop, **host_cfg)))

    @asyncio.coroutine
    def get_vms(self, job):
        host = yield from self._get_host()
        vms = []
        for vm_cfg in job.config["vms"]:
            vm = yield from host.get_vm(vm_cfg, job)
            vms.append(vm)
        return vms

    @asyncio.coroutine
    def _get_host(self):
        import random
        random.shuffle(self.hosts)
        while 1:
            for host in self.hosts:
                yield from host.update_stats()
                if host.num_containers < self.cfg.get("max_containers", 8):
                    return host
            yield from asyncio.sleep(15)

    @asyncio.coroutine
    def start(self):
        yield from asyncio.sleep(0)

    @asyncio.coroutine
    def boot(self, name):
        pass

    @asyncio.coroutine
    def stop(self):
        pass


class VM(base.BaseVM):

    def __init__(self, host, job, ip, cfg, name):
        self.host = host
        self.provider = host.provider
        self.job = job
        self.ip = ip
        self.cfg = cfg
        self.name = name

    @asyncio.coroutine
    def get_ssh(self, username="root"):
        ssh = SSH(self.provider.root.loop, self.ip,
                  username=username, keys=[self.provider.privkey],
                  jumphost=self.host.ssh)
        yield from ssh.wait()
        return ssh

    @asyncio.coroutine
    def destroy(self):
        cmd = ["lxc-destroy", "-f", "-n", self.name]
        yield from self.host.ssh.run(cmd, stdout=print)
