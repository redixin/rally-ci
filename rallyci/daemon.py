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

import signal
import sys

from rallyci import config
from rallyci import events


cfg = config.Config(sys.argv[1])


def handle_term(signo, frame):
    sys.exit(0)


def handle_hup(signo, frame):
    cfg.need_reload = True


def run():
    if len(sys.argv) < 3:
        print "Usage:\n\t%s <config_file> <log_file>\n" % sys.argv[0]
        sys.exit(1)

    signal.signal(signal.SIGHUP, handle_hup)

    handler = events.EventHandler(cfg)
    handler.loop()
