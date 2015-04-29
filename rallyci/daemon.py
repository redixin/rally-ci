#!/usr/bin/env python
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.


from rallyci import root
from rallyci import log

import asyncio
import sys
import signal
import logging


LOG = logging.getLogger(__name__)

def run():
    if len(sys.argv) < 2:
        print("Usage\n\t%s <config.yaml>\n\n")
        sys.exit(1)
    config = sys.argv[1]
    loop = asyncio.get_event_loop()
    r = root.Root(loop)
    r.load_config(config)
    for signame in ("SIGINT", ):
        loop.add_signal_handler(getattr(signal, signame),
                                asyncio.async, r.stop())
    LOG.info("Daemon started. Entering event loop.")
    loop.run_forever()
