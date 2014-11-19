#!/usr/bin/env python

import config
import events
import sys
import logging.config

cfg = config.Config()
config_file = sys.argv[1]
cfg.load_file(config_file)
logging.config.dictConfig(cfg.daemon["logging"])
handler = events.EventHandler(cfg)
handler.loop()
