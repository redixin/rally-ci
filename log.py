
import logging.config

LOGGING = {
        'version': 1,
        'formatters': {
            'standard': {
                'format': '%(asctime)s %(name)s:%(levelname)s: %(message)s '
                '(%(filename)s:%(lineno)d)',
                'datefmt': "%Y-%m-%d %H:%M:%S",
                }
            },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
                },
            'rotate_file': {
                'level': 'DEBUG',
                'formatter': 'standard',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': '/var/log/rally-ci/daemon.log',
                'encoding': 'utf8',
                'maxBytes': 10000000,
                'backupCount': 128,
                }
            },
        'loggers': {
            '': {
                'handlers': ['console', 'rotate_file'],
                'level': 'DEBUG',
                },
            }
        }

logging.config.dictConfig(LOGGING)
