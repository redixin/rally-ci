#!/usr/bin/env python

import log
import config
import events

cfg = config.Config()
cfg.load(["/etc/rally-ci/", "etc/rally-ci"])
handler = events.EventHandler(cfg)
handler.loop()
