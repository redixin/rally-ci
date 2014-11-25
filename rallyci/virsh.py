
import sshutils

from xmlbuilder import XMLBuilder

import StringIO
import random
import string
import logging
import time

LOG = logging.getLogger(__name__)
PREFIX = "rci_"


def get_rnd_name(length=10):
    return PREFIX + "".join(random.sample(string.letters, length))


class Env(object):

    def __init__(self, global_config, config, **kwargs):
        self.env = {}
        self.vms = []
        self.global_config = global_config
        self.config = config
        self.kwargs = kwargs

    def build(self):
        for vm_conf in self.config["create-vms"]:
            vm = VM(self.global_config, vm_conf)
            vm.build()
            ip_env_var = vm_conf.get("ip_env_var")
            if ip_env_var:
                self.env[ip_env_var] = vm.get_ip()
            self.vms.append(vm)

    def cleanup(self):
        for vm in self.vms:
            vm.cleanup()


class VM(object):

    def __init__(self, global_config, config):
        self.volumes = []
        self.global_config = global_config
        self.config = config
        self.ssh = sshutils.SSH(*config["host"])
        self.name = get_rnd_name()

    def _get_rnd_mac(self):
        return "00:" + ":".join(["%02x" % random.randint(0, 255) for i in range(5)])

    def gen_xml(self):
        self.xml = XMLBuilder("domain", type="kvm")
        self.xml.name(self.name)
        self.xml.memory("%d" % self.config["memory"], unit="KiB")
        self.xml.currentMemory("%d" % self.config["memory"], unit="KiB")

        self.xml.vcpu("1", placement="static")
        with self.xml.cpu(mode='host-model'):
            self.xml.model(fallback='forbid')
        self.xml.os.type("hvm", arch="x86_64", machine="pc-i440fx-2.1")
        with self.xml.features:
            self.xml.acpi
            self.xml.apic
            self.xml.pae

        with self.xml.devices:
            self.xml.emulator("/usr/bin/kvm")
            self.xml.controller(type='pci', index='0', model='pci-root')
            self.xml.graphics(type='spice', autoport='yes')

            with self.xml.memballoon(model='virtio'):
                self.xml.address(type='pci', domain='0x0000', bus='0x00',
                                 slot='0x09', function='0x0')

            for num, vol in enumerate(self.volumes):
                with self.xml.disk(type="block", device="disk"):
                    self.xml.driver(name="qemu", type="raw", cache="none",
                                    io="native")
                    self.xml.source(dev=vol.dev)
                    self.xml.target(dev="vd%s" % string.lowercase[num],
                                    bus="virtio")
            for net in self.config["networks"]:
                with self.xml.interface(type="bridge"):
                    self.xml.source(bridge=net)
                    self.xml.model(type="virtio")
                    self.xml.mac(address=self._get_rnd_mac())

    def get_ip(self, timeout=120):
        e = ~self.xml
        start = time.time()
        while 1:
            time.sleep(5)
            mac =  e.find("devices").find("interface").find("mac").get("address")
            s, out, err = self.ssh.execute("cat /var/lib/dhcp/dhcpd.leases")
            for l in out.splitlines():
                if l.startswith("lease "):
                    ip = l.split(" ")[1]
                elif ("hardware ethernet %s;" % mac) in l:
                    return ip
            if time.time() - start > timeout:
                return "TIMEOUT"


    def build(self):
        for v in self.config["volumes"]:
            volume = LVM(self.ssh, **v)
            volume.build()
            self.volumes.append(volume)

        self.gen_xml()
        xml = StringIO.StringIO(str(self.xml))
        self.ssh.run("cat > /tmp/%s.xml" % self.name, stdin=xml)
        self.ssh.run("virsh create /tmp/%s.xml" % self.name)

    def cleanup(self):
        self.ssh.run("virsh destroy %s" % self.name)
        for v in self.volumes:
            v.cleanup()


class LVM(object):

    def __init__(self, ssh, source, vg, size, **kwargs):
        self.ssh = ssh
        self.vg = vg
        self.source = source
        self.size = size

    def build(self):
        self.name = get_rnd_name()
        self.dev = "/dev/%s/%s" % (self.vg, self.name)
        cmd_t = "lvcreate -n%s -L%s -s /dev/%s/%s"
        cmd = cmd_t % (self.name, self.size, self.vg, self.source)
        self.ssh.run(cmd)

    def cleanup(self):
        cmd = "lvremove -f /dev/%s/%s" % (self.vg, self.name)
        self.ssh.run(cmd)


if __name__ == "__main__":
    from rallyci import config
    import log
    conf = config.Config()
    conf.load_file("../config/config.yaml")
    conf.init()
    c = conf.environments[0]
    e = Env(conf, c)
    e.build()
    print e.env
    e.cleanup()
