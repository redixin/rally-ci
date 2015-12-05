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

from rallyci import utils

COMMON_OPTS = (("-B", "backingstore"), )
CREATE_OPTS = (("--zfsroot", "zfsroot"), )


class Provider(BaseProvider):
    def __init__(self, root, cfg):
        """
        :param dict cfg: provider config
        """
        self.root = root
        self.cfg = cfg
        self._building_images = collections.defaultdict(
                functools.partial(asyncio.Event, loop=root.loop))

        self._opts = list(self._get_opts(COMMON_OPTS))
        self._create_opts = list(self._get_opts(CREATE_OPTS))
        self._create_opts.extend(self._opts)

    def _get_opts(self, opts):
        for opt, name in opts:
            opt_value = self.cfg.get(name)
            if opt_value:
                yield [opt, opt_value]

    @asyncio.coroutine
    def _build_image(self, host, image):
        image_cfg = self.cfg["images"][image]
        cmd = ["lxc-create", "--name", image, *self._create_opts]
        cmd.extend(["-t", image_cfg["template"],
                    "--", image_cfg.get("args", "")])
        with self._build_images[image]:
            yield from host.ssh.run(cmd)

    @asyncio.coroutine
    def get_vm(self, image, job):
        host = yield from self._get_host()
        cmd = ["lxc-info", "--name", image]
        no_image = yield from host.run(cmd, check=False)
        if no_image:
            yield from self._build_image(host, image)
        name = utils.get_rnd_name("vm_")
        cmd = ["lxc-clone", "-s", image, "-n", name, *self._opts]
        yield from host.ssh.run(cmd)
        yield from host.ssh.run(["lxc-start", "-d", "-n", name])

    @asyncio.coroutine
    def boot(self, name):
        pass

    @asyncio.coroutine
    def cleanup(self):
        pass
