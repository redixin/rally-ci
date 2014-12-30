
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
            "level": "DEBUG",
        },
        "rallyci.virsh": {
            "level": "DEBUG",
        },
    }
}

logging.config.dictConfig(LOGGING)