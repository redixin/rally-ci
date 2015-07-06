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

from rallyci import utils
from rallyci.common import asyncssh

LOG = logging.getLogger(__name__)

IFACE_RE = re.compile(r"\d+: (.+)(\d+): .*")
IP_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s")
BUILDING_IMAGES = {}
DYNAMIC_BRIDGES = {}
DYNAMIC_BRIDGE_LOCK = asyncio.Lock()


class Class:

    @asyncio.coroutine
    def run(self, job):
        LOG.debug("Running job %r" % job)
        job.started_at = time.time()
        self.vms = []
        self.ssh = self.config.nodepools[self.cfg["nodepool"]].\
            get_ssh(job)
        self.ssh = yield from self.ssh
        job.started_at = time.time()
        for vm_conf in self.local["vms"]:
            vm = VM(self.ssh, vm_conf, self.cfg, job, self.config)
            yield from vm.build()
            self.vms.append(vm)
        for vm in self.vms:
            yield from vm.boot_vm()
        for vm in self.vms:
            status = yield from vm.run_scripts()
            if status:
                job.set_status("failed")
                return status
        job.set_status("success")

    @asyncio.coroutine
    def cleanup(self):
        for vm in self.vms:
            yield from vm.cleanup()


class VM:
    """Represent virsh domain.

    runner_conf is entry from the runners section
      module: ...
      key: /path/to/ssh/key
      scp-root: /path/to/files
      nodepool: ...
      images:
        img1:
          dataset: /tank/ds
          source: img@s
          build-scripts: ["s1", "s2"]
          build-net: ["br5"]
          build-memory: 1024
        img2:
          parent: img1
          build-scripts: ["s3"]
          build-net: ["br5"]
          build-memory: 1024
      vms:
        vm1: # self.runner_vm_conf
          image: img1
          memory: 2048
          net:
            - bridge: "br5"
            - dynamic-bridge: "dyn_br"
        vm2: # runner_vm_conf
          image: img2
          memory: 1024
          net:
            - bridge: "br5"

    vm_conf is section from job configuration:

      name: runner-name
      vms:
        - name: vm1 # self.vm_conf
          no_ip: true
          scripts: ["s1", "s2"]
        - name: vm2
          ip_env_var: RCI_VM2_IP
          scripts: ["s1", "s2"]

    """
    def __init__(self, h_ssh, vm_conf, runner_conf, job, config):
        self.h_ssh = h_ssh
        self.vm_conf = vm_conf
        self.runner_conf = runner_conf
        self.job = job
        self.config = config

        self.runner_vm_conf = self.runner_conf["vms"][vm_conf["name"]]

    def _get_source_image(self, image_name):
        """Get source for cloning. E.g tank/images/img@1"""
        image_cfg = self.runner_conf["images"][image_name]
        parent = image_cfg.get("parent")
        if parent:
            dataset, p = self._get_source_image(parent)
            return (dataset, parent)
        else:
            return (image_cfg["dataset"], image_cfg["source"])

    @asyncio.coroutine
    def _add_disks(self, xml, path):
        files = yield from self.h_ssh.run("ls /%s" % path, return_output=True)
        for f in files.splitlines():
            xml.add_disk(f.split(".")[0], "/%s/%s" % (path, f))

    @asyncio.coroutine
    def _get_dynamic_bridge(self, prefix):
        if not hasattr(self.job, "virsh_dynamic_bridges"):
            self.job.virsh_dynamic_bridges = {}
        br = self.job.virsh_dynamic_bridges.get(prefix)
        if not br:
            with (yield from DYNAMIC_BRIDGE_LOCK):
                data = yield from self.h_ssh.run("ip link list",
                                                 return_output=True)
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
    def _get_ip(self, macs):
        cmd = "egrep -i '%s' /proc/net/arp" % "|".join(macs)
        while True:
            yield from asyncio.sleep(4)
            data = yield from self.h_ssh.run(cmd, return_output=True)
            for line in data.splitlines():
                m = IP_RE.match(line)
                if m:
                    return m.group(1)

    @asyncio.coroutine
    def _setup_networks(self, xml, cfg):
        self.macs = []
        for net in cfg:
            mac = net.get("mac", utils.get_rnd_mac())
            br = net.get("bridge")
            if not br:
                br = self._get_dynamic_bridge(net["dynamic-bridge"])
                if asyncio.iscoroutine(br):
                    br = yield from br
            self.macs.append(mac)
            xml.add_net(br, mac)

    @asyncio.coroutine
    def _shutdown(self, ssh, xml, timeout=30):
        yield from ssh.run("shutdown -h now")
        start = time.time()
        while True:
            yield from asyncio.sleep(4)
            cmd = "virsh list | grep -q %s" % xml.name
            error = yield from self.h_ssh.run(cmd, raise_on_error=False)
            if error:
                return
            elif time.time() - start > timeout:
                cmd = "virsh destroy %s" % xml.name
                yield from self.h_ssh.run(cmd)
                yield from asyncio.sleep(4)
                return

    @asyncio.coroutine
    def run_scripts(self):
        status = 0
        for s in self.vm_conf.get("scripts", []):
            self.job.set_status("%s: running %s" % (self.vm_conf["name"], s))
            status = yield from self.run_script(self.ssh, s,
                                                raise_on_error=False)
            if status:
                break
        return status

    @asyncio.coroutine
    def run_script(self, ssh, script, raise_on_error=True):
        script = self.config.data["script"][script]
        LOG.debug("script: %s" % script)
        cmd = "".join(["%s='%s' " % env for env in self.job.env.items()])
        cmd += script["interpreter"]
        status = yield from ssh.run(cmd, stdin=script["data"],
                                    raise_on_error=raise_on_error,
                                    user=script.get("user", "root"))
        return status

    @asyncio.coroutine
    def build(self, image_name=None):
        if image_name is None:
            image_name = self.runner_vm_conf.get("image")
            if image_name is None:
                # FIXME
                yield from asyncio.sleep(1)
                return

        self.job.set_status("building %s" % image_name)
        LOG.debug("Building image: %s" % image_name)
        build_key = (self.h_ssh.hostname, image_name)
        BUILDING_IMAGES.setdefault(build_key, asyncio.Lock())
        with (yield from BUILDING_IMAGES[build_key]):
            self.dataset, image_source = self._get_source_image(image_name)
            cmd = "zfs list %s/%s@1" % (self.dataset, image_name)
            error = yield from self.h_ssh.run(cmd, raise_on_error=False)
            if not error:
                LOG.debug("Image %s already built." % image_name)
                return image_name
            # delete possibly stale image
            cmd = "zfs destroy %s/%s" % (self.dataset, image_name)
            yield from self.h_ssh.run(cmd, raise_on_error=False)
            # find source image
            image_conf = self.runner_conf["images"][image_name]
            parent = image_conf.get("parent")
            if parent:
                source = yield from self.build(parent)
                self.job.set_status("building %s" % image_name)
            else:
                source = image_source
            if "@" not in source:
                source += "@1"
            name = utils.get_rnd_name(prefix="rci_build_%s_" % image_name)
            xml = XML(name=name, memory=image_conf.get("memory", 1024))
            target = "/".join([self.dataset, image_name])
            try:
                cmd = "zfs clone %s/%s %s" % (self.dataset, source, target)
                yield from self.h_ssh.run(cmd)
                yield from self._add_disks(xml, target)
                mac = utils.get_rnd_mac()
                xml.add_net(image_conf.get("build-net", "virbr0"), mac)
                ssh = yield from self.boot(xml)
                image_conf = self.runner_conf["images"][image_name]
                LOG.debug("building image with image_conf %s" % image_conf)
                for script in image_conf.get("build-scripts", []):
                    yield from self.run_script(ssh, script)
                yield from self._shutdown(ssh, xml)
                yield from self.h_ssh.run("zfs snapshot %s@1" % target)
                return image_name
            except:
                LOG.exception("Error while building %s" % image_name)
                yield from self.h_ssh.run("virsh destroy %s" % xml.name,
                                          raise_on_error=False)
                yield from asyncio.sleep(4)
                yield from self.h_ssh.run("zfs destroy %s" % target,
                                          raise_on_error=False)
                raise

    @asyncio.coroutine
    def boot(self, xml):
        self.job.set_status("booting %s" % self.vm_conf["name"])
        with xml.fd() as fd:
            conf = "/tmp/.conf.%s.xml" % utils.get_rnd_name()
            yield from self.h_ssh.run("cat > %s" % conf, stdin=fd)
        yield from self.h_ssh.run("virsh create %s" % conf)
        yield from self.h_ssh.run("rm %s" % conf)
        if not self.runner_vm_conf.get("no_ip"):
            ip = yield from asyncio.wait_for(self._get_ip(xml.macs), 120)
            LOG.debug("Got ip: %s" % ip)
            ip_env_var = self.vm_conf.get("ip_env_var")
            if ip_env_var:
                self.job.env[ip_env_var] = ip
            yield from asyncio.sleep(4)
            return asyncssh.AsyncSSH("root", ip,
                                     key=self.runner_conf.get("key"),
                                     cb=self.job.logger)

    @asyncio.coroutine
    def boot_vm(self):
        LOG.debug("Booting VM %s" % self.vm_conf["name"])
        name = utils.get_rnd_name(prefix="rci_%s_" % self.vm_conf["name"])
        self.xml = XML(name=name,
                       memory=self.runner_vm_conf.get("memory", 1024))
        image = self.runner_vm_conf.get("image")
        if image:
            dataset, src = self._get_source_image(image)
            src = image
        else:
            dataset = self.runner_vm_conf["dataset"]
            src = self.runner_vm_conf["source"]
        if "@" not in src:
            src += "@1"
        self.volume = "%s/%s" % (dataset, utils.get_rnd_name())
        cmd = "zfs clone %s/%s %s" % (dataset, src, self.volume)
        yield from self.h_ssh.run(cmd)
        yield from self._add_disks(self.xml, self.volume)
        yield from self._setup_networks(self.xml, self.runner_vm_conf["net"])
        self.ssh = yield from self.boot(self.xml)

    @asyncio.coroutine
    def cleanup(self):
        try:
            for src, dst in self.vm_conf.get("scp", []):
                dst = os.path.join(self.runner_conf["scp-root"],
                                   self.job.log_path, dst)
                utils.makedirs(dst)
                yield from self.ssh.scp_get(src, dst)
        except Exception:
            LOG.exception("scp error")

        if hasattr(self, "xml"):
            yield from self.h_ssh.run("virsh destroy %s" % self.xml.name,
                                      raise_on_error=False)
            yield from asyncio.sleep(4)
            cmd = "zfs destroy %s" % self.volume
            yield from self.h_ssh.run(cmd)
        if hasattr(self.job, "virsh_dynamic_bridges"):
            for br in self.job.virsh_dynamic_bridges.values():
                yield from self.h_ssh.run("ip link del %s" % br)
            self.job.virsh_dynamic_bridges = {}


class XML:
    def __init__(self, name=None, memory=1024):
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
