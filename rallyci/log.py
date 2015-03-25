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

import sys
import logging
import logging.config
import threading


if len(sys.argv) > 1:
    logfile = sys.argv[2]
else:
    logfile = "/var/log/rally-ci/daemon.log"


class ThreadNameFilter(logging.Filter):
    def filter(self, record):
        record.thread_name = threading.currentThread().getName()
        return True


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(thread_name)s: %(asctime)s %(name)s:"
                      "%(levelname)s: %(message)s "
                      "(%(filename)s:%(lineno)d)",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "filters": {
        "ThreadNameFilter": {
            "()": ThreadNameFilter,
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "formatter": "standard",
            "filters": ["ThreadNameFilter"],
            "class": "logging.StreamHandler",
        },
        "rotate_file": {
            "filters": ["ThreadNameFilter"],
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": logfile,
            "encoding": "utf-8",
            "maxBytes": 10000000,
            "backupCount": 128,
        }
    },
    "loggers": {
        "": {
            "handlers": ["console", "rotate_file"],
            "level": "DEBUG",
        },
        "paramiko": {
            "level": "WARNING",
        },
        "rallyci.virsh": {
            "level": "DEBUG",
        },
    }
}

logging.config.dictConfig(LOGGING)
