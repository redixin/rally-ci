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

import asyncio
import sys
import signal


def run():
    loop = asyncio.get_event_loop()
    r = root.Root(loop)
    loop.add_signal_handler(signal.SIGINT, r.stop_event.set)
    loop.add_signal_handler(signal.SIGHUP, r.reload_event.set)
    r.load_config()
    loop.run_until_complete(r.run())
