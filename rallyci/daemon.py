#!/usr/bin/env python

import log
import config
import events
import sys

def run():
    cfg = config.Config()
    config_file = sys.argv[1]
    cfg.load_file(config_file)
    cfg.init()
    handler = events.EventHandler(cfg)
    handler.loop()
