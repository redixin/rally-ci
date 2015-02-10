#!/usr/bin/env python

import log  # noqa
import config
import events
import sys


def run():
    if len(sys.argv) < 3:
        print "Usage:\n\t%s <config_file> <log_file>\n" % sys.argv[0]
        sys.exit(1)
    cfg = config.Config()
    config_file = sys.argv[1]
    cfg.load_file(config_file)
    cfg.init()
    handler = events.EventHandler(cfg)
    handler.loop()
