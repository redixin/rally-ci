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

import asyncio
import importlib
import logging
import logging.config
import yaml

LOG = logging.getLogger(__name__)


class Config:
    def __init__(self, root, args):
        self.root = root
        self._modules = {}
        self.data = {}
        self.args = args
        self.filename = args.filename

        with open(self.filename, "rb") as cf:
            self.raw_data = yaml.safe_load(cf)

        for item in self.raw_data:
            if len(item.keys()) > 1:
                raise ValueError("Invalid config entry %s" % item)
            key = list(item.keys())[0]
            value = list(item.values())[0]
            name = value.get("name")
            if name:
                self.data.setdefault(key, {})
                if name in self.data[key]:
                    raise ValueError("Duplicate name %s" % name)
                self.data[key][name] = value
            else:
                self.data.setdefault(key, [])
                self.data[key].append(value)

    @asyncio.coroutine
    def validate(self):
        yield from asyncio.sleep(0)

    def get_instance(self, cfg, *args, **kwargs):
        return self._get_module(cfg["module"]).Class(cfg, *args, **kwargs)

    def iter_instances(self, section):
        section = self.data.get(section, {})
        for config in section.values():
            cls = self._get_module(config["module"]).Class
            yield cls(self.root, **config)

    def iter_providers(self):
        for cfg in self.data.get("provider", {}).values():
            yield self._get_module(cfg["module"]).Provider(self.root, cfg)

    def _get_module(self, name):
        """Get module by name.

        Import module if it is not imported.
        """
        module = self._modules.get(name)
        if not module:
            module = importlib.import_module(name)
            self._modules[name] = module
        return module

    def configure_logging(self):
        LOGGING = {
            "version": 1,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(name)s:"
                              "%(levelname)s: %(message)s "
                              "(%(filename)s:%(lineno)d)",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": "DEBUG",
                    "formatter": "standard",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["console"],
                    "level": "DEBUG"
                }
            }
        }

        if self.args.quiet:
            LOGGING["loggers"][""]["handlers"].remove("console")
        elif self.args.verbose:
            LOGGING["handlers"]["console"]["level"] = "DEBUG"

        def _get_handler(key, value):
            return {
                "level": key.upper(),
                "filename": value,
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "standard"
            }

        default_log = {
            "debug": _get_handler,
            "error": _get_handler,
            "info": _get_handler,
        }

        if self.data.get("logging"):
            section = self.data.get("logging")[0]
            for key in section:
                if default_log.get(key):
                    LOGGING["handlers"][key] = default_log[key](key, section[key])
                    LOGGING["loggers"][""]["handlers"].append(key)
                else:
                    raise ValueError("Unknown logging level")

        logging.config.dictConfig(LOGGING)
