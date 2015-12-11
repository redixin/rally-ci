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
import copy
import contextlib
import functools
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
from clis import clis

from rallyci import utils
from rallyci.common.ssh import SSH


LOG = logging.getLogger(__name__)

RE_LA = re.compile(r".*load average: (\d+\.\d+),.*")
RE_MEM = re.compile(r".*Mem: +\d+ +\d+ +(\d+) +\d+ +\d+ +(\d+).*")
IFACE_RE = re.compile(r"\d+: ([a-z]+)(\d+): .*")
IP_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s")
DYNAMIC_BRIDGES = {}
DYNAMIC_BRIDGE_LOCK = asyncio.Lock()


class ZFS:

    def __init__(self, ssh, path, dataset, **kwargs):
        self.ssh = ssh
        self.path = path
        self.dataset = dataset

    @asyncio.coroutine
    def create(self, name):
        cmd = ["zfs", "create", "/".join((self.dataset, name))]
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def list_files(self, name):
        cmd = "ls /{path}/{name}".format(path=self.path, name=name)
        err, ls, err = yield from self.ssh.out(cmd)
        return [os.path.join("/", self.dataset, name, f) for f in ls.splitlines()]

    @asyncio.coroutine
    def clone(self, src, dst):
        cmd = "zfs clone {dataset}/{src}@1 {dataset}/{dst}"
        cmd = cmd.format(dataset=self.dataset, src=src, dst=dst)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def exist(self, name):
        LOG.debug("Checking if image %s exist" % name)
        cmd = "zfs list"
        err, data, err = yield from self.ssh.out(cmd, check=False)
        r = re.search("^%s/%s " % (self.dataset, name), data, re.MULTILINE)
        return bool(r)

    @asyncio.coroutine
    def snapshot(self, name, snapshot="1"):
        cmd = "zfs snapshot {dataset}/{name}@{snapshot}".format(
                dataset=self.dataset, name=name, snapshot=snapshot)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def destroy(self, name):
        cmd = "zfs destroy {dataset}/{name}".format(name=name,
                                                    dataset=self.dataset)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def download(self, name, url):
        # TODO: cache
        yield from self.create(name)
        cmd = "wget -nv {url} -O {path}/{name}/vda.qcow2"
        cmd = cmd.format(name=name, path=self.path, url=url)
        yield from self.ssh.run(cmd)
        cmd = "qemu-img resize {path}/{name}/vda.qcow2 64G"
        cmd = cmd.format(name=name, path=self.path)
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
        err, ls, err = yield from self.ssh.out(cmd)
        return [os.path.join("/", self.path, name, f) for f in ls.splitlines()]

    @asyncio.coroutine
    def clone(self, src, dst):
        cmd = "btrfs subvolume delete {path}/{dst}"
        cmd = cmd.format(path=self.path, src=src, dst=dst)
        yield from self.ssh.run(cmd, check=False)
        cmd = "btrfs subvolume snapshot {path}/{src} {path}/{dst}"
        cmd = cmd.format(path=self.path, src=src, dst=dst)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def exist(self, name):
        LOG.debug("Checking if image %s exist" % name)
        cmd = "btrfs subvolume list %s" % self.path
        err, data, err = yield from self.ssh.out(cmd, check=False)
        r = re.search(" %s$" % name, data, re.MULTILINE)
        return bool(r)

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
        cmd = "wget -nv {url} -O /{path}/{name}/vda.qcow2"
        cmd = cmd.format(name=name, path=self.path, url=url)
        yield from self.ssh.run(cmd)
        # TODO: size should be set in config
        cmd = "qemu-img resize /{path}/{name}/vda.qcow2 64G"
        cmd = cmd.format(name=name, path=self.path)
        yield from self.ssh.run(cmd)


BACKENDS = {"btrfs": BTRFS, "zfs": ZFS}


class Host:

    def __init__(self, ssh_conf, config, root):
        """
        ssh_conf: item from hosts from provider
        :param dict config: full "provider" item
        """
        self.image_locks = {}
        self.config = config
        self.root = root
        self.br_vm = {}
        self.vms = []
        self.ssh = SSH(root.loop, **ssh_conf,
                       keys=root.config.get_ssh_keys(keytype="private"))
        self.la = 0.0
        self.free = 0
        storage_cf = config["storage"]
        self.storage = BACKENDS[storage_cf["backend"]](self.ssh, **storage_cf)

    def __str__(self):
        return "<Host %s (la: %s, free: %s)>" % (self.ssh.hostname,
                                                 self.la, self.free)

    @asyncio.coroutine
    def update_stats(self):
        cmd = "uptime && free -m"
        err, data, err = yield from self.ssh.out(cmd)
        self.la = float(RE_LA.search(data, re.MULTILINE).group(1))
        free = RE_MEM.search(data, re.MULTILINE).groups()
        self.free = sum(map(int, free))

    @asyncio.coroutine
    def boot_image(self, name):
        conf = self.config["images"][name]
        vm = VM(self, name, conf)
        vm.disks.append(name)
        for f in (yield from self.storage.list_files(name)):
            vm.add_disk(f)
        vm.add_net(conf.get("build-net", "virbr0"))
        yield from vm.boot()
        return vm

    @asyncio.coroutine
    def build_image(self, name):
        LOG.info("Building image %s" % name)
        self.image_locks.setdefault(name, asyncio.Lock(loop=self.root.loop))
        with (yield from self.image_locks[name]):
            if (yield from self.storage.exist(name)):
                LOG.debug("Image %s exist" % name)
                return
            image_conf = self.config["images"][name]
            parent = image_conf.get("parent")
            if parent:
                yield from self.build_image(parent)
                yield from self.storage.clone(parent, name)
            else:
                url = image_conf.get("url")
                if url:
                    yield from self.storage.download(name, url)
                    yield from self.storage.snapshot(name)
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
    def _get_vm(self, name, conf):
        """
        :param conf: config.provider.vms item
        """
        LOG.debug("Creating VM %s" % name)
        image = conf.get("image")
        if image:
            yield from self.build_image(image)
        else:
            image = name
        rnd_name = utils.get_rnd_name(name)
        yield from self.storage.clone(image, rnd_name)
        vm = VM(self, name, conf)
        files = yield from self.storage.list_files(rnd_name)
        vm.disks.append(rnd_name)
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
        return vm

    def _cleanup_vm(self, vm):
        print(vm)

    @asyncio.coroutine
    def get_vm_for_job(self, name, job):
        """
        :param str name: vm name
        :param Job job:
        """
        conf = copy.deepcopy(self.config["vms"][name])
        if "net" not in conf:
            conf["net"] = ["virbr0"]
        for net in conf["net"]:
            ifname = net.split(" ")
            if ifname[0].endswith("%"):
                number = self._job_bridge_numbers.get(job, {}).get(ifname[0])
                if not number:
                    number = yield from self._get_bridge(ifname[0][:-1])
                    self._job_bridge_numbers.setdefault(job, {})
                    self._job_bridge_numbers[job][ifname[0]] = number
                conf["net"][net].replace(ifname[0],
                                         ifname[0][:-1] + str(number))
        vm = yield from self._get_vm(name, conf)
        return vm

    @asyncio.coroutine
    def cleanup_net(self):
        clean = []
        with (yield from DYNAMIC_BRIDGE_LOCK):
            for br, vms in self.br_vm.items():
                if not vms:
                    yield from self.ssh.run(["ip", "link", "del", br])
                    clean.append(br)
            for br in clean:
                del self.br_vm[br]

    @asyncio.coroutine
    def _get_bridge(self, prefix):
        with (yield from DYNAMIC_BRIDGE_LOCK):
            err, data, err = yield from self.ssh.out(["ip", "link", "list"])
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
            yield from self.ssh.run(["ip", "link", "add", br,
                                     "type", "bridge"])
            yield from self.ssh.run(["ip", "link", "set", bt, "up"])
        return br


class Provider:

    def __init__(self, root, config):
        """
        :param config: full provider config
        """
        self.root = root
        self.config = config

        self.name = config["name"]
        self.key = root.config.get_ssh_key()
        self.last = time.time()
        self.get_vms_lock = asyncio.Lock(loop=root.loop)
        self._job_host_map = {}

    def get_stats(self):
        pass

    @asyncio.coroutine
    def start(self):
        self.hosts = [Host(c, self.config, self.root)
                      for c in self.config["hosts"]]
        mds_cfg = self.config.get("metadata_server", {})
        mds_addr = mds_cfg.get("listen_addr", "0.0.0.0")
        mds_port = mds_cfg.get("listen_port", 8088)
        self.mds = clis.Server(self.root.loop,
                               listen_addr=mds_addr,
                               listen_port=mds_port,
                               ssh_keys=self.root.config.get_ssh_keys())
        self.mds_future = asyncio.async(self.mds.run(), loop=self.root.loop)
        command = ("PREROUTING -d 169.254.169.254 -p tcp --dport 80 "
                   "-j DNAT --to-destination %s:%s")
        for host in self.hosts:
            if mds_addr == "0.0.0.0":
                my_addr = utils.get_local_address(host.ssh.hostname)
            else:
                my_addr = mds_addr
            cmd = command % (my_addr, mds_port)
            yield from host.ssh.run(("iptables -t nat -C %s ||"
                                     "iptables -t nat -I %s") % (cmd, cmd))

    @asyncio.coroutine
    def cleanup(self, vms):
        LOG.debug("Starting cleanup %s" % vms)
        for vm in vms:
            LOG.debug("Cleaning %s" % vm)
            yield from vm.destroy()
        LOG.debug("Cleanup completed")

    @asyncio.coroutine
    def stop(self):
        self.mds_future.cancel()
        yield from self.mds_future

    @asyncio.coroutine
    def get_vm(self, name, job):
        """
        :param str name: vm name
        :param Job job:
        """
        host = yield from self._get_host_for_job(job)
        return (yield from host.get_vm_for_job(name, job))

    @asyncio.coroutine
    def _get_host_for_job(self, job):
        host = self._job_host_map.get(job)
        if not host:
            host = yield from self._get_host()
            self._job_host_map[job] = host
        return host

    @asyncio.coroutine
    def _get_host(self):
        memory_required = self.config.get("freemb", 1024)
        best = None

        sleep = self.last + 1 - time.time()
        if sleep > 1:
            yield from asyncio.sleep(sleep)
        while best is None:
            random.shuffle(self.hosts)
            LOG.debug("Chosing from %s" % self.hosts)
            for host in self.hosts:
                yield from host.update_stats()
                if host.free >= memory_required and host.la < self.config.get("maxla", 4):
                    LOG.debug("Chosen host: %s" % host)
                    self.last = time.time()
                    return host
            LOG.info("All servers are overloaded. Waiting 30 seconds.")
            yield from asyncio.sleep(30)

class VM:
    def __init__(self, host, name, cfg=None):
        """Represent a VM.

        :param Host host:
        :param str name:
        :param dict cfg: config.provider.vms item

        """
        self.host = host
        self.cfg = cfg or {}
        self._ssh = host.ssh
        self.macs = []
        self.disks = []
        self.bridges = []
        self.name = utils.get_rnd_name(name)
        x = XMLElement(None, "domain", type="kvm")
        self.x = x
        x.se("name").x.text = self.name
        for mem in ("memory", "currentMemory"):
            x.se(mem, unit="MiB").x.text = str(self.cfg.get("memory", 1024))
        x.se("vcpu", placement="static").x.text = str(self.cfg.get("vcpu", 1))
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

    def __repr__(self):
        return "<VM %s>" % (self.name)

    @asyncio.coroutine
    def run_script(self, script, env=None, check=True):
        LOG.debug("Running script: %s on vm %s with env %s" % (script, self, env))
        yield from self.get_ip()
        cmd = script.get("interpreter", "/bin/bash -xe -s")
        ssh = yield from self.get_ssh(script.get("user", "root"))
        status = yield from ssh.run(cmd, stdin=script["data"], stdout=print, stderr=print, check=check)
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
            error = yield from self._ssh.run(cmd, check=False)
            if error:
                return
            elif time.time() > timeout:
                yield from self.destroy(storage=storage)
                return

    @asyncio.coroutine
    def destroy(self, storage=True):
        cmd = ["virsh", "destroy", self.name]
        yield from self._ssh.run(cmd, check=False)
        if storage:
            for disk in self.disks:
                yield from self.host.storage.destroy(disk)
        for br in self.bridges:
            lst = self.host.br_vm.get(br)
            if lst and self in lst:
                lst.remove(self)
        yield from self.host.cleanup_net()
        self.host.vms.remove(self)

    @asyncio.coroutine
    def get_ssh(self, user="root"):
        yield from self.get_ip()
        ssh = SSH(self.host.root.loop, self.ip, username=user,
                  keys=self.host.root.config.get_ssh_keys("private"))
        yield from ssh.wait()
        return ssh

    @asyncio.coroutine
    def get_ip(self, timeout=300):
        if hasattr(self, "ip"):
            yield from asyncio.sleep(0)
            return self.ip
        deadline = time.time() + timeout
        cmd = ["egrep", "-i", "|".join(self.macs), "/proc/net/arp"]
        while True:
            if time.time() > deadline:
                raise Exception("Unable to find ip of VM %s" % self.cfg)
            yield from asyncio.sleep(4)
            LOG.debug("Checking for ip for vm %s (%s)" % (self.name, repr(self.macs)))
            err, data, err = yield from self._ssh.out(cmd, check=False)
            for line in data.splitlines():
                m = IP_RE.match(line)
                if m:
                    self.ip = m.group(1)
                    return

    @asyncio.coroutine
    def boot(self):
        conf = "/tmp/.rci-%s.xml" % id(self)
        with self.fd() as fd:
            yield from self._ssh.run("cat > '%s'" % conf, stdin=fd)
        yield from self._ssh.run(["virsh", "create", conf])

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
