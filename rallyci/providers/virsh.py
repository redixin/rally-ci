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
import contextlib
import time
import os
import random
import re
import json
import logging
import tempfile
import uuid
from xml.etree import ElementTree as et

import aiohttp
from aiohttp import web

from rallyci import utils
from rallyci.common import asyncssh

LOG = logging.getLogger(__name__)

RE_LA = re.compile(r".*load average: (\d+\.\d+),.*")
RE_MEM = re.compile(r".*Mem: +\d+ +\d+ +(\d+) +\d+ +\d+ +(\d+).*")
IFACE_RE = re.compile(r"\d+: ([a-z]+)(\d+): .*")
IP_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s")
DYNAMIC_BRIDGES = {}
DYNAMIC_BRIDGE_LOCK = asyncio.Lock()
IMAGE_LOCKS = {}


class ZFS:

    def __init__(self, ssh, **kwargs):
        self.ssh = ssh
        self.dataset = kwargs["dataset"]

    @asyncio.coroutine
    def clone(self, src, dst):
        cmd = "zfs clone {dataset}/{src}@1 {dataset}/{dst}"
        cmd = cmd.format(dataset=self.dataset, src=src, dst=dst)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def snapshot(self, name, snapshot="1"):
        cmd = "zfs snapshot {dataset}/{name}@{snapshot}".format(
                dataset=self.dataset, name=name, snapshot=snapshot)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def create(self, name):
        cmd = "zfs create {dataset}/{name}".format(dataset=self.dataset,
                                                   name=name)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def exist(self, name):
        cmd = "zfs list {dataset}/{name}@1".format(dataset=self.dataset,
                                                   name=name)
        error = yield from self.ssh.run(cmd, raise_on_error=False)
        return not error

    @asyncio.coroutine
    def list_files(self, name):
        cmd = "ls /{dataset}/{name}".format(dataset=self.dataset, name=name)
        ls = yield from self.ssh.run(cmd, return_output=True)
        return [os.path.join("/", self.dataset, name, f) for f in ls.splitlines()]

    @asyncio.coroutine
    def download(self, name, url):
        # TODO: cache
        yield from self.create(name)
        cmd = "wget {url} -O /{dataset}/{name}/vda.qcow2"
        cmd = cmd.format(name=name, dataset=self.dataset, url=url)
        yield from self.ssh.run(cmd)
        cmd = "qemu-img resize /{dataset}/{name}/vda.qcow2 32G"
        cmd = cmd.format(name=name, dataset=self.dataset, url=url)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def destroy(self, name):
        cmd = "zfs destroy {dataset}/{name}".format(name=name,
                                                    dataset=self.dataset)
        yield from self.ssh.run(cmd)


class BTRFS:

    def __init__(self, ssh, path, **kwargs):
        self.ssh = ssh
        self.path = path

    @asyncio.coroutine
    def create(self, name):
        cmd = "btrfs subvolume create {path}/{name}".format(path=self.path,
                                                            name=name)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def list_files(self, name):
        cmd = "ls {path}/{name}".format(path=self.path, name=name)
        ls = yield from self.ssh.run(cmd, return_output=True)
        return [os.path.join("/", self.path, name, f) for f in ls.splitlines()]

    @asyncio.coroutine
    def clone(self, src, dst):
        cmd = "btrfs subvolume snapshot {path}/{src} {path}/{dst}"
        cmd = cmd.format(path=self.path, src=src, dst=dst)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def exist(self, name):
        cmd = "btrfs subvolume show {path}/{name}".format(path=self.path,
                                                          name=name)
        error = yield from self.ssh.run(cmd, raise_on_error=False)
        return not error

    @asyncio.coroutine
    def snapshot(self, *args, **kwargs):
        yield from asyncio.sleep(0)

    @asyncio.coroutine
    def destroy(self, name):
        cmd = "btrfs subvolume delete {path}/{name}".format(path=self.path,
                                                            name=name)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def download(self, name, url):
        # TODO: cache
        yield from self.create(name)
        cmd = "wget {url} -O /{path}/{name}/vda.qcow2 2> /dev/null"
        cmd = cmd.format(name=name, path=self.path, url=url)
        yield from self.ssh.run(cmd)
        # TODO: size should be set in config
        cmd = "qemu-img resize /{path}/{name}/vda.qcow2 32G"
        cmd = cmd.format(name=name, path=self.path, url=url)
        yield from self.ssh.run(cmd)


class Host:

    def __init__(self, ssh_conf, config, root, vm_key):
        """
        ssh_config: item from hosts from provider
        config: full "provider" item
        """
        self.config = config
        self.root = root
        self.vms = []
        self.br_vm = {}
        self.ssh = asyncssh.AsyncSSH(**ssh_conf)
        self.storage = BTRFS(self.ssh, **config["storage"])
        self.vm_key = vm_key
        self.la = 0.0
        self.free = 0

    def __str__(self):
        return "<Host %s (la: %s, free: %s)>" % (self.ssh.hostname,
                                                 self.la, self.free)

    @asyncio.coroutine
    def update_stats(self):
        cmd = "uptime && free -m"
        data = yield from self.ssh.run(cmd, return_output=True)
        self.la = float(RE_LA.search(data, re.MULTILINE).group(1))
        free = RE_MEM.search(data, re.MULTILINE).groups()
        self.free = sum(map(int, free))

    @asyncio.coroutine
    def boot_image(self, name):
        conf = self.config["images"][name]
        vm = VM(self, conf)
        vm.storage_name = name # FIXME
        for f in (yield from self.storage.list_files(name)):
            vm.add_disk(f)
        vm.add_net(self.config.get("build_net", "virbr0"))
        yield from vm.boot()
        return vm

    @asyncio.coroutine
    def build_image(self, name):
        IMAGE_LOCKS.setdefault(name, asyncio.Lock())
        with (yield from IMAGE_LOCKS[name]):
            if (yield from self.storage.exist(name)):
                LOG.debug("Image %s exist" % name)
                return
            LOG.info("Building image %s" % name)
            image_conf = self.config["images"][name]
            parent = image_conf.get("parent")
            if parent:
                yield from self.build_image(parent)
                yield from self.storage.clone(parent, name)
            else:
                url = image_conf.get("url")
                if url:
                    yield from self.storage.download(name, url)
                    return # TODO: support build_script for downloaded images
            build_scripts = image_conf.get("build-scripts")
            if build_scripts:
                vm = yield from self.boot_image(name)
                try:
                    for script in build_scripts:
                        script = self.root.config.data["script"][script]
                        LOG.debug("Running build script %s" % script)
                        yield from vm.run_script(script)
                    yield from vm.shutdown(storage=False)
                except:
                    LOG.exception("Error building image")
                    yield from vm.destroy()
                    raise
            else:
                LOG.debug("No build script for image %s" % name)
            yield from asyncio.sleep(4)
            yield from self.storage.snapshot(name)

    @asyncio.coroutine
    def _get_vm(self, local_cfg, conf):
        """
        :param local_cfg: config.job.runner.vms item
        :param conf: config.provider.vms item
        """
        LOG.debug("Creating VM with conf %s" % conf)
        name = local_cfg["name"]
        image = conf.get("image")
        if image:
            yield from self.build_image(image)
        else:
            image = name
        rnd_name = utils.get_rnd_name(name)
        yield from self.storage.clone(image, rnd_name)
        vm = VM(self, conf, local_cfg)
        files = yield from self.storage.list_files(rnd_name)
        for f in files:
            vm.add_disk(f)
        for net in conf["net"]:
            net = net.split(" ")
            if len(net) == 1:
                vm.add_net(net[0])
            else:
                vm.add_net(net[0], mac=net[1])
        yield from vm.boot()
        self.vms.append(vm)
        vm.storage_name = rnd_name # FIXME
        return vm

    @asyncio.coroutine
    def get_vms(self, vm_confs):
        """Return VMs for runner.

        :param vm_confs: config.job.runner.vms items
        """
        vms = []
        ifs = {}
        for vm_conf in vm_confs:
            conf = self.config["vms"][vm_conf["name"]]
            br = None
            net_conf = []
            for net in conf["net"]:
                ifname = net.split(" ")
                if ifname[0].endswith("%"):
                    if ifname[0] in ifs:
                        br = ifname[0] = ifs[ifname[0]]
                    else:
                        br = yield from self._get_bridge(ifname[0][:-1])
                        ifs[ifname[0]] = br
                        ifname[0] = br
                net_conf.append(" ".join(ifname))
            conf["net"] = net_conf
            vm = yield from self._get_vm(vm_conf, conf)
            self.br_vm.setdefault(br, [])
            self.br_vm[br].append(vm)
            vms.append(vm)
        return vms

    @asyncio.coroutine
    def cleanup_net(self):
        clean = []
        with (yield from DYNAMIC_BRIDGE_LOCK):
            for br, vms in self.br_vm.items():
                if not vms:
                    yield from self.ssh.run("ip link del %s" % br)
                    clean.append(br)
            for br in clean:
                del self.br_vm[br]

    @asyncio.coroutine
    def _get_bridge(self, prefix):
        with (yield from DYNAMIC_BRIDGE_LOCK):
            data = yield from self.ssh.run("ip link list", return_output=True)
            nums = set()
            for line in data.splitlines():
                m = IFACE_RE.match(line)
                if m:
                    if m.group(1) == prefix:
                        nums.add(int(m.group(2)))
            for i in range(len(nums) + 1):
                if i not in nums:
                    br = "%s%d" % (prefix, i)
                    break
            yield from self.ssh.run("ip link add %s type bridge" % br)
            yield from self.ssh.run("ip link set %s up" % br)
        return br


class Provider:

    def __init__(self, root, config):
        """
        :param config: full provider config
        """
        self.root = root
        self.config = config
        self.name = config["name"]
        self.key = config.get("key")
        self.ifs = {}
        self.get_vms_lock = asyncio.Lock()

    def start(self):
        self.hosts = [Host(c, self.config, self.root, self.key)
                      for c in self.config["hosts"]]
        self.mds = MetadataServer(self.root.loop,
                                  self.config.get("metadata_server", {}))
        self.mds_future = asyncio.async(self.mds.start())

    @asyncio.coroutine
    def cleanup(self, vms):
        LOG.debug("Starting cleanup %s" % vms)
        for vm in vms:
            LOG.debug("Cleaning %s" % vm)
            yield from vm.destroy()
        LOG.debug("Cleanup completed")

    @asyncio.coroutine
    def stop(self):
        yield from self.mds_future.cancel()

    @asyncio.coroutine
    def get_vms(self, vm_confs):
        """
        :param vm_confs: job.runner.vms
        """
        memory_required = self.config.get("freemb", 1024)
        for cfg in vm_confs:
            memory_required += self.config["vms"][cfg["name"]]["memory"]

        with (yield from self.get_vms_lock):
            while True:
                random.shuffle(self.hosts)
                for host in self.hosts:
                    yield from host.update_stats()
                    if host.free >= memory_required and host.la < self.config.get("maxla", 4):
                        LOG.debug("Chosen host: %s" % host)
                        return (yield from host.get_vms(vm_confs))
                yield from asyncio.sleep(30)

class VM:
    def __init__(self, host, cfg=None, local_cfg=None):
        """Represent a VM.

        :param host: Host instance
        :param cfg: config.provider.vms item

        """
        self.host = host
        self.cfg = cfg or {}
        self.local_cfg = local_cfg
        self._ssh = host.ssh
        self.macs = []
        self.bridges = []
        self.name = self.cfg.get("name", utils.get_rnd_name())
        x = XMLElement(None, "domain", type="kvm")
        self.x = x
        x.se("name").x.text = self.name
        for mem in ("memory", "currentMemory"):
            x.se(mem, unit="MiB").x.text = str(self.cfg.get("memory", 512))
        x.se("vcpu", placement="static").x.text = "1"
        cpu = x.se("cpu", mode="host-model")
        cpu.se("model", fallback="forbid")
        os = x.se("os")
        os.se("type", arch="x86_64", machine="pc-1.0").x.text = "hvm"
        features = x.se("features")
        features.se("acpi")
        features.se("apic")
        features.se("pae")
        self.devices = x.se("devices")
        self.devices.se("emulator").x.text = "/usr/bin/kvm"
        self.devices.se("controller", type="pci", index="0", model="pci-root")
        self.devices.se("graphics", type="spice", autoport="yes")
        mb = self.devices.se("memballoon", model="virtio")
        mb.se("address", type="pci", domain="0x0000", bus="0x00",
              slot="0x09", function="0x0")

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "<VM %s %s>" % (self.name, self.local_cfg)

    @asyncio.coroutine
    def run_script(self, script, env=None, raise_on_error=True, cb=None):
        yield from self.get_ip()
        LOG.debug("Running script: %s on vm %s with env %s" % (script, self, env))
        cmd = "".join(["%s='%s' " % tuple(e) for e in env.items()]) if env else ""
        cmd += script["interpreter"]
        ssh = asyncssh.AsyncSSH(script.get("user", "root"), self.ip,
                                key=self.host.vm_key, cb=cb)
        status = yield from ssh.run(cmd, stdin=script["data"],
                                    raise_on_error=raise_on_error,
                                    user=script.get("user", "root"))
        return status

    @asyncio.coroutine
    def shutdown(self, timeout=30, storage=False):
        if not hasattr(self, "ip"):
            yield from self.destroy(storage=storage)
            return
        ssh = yield from self.get_ssh()
        yield from ssh.run("shutdown -h now")
        deadline = time.time() + timeout
        cmd = "virsh list | grep -q {}".format(self.name)
        while True:
            yield from asyncio.sleep(4)
            error = yield from self._ssh.run(cmd, raise_on_error=False)
            if error:
                return
            elif time.time() > timeout:
                yield from self.destroy()
                return

    @asyncio.coroutine
    def destroy(self, storage=False):
        cmd = "virsh destroy {}".format(self.name)
        yield from self._ssh.run(cmd, raise_on_error=False)
        if storage:
            yield from self.host.storage.destroy(self.storage_name)
        for br in self.bridges:
            lst = self.host.br_vm.get(br)
            if lst and self in lst:
                lst.remove(self)
        yield from self.host.cleanup_net()

    @asyncio.coroutine
    def get_ssh(self):
        yield from self.get_ip()
        return asyncssh.AsyncSSH("root", self.ip, key=self.host.vm_key)

    @asyncio.coroutine
    def get_ip(self, timeout=60):
        if hasattr(self, "ip"):
            yield from asyncio.sleep(0)
            return self.ip
        deadline = time.time() + timeout
        cmd = "egrep -i '%s' /proc/net/arp" % "|".join(self.macs)
        while True:
            if time.time() > deadline:
                raise Exception("Unable to find ip of VM %s" % self.cfg)
            yield from asyncio.sleep(4)
            data = yield from self._ssh.run(cmd, return_output=True)
            for line in data.splitlines():
                m = IP_RE.match(line)
                if m:
                    self.ip = m.group(1)
                    # TODO: wait_for_ssh
                    yield from asyncio.sleep(8)
                    return

    @asyncio.coroutine
    def boot(self):
        conf = "/tmp/.conf.%s.xml" % utils.get_rnd_name()
        with self.fd() as fd:
            yield from self._ssh.run("cat > %s" % conf, stdin=fd)
        yield from self._ssh.run("virsh create {c}; rm {c}".format(c=conf))

    @contextlib.contextmanager
    def fd(self):
        xmlfile = tempfile.NamedTemporaryFile()
        try:
            fd = open(xmlfile.name, "w+b")
            et.ElementTree(self.x.x).write(fd)
            fd.seek(0)
            yield fd
        finally:
            fd.close()

    def add_disk(self, path):
        dev = os.path.split(path)[1].split(".")[0]
        LOG.debug("Adding disk %s with path %s" % (dev, path))
        disk = self.devices.se("disk", device="disk", type="file")
        disk.se("driver", name="qemu", type="qcow2", cache="unsafe")
        disk.se("source", file=path)
        disk.se("target", dev=dev, bus="virtio")

    def add_net(self, bridge, mac=None):
        if not mac:
            mac = utils.get_rnd_mac()
        net = self.devices.se("interface", type="bridge")
        net.se("source", bridge=bridge)
        net.se("model", type="virtio")
        net.se("mac", address=mac)
        self.macs.append(mac)
        self.bridges.append(bridge)


class XMLElement:

    def __init__(self, parent, *args, **kwargs):
        if parent is not None:
            self.x = et.SubElement(parent, *args, **kwargs)
        else:
            self.x = et.Element(*args, **kwargs)

    def se(self, *args, **kwargs):
        return XMLElement(self.x, *args, **kwargs)

    def write(self, fd):
        et.ElementTree(self.x).write(fd)

    def tostring(self):
        return et.tostring(self.x)


class MetadataServer:
    """Metadata server for cloud-init.

    Supported versions:
    * 2012-08-10
    """

    def __init__(self, loop, config):
        self.loop = loop
        self.config = config

    def get_metadata(self):
        keys = {}
        with open(self.config["authorized_keys"]) as kf:
            for i, line in enumerate(kf.readlines()):
                if line:
                    keys["key-" + str(i)] = line
        return json.dumps({
                "uuid": str(uuid.uuid4()),
                "availability_zone": "nova",
                "hostname": "rally-ci-vm",
                "launch_index": 0,
                "meta": {
                    "priority": "low",
                    "role": "rally-ci-test-vm",
                },
                "public_keys": keys,
                "name": "test"
        }).encode("utf8")

    @asyncio.coroutine
    def user_data(self, request):
        version = request.match_info["version"]
        if version in ("2012-08-10", "latest"):
            return web.Response(body=self.config["user_data"].encode("utf-8"))
        return web.Response(status=404)

    @asyncio.coroutine
    def meta_data(self, request):
        LOG.debug("Metadata request: %s" % request)
        version = request.match_info["version"]
        if version in ("2012-08-10", "latest"):
            md = self.get_metadata()
            LOG.debug(md)
            return web.Response(body=md, content_type="application/json")
        return web.Response(status=404)

    @asyncio.coroutine
    def start(self):
        self.app = web.Application(loop=self.loop)
        for route in (
                ("/openstack/{version:.*}/meta_data.json", self.meta_data),
                ("/openstack/{version:.*}/user_data", self.user_data),
        ):
            self.app.router.add_route("GET", *route)
        self.handler = self.app.make_handler()
        addr = self.config.get("listen_addr", "169.254.169.254")
        port = self.config.get("listen_port", 8080)
        self.srv = yield from self.loop.create_server(self.handler, addr, port)
        LOG.debug("Metadata server started at %s:%s" % (addr, port))

    @asyncio.coroutine
    def stop(self, timeout=1.0):
        yield from self.handler.finish_connections(timeout)
        self.srv.close()
        yield from self.srv.wait_closed()
        yield from self.app.finish()
