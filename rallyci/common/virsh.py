from xmlbuilder import XMLBuilder

import StringIO
import threading
import os
import random
import re
import string
import logging
import time

from rallyci import sshutils
from rallyci import utils

LOG = logging.getLogger(__name__)
IFACE_RE = re.compile("\d+: ([a-z]+)([0-9]+): .*")
NETWORKS = set()
LOCK = threading.Lock()


class ZFS(object):
    def __init__(self, ssh, source, **kwargs):
        self.ssh = ssh
        self.dataset, self.source = source.rsplit("/", 1)
        self.name = utils.get_rnd_name()
        self.dev = os.path.join("/dev", self.dataset, self.name)

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


class LVM(object):

    def __init__(self, ssh, source, vg, size, **kwargs):
        self.ssh = ssh
        self.vg = vg
        self.source = source
        self.size = size

    def build(self):
        self.name = utils.get_rnd_name()
        self.dev = os.path.join("/dev", self.vg, self.name)
        cmd_t = "lvcreate -n%s -L%s -s /dev/%s/%s"
        cmd = cmd_t % (self.name, self.size, self.vg, self.source)
        self.ssh.run(cmd)

    def cleanup(self):
        cmd = "lvremove -f /dev/%s/%s" % (self.vg, self.name)
        self.ssh.run(cmd)
        self.ssh.close()
        del(self.ssh)

DRIVERS = {"lvm": LVM, "zfs": ZFS}


class VM(object):

    def __init__(self, global_config, config, env=None):
        self.volumes = []
        self.ifs = []
        self.global_config = global_config
        self.config = config
        self.ssh = sshutils.SSH(*config["host"])
        self.name = utils.get_rnd_name()
        self.env = env

    def _get_rnd_mac(self):
        return "00:" + ":".join(["%02x" % random.randint(0, 255) for i in range(5)])

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

    def gen_xml(self):
        self.xml = XMLBuilder("domain", type="kvm")
        self.xml.name(self.name)
        self.xml.memory("%d" % self.config["memory"], unit="KiB")
        self.xml.currentMemory("%d" % self.config["memory"], unit="KiB")

        self.xml.vcpu("1", placement="static")
        with self.xml.cpu(mode="host-model"):
            self.xml.model(fallback="forbid")
        self.xml.os.type("hvm", arch="x86_64", machine="pc-i440fx-2.1")
        with self.xml.features:
            self.xml.acpi
            self.xml.apic
            self.xml.pae

        with self.xml.devices:
            self.xml.emulator("/usr/bin/kvm")
            self.xml.controller(type="pci", index="0", model="pci-root")
            self.xml.graphics(type="spice", autoport="yes")

            with self.xml.memballoon(model="virtio"):
                self.xml.address(type="pci", domain="0x0000", bus="0x00",
                                 slot="0x09", function="0x0")

            for num, vol in enumerate(self.volumes):
                with self.xml.disk(type="block", device="disk"):
                    self.xml.driver(name="qemu", type="raw", cache="directsync",
                                    io="native")
                    self.xml.source(dev=vol.dev)
                    self.xml.target(dev="vd%s" % string.lowercase[num],
                                    bus="virtio")
            for net in self.config["networks"]:
                net = net.split(" ")
                mac = self._get_rnd_mac() if len(net) < 2 else net[1]
                iface = net[0]
                if iface.endswith("%"):
                    iface = self._get_bridge(iface[:-1])
                with self.xml.interface(type="bridge"):
                    self.xml.source(bridge=iface)
                    self.xml.model(type="virtio")
                    self.xml.mac(address=mac)

    def get_ip(self, timeout=120):
        e = ~self.xml
        start = time.time()
        while 1:
            time.sleep(8)
            mac =  e.find("devices").find("interface").find("mac").get("address")
            mac = mac.lower()
            LOG.debug("Searching for mac %s" % mac)
            s, out, err = self.ssh.execute("cat /var/lib/dhcp/dhcpd.leases")
            for l in out.splitlines():
                l = l.lower()
                if l.startswith("lease "):
                    ip = l.split(" ")[1]
                elif ("hardware ethernet %s;" % mac) in l:
                    time.sleep(5)
                    return ip
            if time.time() - start > timeout:
                raise Exception('timeout')


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
