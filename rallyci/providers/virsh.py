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
import re
import logging
import tempfile
from xml.etree import ElementTree as et

import aiohttp
from aiohttp import web

from rallyci import utils
from rallyci.common import asyncssh

LOG = logging.getLogger(__name__)

IFACE_RE = re.compile(r"\d+: (.+)(\d+): .*")
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
        cmd = cmd.format(dataset=self.dataset, src=src,
                         dst=dst, snapshot=snapshot)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def snapshot(self, name, snapshot="0"):
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
        cmd = "wget {url} -O /{dataset}/{name}/vda.qcow2".format(name=name,
                                                                 url=url)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def destroy(self, name):
        cmd = "zfs destroy {dataset}/{name}".format(name=name,
                                                    dataset=self.dataset)
        yield from self.ssh.run(cmd)


class Node:

    def __init__(self, ssh_conf, config):
        """
        ssh_config: item from nodes from provider
        config: full "provider" item
        """
        self.config = config
        self.vms = []
        self.ssh = asyncssh.AsyncSSH(**ssh_conf)
        self.storage = ZFS(self.ssh, **config["storage"])

    @asyncio.coroutine
    def boot_image(self, conf):
        vm = VM(memory=conf.get("memory", 1024))
        for f in self.storage.list_files(conf["name"]):
            vm.add_disk(f)
        vm.add_net(config.get("build_net", "virbr0"))
        vm.boot()
        return vm

    @asyncio.coroutine
    def build_image(self, name):
        image_conf = self.config["images"][name]
        parent = image_conf.get("parent")
        if parent:
            self.build_image(parent)
            self.storage.clone(parent, name)
        else:
            url = image_conf.get("url")
            if url:
                self.storage.download(name, url)
        vm = self.boot_image(name)
        for script in image_conf["build_scripts"]:
            vm.run_script(script)
        vm.shutdown()
        yield from asyncio.sleep(4)
        self.storage.snapshot(name)

    @asyncio.coroutine
    def get_vm(self, name):
        conf = self.config.vms[name]
        image = conf["image"]
        IMAGE_LOCKS.setdefault(image, asyncio.Lock())
        with IMAGE_LOCKS[image]:
            if not self.storage.exist(image):
                yield from self.build_image(image)
        rnd_name = utils.get_rnd_name(name)
        self.storage.snapshot(name, rnd_name)
        vm = VM(memory=conf["memory"])
        for f in self.storage.list_files(rnd_name):
            vm.add_disk(f)
        for net in conf["net"]:
            # TODO: dymanic bridve/vlan
            vm.add_net(net)
        yield from vm.boot()
        self.vms.append(vm)
        vm.storage_name = rnd_name # FIXME
        return vm

    @asyncio.coroutine
    def del_vm(self, vm):
        vm.shutdown()
        self.vms.remove(vm)
        self.storage.destroy(vm.storage_name)

class MetadataServer:

    LAYOUT = {
        "/openstack/": "latest",
        "/latest/metadata/": "instance-id",
        #"/openstack/latest/user_data": "#!/bin/sh\necho ok",
        "/latest/metadata/instance-id": "TODO",
        "/openstack/latest/meta_data.json": "TODO",
    }

    def __init__(self, loop, config):
        self.loop = loop
        self.config = config

    @asyncio.coroutine
    def index(self, request):
        LOG.debug("Metadata request: %s" % request)
        text = self.LAYOUT.get(request.path)
        if text:
            return web.Response(text=text, content_type="text/plain")
        return web.Response(status=404)

    @asyncio.coroutine
    def start(self):
        self.app = web.Application(loop=self.loop)
        self.app.router.add_route("GET", "/{path:.*}", self.index)
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


class Provider:

    def __init__(self, root, config):
        self.root = root
        self.config = config

    def start(self):
        self.nodes = [Node(c, self.config) for c in self.config["nodes"]]
        self.mds = MetadataServer(self.root.loop,
                                  self.config.get("metadata_server", {}))
        self.mds_future = asyncio.async(self.mds.start())

    @asyncio.coroutine
    def stop(self):
        yield from self.mds_future.cancel()

    def get_node(self):
        node = self.nodes[0]
        vms = len(node.vms)
        for n in self.nodes:
            n_vms = len(n.vms)
            if n_vms < vms:
                node = n
                vms = n_vms
        return node

    def boot_vms(self, vm_names, task):
        vms = []
        node = self.get_node()
        for name in vm_names:
            vm = yield from node.get_vm(name)
            vms.append(vm)
        return vms

class VM:

    def __init__(self, ssh, name=None, memory=1024):
        self._ssh = ssh
        self.macs = []
        if name is None:
            self.name = utils.get_rnd_name()
        else:
            self.name = name
        x = XMLElement(None, "domain", type="kvm")
        self.x = x
        x.se("name").x.text = self.name
        for mem in ("memory", "currentMemory"):
            x.se(mem, unit="MiB").x.text = str(memory)
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

    @asyncio.coroutine
    def run_script(self, script, env=None, raise_on_error=True, key=None):
        if not hasattr(self, "ip"):
            self.ip = self.get_ip()
        LOG.debug("Running script: %s on node %s" % (script, self))
        cmd = "".join(["%s='%s' " % e for e in env]) if env else ""
        cmd += script["interpreter"]
        ssh = asyncssh.AsyncSSH(script.get("user", "root"), self.ip, key=key)
        status = yield from ssh.run(cmd, stdin=script["data"],
                                    raise_on_error=raise_on_error,
                                    user=script.get("user", "root"))
        return status

    @asyncio.coroutine
    def shutdown(self, timeout=30):
        yield from self.ssh.run("shutdown -h now")
        deadline = time.time() + timeout
        cmd = "virsh list | grep -q {}".format(xml.name)
        while True:
            yield from asyncio.sleep(4)
            error = yield from self._ssh.run(cmd, raise_on_error=False)
            if error:
                return
            elif time.time() > timeout:
                cmd = "virsh destroy {}".format(self.xml.name)
                yield from self._ssh.run(cmd)
                return

    @asyncio.coroutine
    def get_ip(self, macs, timeout=30):
        deadline = time.time() + timeout
        cmd = "egrep -i '%s' /proc/net/arp" % "|".join(macs)
        while True:
            if time.time() > deadline:
                return None
            yield from asyncio.sleep(4)
            data = yield from self._ssh.run(cmd, return_output=True)
            for line in data.splitlines():
                m = IP_RE.match(line)
                if m:
                    return m.group(1)

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

    def add_net(self, bridge, mac):
        net = self.devices.se("interface", type="bridge")
        net.se("source", bridge=bridge)
        net.se("model", type="virtio")
        net.se("mac", address=mac)
        self.macs.append(mac)


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
