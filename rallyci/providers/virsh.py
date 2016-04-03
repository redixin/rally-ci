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
import time
import os
import random
import re
import logging
import tempfile
from xml.etree import ElementTree as et

from clis import clis

from rallyci import base
from rallyci import utils
from rallyci.common.ssh import SSH


RE_LA = re.compile(r".*load average: (\d+\.\d+),.*")
RE_MEM = re.compile(r".*Mem: +(\d+) +\d+ +(\d+) +\d+ +\d+ +(\d+).*")
IFACE_RE = re.compile(r"\d+: ([a-z]+)(\d+): .*")
IP_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s")
VMEM_FACTOR = {"KiB": 1024, "MiB": 1024*1024}

class ZFS:

    def __init__(self, log, ssh, path, dataset, **kwargs):
        self.log = log
        self.ssh = ssh
        self.path = path
        self.dataset = dataset

    @asyncio.coroutine
    def create(self, name):
        cmd = ["zfs", "create", "/".join((self.dataset, name))]
        yield from self.ssh.run(cmd, stderr=print)

    @asyncio.coroutine
    def list_files(self, name):
        path = os.path.join(self.path, name)
        cmd = "ls %s" % path
        status, ls, err = yield from self.ssh.out(cmd, check=False)
        if status:
            raise Exception(err)
        return [os.path.join(path, f)
                for f in ls.splitlines()]

    @asyncio.coroutine
    def clone(self, src, dst):
        cmd = "zfs clone {dataset}/{src}@1 {dataset}/{dst}"
        cmd = cmd.format(dataset=self.dataset, src=src, dst=dst)
        yield from self.ssh.run(cmd, stderr=print)

    @asyncio.coroutine
    def exist(self, name):
        self.log.debug("Checking if image %s exist" % name)
        cmd = ["zfs", "list", "%s/%s@1" % (self.dataset, name)]
        return not (yield from self.ssh.run(cmd, check=False, stderr=print))

    @asyncio.coroutine
    def snapshot(self, name, snapshot="1"):
        cmd = "zfs snapshot {dataset}/{name}@{snapshot}".format(
                dataset=self.dataset, name=name, snapshot=snapshot)
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def destroy(self, name):
        cmd = "zfs destroy {dataset}/{name}".format(name=name,
                                                    dataset=self.dataset)
        return (yield from self.ssh.run(cmd, check=False))

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
        self.log.debug("Checking if image %s exist" % name)
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


class Host(base.BaseHost):

    def __init__(self, cfg, provider):
        """
        :param dict ssh_conf: item from hosts from provider
        :param Host host:
        """
        super().__init__(cfg, provider)

        self.config = provider.config

        self.log = self.provider.log
        self.image_locks = {}
        self._job_vms = {}
        self._job_brs = {}
        cfg.setdefault("username", "root")
        cfg["keys"] = self.provider.root.config.get_ssh_keys(keytype="private")
        self.ssh = SSH(self.provider.root.loop, **cfg)
        self.cpus = False
        self.la = 0.0
        self.free = 0
        storage_cf = self.config["storage"]
        self.storage = BACKENDS[storage_cf["backend"]](self.log, self.ssh, **storage_cf)
        self.bridge_lock = asyncio.Lock(loop=self.provider.root.loop)

    def __str__(self):
        return "<Host %s (la: %s, free: %s)>" % (self.ssh.hostname,
                                                 self.la, self.free)

    @asyncio.coroutine
    def update_stats(self):
        if not self.cpus:
            cmd = "cat /proc/cpuinfo | grep processor -c"
            status, data, err = yield from self.ssh.out(cmd)
            self.cpus = int(data)
        cmd = "uptime && free -b"
        err, data, err = yield from self.ssh.out(cmd)
        self.la = float(RE_LA.search(data, re.MULTILINE).group(1))
        mem = RE_MEM.search(data, re.MULTILINE)
        self.mem_total = int(mem.group(1))
        self.free = int(mem.group(2)) + int(mem.group(3))
        cmd = "virsh list --uuid --state-running"
        status, data, err = yield from self.ssh.out(cmd)
        self.vcpu = 0
        self.vmem_used = 0
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            cmd = "virsh dumpxml %s" % line
            status, data, err = yield from self.ssh.out(cmd)
            xml = et.fromstring(data)
            self.vcpu += int(xml.find("vcpu").text)
            vmem_element = xml.find("currentMemory")
            vmem = int(vmem_element.text)
            vmem += vmem * VMEM_FACTOR[vmem_element.attrib["unit"]]

    @asyncio.coroutine
    def build_image(self, name, job):
        self.log.info("Building image %s" % name)
        self.image_locks.setdefault(name,
                                    asyncio.Lock(loop=self.provider.root.loop))
        with (yield from self.image_locks[name]):
            if (yield from self.storage.exist(name)):
                self.log.debug("Found image %s" % name)
                return
            self.log.info("Image %s not found. Building..." % name)
            yield from self.storage.destroy(name)
            image_conf = self.provider.config["images"][name]
            parent = image_conf.get("parent")
            if parent:
                yield from self.build_image(parent, job)
            else:
                yield from self.storage.download(name, image_conf["url"])
            scripts = image_conf.get("scripts")
            if scripts:
                job_vm_conf = copy.deepcopy(image_conf)
                job_vm_conf["name"] = name
                vm = VM(self, job, job_vm_conf, image_conf, name)
                yield from vm.boot(clone=False)
                self.log.debug("Running build scripts for image %s" % name)
                error = yield from vm.run_scripts("scripts", out_cb=print, err_cb=print)
                if error:
                    self.log.debug("Failed to build %s" % name)
                    yield from vm.force_off()
                    yield from vm.destroy()
                    raise Exception("Failed to build %s" % name)
                yield from vm.shutdown()
            yield from asyncio.sleep(4)
            yield from self.storage.snapshot(name)

    @asyncio.coroutine
    def get_vms(self, job):
        vms = []
        for job_vm_conf in job.config["vms"]:
            vm_conf = self.provider.config["vms"][job_vm_conf["name"]]
            yield from self.build_image(vm_conf["image"], job)
            vm = VM(self, job, job_vm_conf, vm_conf)
            yield from vm.boot()
            vms.append(vm)
        return vms

    @asyncio.coroutine
    def get_bridge(self, job, prefix):
        with (yield from self.bridge_lock):
            job_brs = self._job_brs.get(job)
            if job_brs is None:
                job_brs = {}
                self._job_brs[job] = job_brs
            br = job_brs.get(prefix)
            if br:
                return br
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
            yield from self.ssh.run(["ip", "link", "set", br, "up"])
        return br


class Provider(base.BaseProvider):

    def __init__(self, root, config):
        """
        :param config: full provider config
        """
        super().__init__(root, config)

        self.log = root.log
        self.shutdown_event = asyncio.Event()
        self.name = config["name"]
        self.key = root.config.get_ssh_key()
        self.last = time.time()
        self._job_host_map = {}
        self._get_host_lock = asyncio.Lock(loop=root.loop)
        self._get_vm_lock = asyncio.Lock(loop=root.loop)

    @asyncio.coroutine
    def get_vms(self, job):
        host = yield from self._get_host(job)
        with (yield from self._host_lock[host]):
            return (yield from host.get_vms(job))

    @asyncio.coroutine
    def start(self):
        self.hosts = [Host(c, self)
                      for c in self.config["hosts"]]
        self._host_lock = dict(((h, asyncio.Lock(loop=self.root.loop))
                                 for h in self.hosts))
        mds_cfg = self.config.get("metadata_server", {})
        mds_addr = mds_cfg.get("listen_addr", "0.0.0.0")
        mds_port = mds_cfg.get("listen_port", 8088)
        self.mds = clis.Server(self.root.loop,
                               listen_addr=mds_addr,
                               listen_port=mds_port,
                               ssh_keys=self.root.config.get_ssh_keys())
        self.mds_future = asyncio.async(self.mds.run(), loop=self.root.loop)
        for host in self.hosts:
            cmd = "ip r get 169.254.169.254 | grep -c 'src 169.254.169.254'"
            status = yield from host.ssh.run(cmd, check=False)
            if status:
                cmd = "ip addr add 169.254.169.254/32 dev lo"
                yield from host.ssh.run(cmd)
            yield from host.ssh.forward_remote_port("169.254.169.254", 80,
                                                    mds_addr, mds_port)

    @asyncio.coroutine
    def stop(self):
        self.mds_future.cancel()
        yield from self.mds_future

    @asyncio.coroutine
    def _get_host(self, job):
        """
        :param Job job:
        """
        mem = 0
        vcpu = 0
        for vm in job.config["vms"]:
            vm = self.config["vms"][vm["name"]]
            mem += vm["memory"] * 1024 * 1024
            vcpu += vm.get("vcpu", 1)
        random.shuffle(self.hosts)
        mem_reserve = self.config.get("mem_reserve", 1024) * 1024 * 1024
        while True:
            for host in self.hosts:
                yield from host.update_stats()
                if host.la > host.cpus:
                    self.log.debug("Host %s is overloaded by la/cpu" % host)
                    continue
                if host.free < (mem + mem_reserve):
                    self.log.debug("Host %s is overloaded by memory" % host)
                    self.log.debug("%s < %s + %s" % (host.free, mem, mem_reserve))
                    continue
                if (mem + mem_reserve) > (host.mem_total - host.vmem_used):
                    msg = "Host %s is overloaded by vmem" % host
                    msg += " (%s>%s)" % (mem + mem_reserve,
                                         host.mem_total - host.vmem_used)
                    self.log.debug(msg)
                    continue
                if host.vcpu > host.cpus:
                    self.log.debug("Host %s is overloaded by vcpu" % host)
                    continue
                return host

            self.log.info("All servers are overloaded. Waiting.")
            wait = self.shutdown_event.wait()
            try:
                yield from asyncio.wait_for(wait, 10, loop=self.root.loop)
            except asyncio.TimeoutError:
                pass
            else:
                self.shutdown_event.clear()

class VM(base.BaseVM):

    def __init__(self, *args, **kwargs):
        """Represent a VM.

        :param Host host:
        :param str name:
        :param dict config: config.provider.vms item
        :param dict cfg: job.vms item

        """
        super().__init__(*args, **kwargs)

        self.log = self.host.log

        self.macs = []
        self.disks = []
        x = XMLElement(None, "domain", type="kvm")
        self.x = x
        x.se("name").x.text = self.name
        for mem in ("memory", "currentMemory"):
            x.se(mem, unit="MiB").x.text = str(self.vm_conf.get("memory", 1024))
        x.se("vcpu", placement="static").x.text = str(self.vm_conf.get("vcpu", 1))
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
    def shutdown(self, cmd="shutdown -h now", timeout=30, delay=4):
        ssh = yield from self.get_ssh("root")
        yield from ssh.run(cmd)
        yield from self._close_ssh()
        deadline = time.time() + timeout
        cmd = "virsh list | grep -q %s" % self.name
        while True:
            yield from asyncio.sleep(delay)
            error = yield from self.host.ssh.run(cmd, check=False)
            if error:
                return
            elif time.time() > deadline:
                self.log.debug(("Timeot waiting %s to shutdown. "
                                "Switching off.") % self)
                yield from self._close_ssh()
                yield from self.force_off()
                return

    @asyncio.coroutine
    def destroy(self):
        yield from self.host.storage.destroy(self.name)
        self.host.provider.shutdown_event.set()

    @asyncio.coroutine
    def _close_ssh(self):
        for ssh in self._ssh_cache.values():
            ssh.close()
        self._ssh_cache = {}

    @asyncio.coroutine
    def _get_ip(self, timeout=300):
        deadline = time.time() + timeout
        cmd = ["egrep", "-i", "|".join(self.macs), "/proc/net/arp"]
        while True:
            if time.time() > deadline:
                raise Exception("Unable to find ip of VM %s" % self.cfg)
            yield from asyncio.sleep(4)
            self.log.debug("Checking for ip for vm %s (%s)" % (self.name,
                                                          repr(self.macs)))
            err, data, err = yield from self.host.ssh.out(cmd, check=False)
            for line in data.splitlines():
                m = IP_RE.match(line)
                if m:
                    return m.group(1)

    @asyncio.coroutine
    def boot(self, clone=True):
        if clone:
            yield from self.host.storage.clone(self.vm_conf["image"], self.name)
        for disk in (yield from self.host.storage.list_files(self.name)):
            self._add_disk(disk)
        for net in self.vm_conf.get("net", ["virbr0"]):
            if " " in net:
                net, mac = net.split(" ")
            else:
                mac = None
            if net.endswith("%"):
                net = yield from self.host.get_bridge(self.job, net[:-1])
            self._add_net(net, mac)
        cf = "/tmp/.rci-%s.xml" % id(self)
        with self.fd() as fd:
            yield from self.host.ssh.run("cat > '%s'" % cf, stdin=fd)
        yield from self.host.ssh.run(["virsh", "create", cf], stderr=print)
        yield from self.host.ssh.run("rm %s" % cf)

    @asyncio.coroutine
    def force_off(self):
        yield from self._close_ssh()
        cmd = "virsh destroy %s" % self.name
        yield from self.host.ssh.run(cmd)

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

    def _add_disk(self, path):
        dev = os.path.split(path)[1].split(".")[0]
        self.log.debug("Adding disk %s with path %s" % (dev, path))
        disk = self.devices.se("disk", device="disk", type="file")
        disk.se("driver", name="qemu", type="qcow2", cache="unsafe")
        disk.se("source", file=path)
        disk.se("target", dev=dev, bus="virtio")

    def _add_net(self, bridge, mac=None):
        if not mac:
            mac = utils.get_rnd_mac()
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
