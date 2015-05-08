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
import tempfile
import os
import random
import re
import string
import logging
import time
from xml.etree import ElementTree as et

from rallyci import utils

LOG = logging.getLogger(__name__)
IFACE_RE = re.compile("\d+: ([a-z]+)([0-9]+): .*")
NETWORKS = set()
BUILDING_IMAGES = {}


class ZFSVolume:

    def __init__(self, ssh, name, cfg):
        self.ssh = ssh
        self.name = name
        self.cfg = cfg
        self.dataset = cfg["dataset"]
        self.src = cfg["source"]

    @asyncio.coroutine
    def _clone(self, src, dst):
        src = "%s/%s" % (self.dataset, src)
        dst = "%s/%s" % (self.dataset, dst)
        cmd = "zfs clone %s %s" % (src, dst)
        retval = yield from self.ssh.run(cmd, raise_on_error=False)
        return retval

    @asyncio.coroutine
    def init(self):
        self.cur_name = utils.get_rnd_name()
        retval = yield from self._clone(self.name + "@1", self.cur_name)
        return retval

    @asyncio.coroutine
    def create(self):
        retval = yield from self._clone(self.src, self.name)
        if retval:
            raise Exception("No source image")
        self.cur_name = self.name

    @asyncio.coroutine
    def commit(self, name="1"):
        yield from self.ssh.run("zfs snapshot %s/%s@%s" % (self.dataset, self.name, name))

    @asyncio.coroutine
    def cleanup(self):
        # https://bugzilla.redhat.com/show_bug.cgi?id=1178150
        yield from asyncio.sleep(10)
        yield from self.ssh.run("zfs destroy %s/%s" % (self.dataset, self.cur_name))

    @asyncio.coroutine
    def get_disks(self):
        cmd = "ls /%s/%s" % (self.dataset, self.cur_name)
        files = yield from self.ssh.run(cmd, return_output=True)
        return files.splitlines()


class VM:

    def __init__(self, ssh, vm_name, cfg):
        self.h_ssh = ssh
        self.cfg = cfg
        self.vm_config = cfg["vms"][vm_name]
        self.volume = ZFSVolume(ssh, vm_name, self.vm_config)

    def boot(self):
        files = yield from self.volume.get_disks()
        LOG.debug("files: %r" % files)

    @asyncio.coroutine
    def build(self):
        build_key = (self.h_ssh.hostname, self.volume.name)
        BUILDING_IMAGES.setdefault(build_key, asyncio.Lock())
        with (yield from BUILDING_IMAGES[build_key]):
            error = yield from self.volume.init()
            if error:
                yield from self.volume.create()
                yield from self.boot()
                for script in self.vm_config.get("build-scripts", []):
                    error = yield from self.run_script(script)
                    if error:
                        self.cleanup()
                        return error
                yield from self.volume.commit()
                yield from self.volume.init()
        self.xml = XML(self.vm_config)

    @asyncio.coroutine
    def run_script(self, script):
        yield from self.h_ssh.run("echo ooke")

    @asyncio.coroutine
    def cleanup(self):
        yield from self.volume.cleanup()


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

class XML:

    def __init__(self, cfg):
        self.cfg = cfg
        x = XMLElement(None, "domain", type="kvm")
        self.x = x
        x.se("name").x.text = utils.get_rnd_name()
        for mem in ("memory", "currentMemory"):
            x.se("memory", unit="MiB").x.text = cfg["memory"]
        x.se("vcpu", placement="static").x.text = "1"
        cpu = x.se("cpu", mode="host-model")
        cpu.se("model", fallback="forbid")
        os = x.se("os")
        os.se("type", arch="x86_64", machine="pc-0.1").x.text = "hvm"
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

    def add_disk(self, path, dev):
        disk = self.devices.se("disk", device="disk", type="file")
        disk.se("driver", name="qemu", type="qcow2", cache="unsafe")
        disk.se("source", file=path)
        disk.se("target", dev=dev, bus="virtio")

    def add_net(self, iface, mac=None):
        if mac is None:
            mac5 = ["%02x" % random.randint(0, 255) for i in range(5)]
            mac = "00:" + ":".join(mac5)
        net = self.devices.se("interface", type="bridge")
        net.se("source", bridge=iface)
        net.se("model", type="virtio")
        net.se("mac", address=mac)


class DevVolMixin(object):
    num = 0

    def gen_xml(self, xml):
        with xml.disk(type="block", device="disk"):
            xml.driver(name="qemu", type="raw",
                       cache="directsync", io="native")
            xml.source(dev=self.dev)
            xml.target(dev="vd%s" % string.lowercase[self.num], bus="virtio")
        self.num += 1


class ZFS(DevVolMixin):
    def __init__(self, ssh, source, **kwargs):
        self.ssh = ssh
        self.dataset, self.source = source.rsplit("/", 1)
        self.name = utils.get_rnd_name()
        self.dev = os.path.join("/dev/zvol", self.dataset, self.name)

    def build(self):
        LOG.info("Creating zfs volume %s" % self.name)
        cmd = "zfs clone %(dataset)s/%(src)s %(dataset)s/%(dst)s" % {
                "src": self.source, "dst": self.name, "dataset": self.dataset}
        self.ssh.run(cmd)

    def cleanup(self):
        time.sleep(5)
        # remove sleep when (if) this is fixed:
        # https://bugzilla.redhat.com/show_bug.cgi?id=1178150
        LOG.info("Removing zfs volume %s" % self.name)
        cmd = "zfs destroy %(dataset)s/%(name)s" % {
                "name": self.name, "dataset": self.dataset}
        self.ssh.run(cmd)
        self.ssh.close()
        del(self.ssh)


class ZFSDir(object):
    num = 0

    def __init__(self, ssh, dataset, source, **kwargs):
        self.ssh = ssh
        self.dataset = dataset
        self.source = source
        self.name = utils.get_rnd_name()

    def build(self):
        cmd = "zfs clone {ds}/{src} {ds}/{dst}".format(ds=self.dataset,
                                                       src=self.source,
                                                       dst=self.name)
        self.ssh.run(cmd)


    def cleanup(self):
        self.ssh.run("zfs destroy %s/%s" % (self.dataset, self.name))



class OLDVM:
    def __init__(self, config, host_ssh):
        self.host_ssh = host_ssh
        self.volumes = []
        self.ifs = []
        self.config = config
        self.ssh = sshutils.SSH(**config["ssh"])
        self.name = utils.get_rnd_name()
        self.env = env


    def _get_bridge(self, prefix):
        iface = self.env.ifs.get(prefix)
        if iface:
            return iface
        nums = set()
        with LOCK:
            s, o, e = self.ssh.execute("ip link list")
            for l in o.splitlines():
                m = IFACE_RE.match(l)
                if m:
                    if m.group(1) == prefix:
                        nums.add(int(m.group(2)))
            for i in range(len(nums) + 1):
                if i not in nums:
                    iface = "%s%d" % (prefix, i)
                    break
            self.ssh.run("ip link add %s type bridge" % iface)
            self.ssh.run("ip link set %s up" % iface)
            self.ifs.append(iface)
            if self.env:
                self.env.ifs[prefix] = iface
            return iface

    @asyncio.coroutine
    def get_ip(self):
        e = ~self.xml
        ifs = e.find("devices").find("interface")
        mac = ifs.find("mac").get("address").lower()
        while True:
            yield from asyncio.sleep(2)
            LOG.debug("Searching for mac %s" % mac)
            cmd = "cat /var/lib/dhcp/dhcpd.leases"
            out = yield from self.h_ssh.run(cmd, return_output=True)
            for l in out.splitlines():
                l = l.lower()
                if l.startswith("lease "):
                    ip = l.split(" ")[1]
                elif ("hardware ethernet %s;" % mac) in l:
                    return ip

    def build(self):
        for v in self.config["volumes"]:
            volume = DRIVERS[v["driver"]](self.ssh, **v)
            volume.build()
            self.volumes.append(volume)

        self.gen_xml()
        xml = StringIO.StringIO(str(self.xml))
        self.ssh.run("cat > /tmp/%s.xml" % self.name, stdin=xml)
        self.ssh.run("virsh create /tmp/%s.xml" % self.name)

    def cleanup(self):
        self.ssh.run("virsh destroy %s" % self.name)
        while self.volumes:
            v = self.volumes.pop()
            v.cleanup()
        for i in self.ifs:
            self.ssh.run("ip link del %s" % i)
        self.ssh.close()
        del(self.ssh)
