#!/usr/bin/env python

import log  # noqa
import config
import events
import signal
import sys


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
