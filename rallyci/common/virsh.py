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

from rallyci.common import asyncssh
from rallyci import utils

LOG = logging.getLogger(__name__)
IFACE_RE = re.compile(r"\d+: (.+)(\d+): .*")
IP_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s")
NETWORKS = set()
BUILDING_IMAGES = {}
DYNAMIC_BRIDGE_LOCK = asyncio.Lock()

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
        yield from self.ssh.run(cmd)

    @asyncio.coroutine
    def init(self):
        self.cur_name = utils.get_rnd_name()
        try:
            yield from self._clone(self.name + "@1", self.cur_name)
        except:
            LOG.exception("Unable to clone %s" % self.name)
            return 254

    @asyncio.coroutine
    def create(self):
        yield from self._clone(self.src, self.name)
        self.cur_name = self.name

    @asyncio.coroutine
    def commit(self, name="1"):
        yield from self.ssh.run("zfs snapshot %s/%s@%s" % (self.dataset, self.name, name))

    @asyncio.coroutine
    def cleanup(self):
        # https://bugzilla.redhat.com/show_bug.cgi?id=1178150
        cmd = "zfs destroy %s/%s" % (self.dataset, self.cur_name)
        yield from asyncio.sleep(4)
        data = yield from self.ssh.run(cmd, return_output=True, raise_on_error=False)
        LOG.debug(data)

    @asyncio.coroutine
    def get_disks(self):
        cmd = "ls /%s/%s" % (self.dataset, self.cur_name)
        files = yield from self.ssh.run(cmd, return_output=True)
        return ["/%s/%s/%s" % (self.dataset, self.cur_name, f) for f in files.splitlines()]


class VM:

    def __init__(self, ssh, name, cfg, local, job, config):
        """
        :param cfg: vm config
        """
        self.name = name
        self.config = config
        self.local = local
        self.job = job
        self.h_ssh = ssh
        self.cfg = cfg
        self.volume = ZFSVolume(ssh, name, cfg)
        self.macs = []
        job.virsh_dynamic_bridges = {}

    def _get_rnd_mac(self):
        mac5 = ["%02x" % random.randint(0, 255) for i in range(5)]
        return "52:" + ":".join(mac5)

    @asyncio.coroutine
    def _get_ip(self):
        cmd = "egrep -i '%s' /proc/net/arp" % self.macs[0]
        while True:
            yield from asyncio.sleep(4)
            data = yield from self.h_ssh.run(cmd, return_output=True)
            for line in data.splitlines():
                m = IP_RE.match(line)
                if m:
                    return m.group(1)

    def _get_dynamic_bridge(self, prefix):
        br = self.job.virsh_dynamic_bridges.get(prefix)
        if not br:
            with (yield from DYNAMIC_BRIDGE_LOCK):
                data = yield from self.h_ssh.run("ip link list", return_output=True)
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
                yield from self.h_ssh.run("ip link add %s type bridge" % br)
                yield from self.h_ssh.run("ip link set %s up" % br)
        self.job.virsh_dynamic_bridges[prefix] = br
        return br

    @asyncio.coroutine
    def _setup_network(self):
        for net in self.cfg["net"]:
            mac = net.get("mac", self._get_rnd_mac())
            br = net.get("bridge")
            if not br:
                br = self._get_dynamic_bridge(net["dynamic-bridge"])
                if asyncio.iscoroutine(br):
                    br = yield from br
            self.macs.append(mac)
            self.xml.add_net(br, mac)

    @asyncio.coroutine
    def boot(self):
        self.xml = XML(self.cfg)
        files = yield from self.volume.get_disks()

        for path in files:
            dev = os.path.split(path)[1].split(".")[0]
            self.xml.add_disk(dev, path)

        yield from self._setup_network()

        with self.xml.fd() as fd:
            conf = utils.get_rnd_name()
            conf = "/tmp/.conf.%s.xml" % conf
            yield from self.h_ssh.run("cat > %s" % conf, stdin=fd)
        yield from self.h_ssh.run("virsh create %s" % conf)
        yield from self.h_ssh.run("rm %s"% conf)
        if not self.cfg.get("no_ip"):
            self.ip = yield from asyncio.wait_for(self._get_ip(), 120)
            LOG.debug("Got ip: %s" % self.ip)
            ip_env_var = self.local.get("ip_env_var")
            if ip_env_var:
                self.job.env[ip_env_var] = self.ip
        username = self.cfg.get("user", "root")
        yield from asyncio.sleep(4)

    @asyncio.coroutine
    def build(self):
        build_key = (self.h_ssh.hostname, self.volume.name)
        BUILDING_IMAGES.setdefault(build_key, asyncio.Lock())
        with (yield from BUILDING_IMAGES[build_key]):
            error = yield from self.volume.init()
            if error:
                yield from self.volume.create()
                try:
                    yield from self.boot()
                    for script in self.cfg.get("build-scripts", []):
                        script = self.config.data["scripts"][script]
                        yield from self.run_script(script)
                    yield from self.shutdown()
                    yield from self.volume.commit()
                    yield from self.volume.init()
                except:
                    LOG.exception("Error building image.")
                    yield from self.cleanup()
                    raise

    @asyncio.coroutine
    def run_script(self, script):
        LOG.debug("script: %s" % script)
        cmd = "".join(["%s='%s' " % env for env in self.job.env.items()])
        cmd += script["interpreter"]
        ssh = asyncssh.AsyncSSH(hostname=self.ip,
                                username=script.get("user", "root"),
                                key=self.cfg.get("key"),
                                cb=self.job.logger)
        yield from ssh.run(cmd, stdin=script["data"])

    @asyncio.coroutine
    def shutdown(self, timeout=30):
        ssh = asyncssh.AsyncSSH(hostname=self.ip,
                                username="root",
                                key=self.cfg.get("key"),
                                cb=self.job.logger)
        yield from ssh.run("shutdown -h now")
        start = time.time()
        while True:
            yield from asyncio.sleep(4)
            cmd = "virsh list | grep -q %s" % self.xml.name
            error = yield from self.h_ssh.run(cmd, raise_on_error=False)
            if error:
                return
            elif time.time() - start > timeout:
                cmd = "virsh destroy %s" % self.xml.name
                yield from self.h_ssh.run(cmd)
                yield from asyncio.sleep(4)
                return

    @asyncio.coroutine
    def cleanup(self):
        yield from self.h_ssh.run("virsh destroy %s" % self.xml.name, raise_on_error=False)
        yield from self.volume.cleanup()
        for br in self.job.virsh_dynamic_bridges.values():
            yield from self.h_ssh.run("ip link del %s" % br)
        self.job.virsh_dynamic_bridges = {}


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
        self.name = utils.get_rnd_name() + "_new"
        x = XMLElement(None, "domain", type="kvm")
        self.x = x
        x.se("name").x.text = self.name
        for mem in ("memory", "currentMemory"):
            x.se(mem, unit="MiB").x.text = str(cfg["memory"])
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

    def add_disk(self, dev, path):
        disk = self.devices.se("disk", device="disk", type="file")
        disk.se("driver", name="qemu", type="qcow2", cache="unsafe")
        disk.se("source", file=path)
        disk.se("target", dev=dev, bus="virtio")

    def add_net(self, bridge, mac):
        net = self.devices.se("interface", type="bridge")
        net.se("source", bridge=bridge)
        net.se("model", type="virtio")
        net.se("mac", address=mac)
