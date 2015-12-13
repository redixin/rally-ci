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

from rallyci import utils


class Config:
    def __init__(self, root, filename, verbose):
        self.root = root
        self.filename = filename
        self.verbose = verbose

        self.data = {}
        self._modules = {}
        self._configured_projects = set()
        self._vm_provider_map = {}

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
                    raise ValueError("Duplicate name %s (%s)" % (name, self.data[key]))
                self.data[key][name] = value
            else:
                self.data.setdefault(key, [])
                self.data[key].append(value)
        utils.expand_jobs(self.data)
        for matrix in self.data.get("matrix", {}).values():
            for project in matrix["projects"]:
                self._configured_projects.add(project)

        for provider, config in self.data["provider"].items():
            for vm in config["vms"]:
                if vm in self._vm_provider_map:
                    raise ValueError("Duplicate vm %s" % vm)
                self._vm_provider_map[vm] = provider

    def get_value(self, value):
        return self.data["rally-ci"][0].get(value)

    def get_ssh_key(self, keytype="public", name="default"):
        return self.data["ssh-key"][name][keytype]

    def get_ssh_keys(self, keytype="public"):
        return [k[keytype] for k in self.data["ssh-key"].values()]

    def is_project_configured(self, project):
        return project in self._configured_projects

    def get_provider(self, vm):
        return self.root.providers[self._vm_provider_map[vm]]

    @asyncio.coroutine
    def validate(self):
        yield from asyncio.sleep(0)

    def get_instance(self, cfg, class_name, *args, **kwargs):
        module = self._get_module(cfg["module"])
        return getattr(module, class_name)(cfg, *args, **kwargs)

    def iter_instances(self, section, class_name):
        section = self.data.get(section, {})
        for config in section.values():
            module = self._get_module(config["module"])
            yield getattr(module, class_name)(self.root, **config)

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

        if self.verbose:
            LOGGING["handlers"]["console"]["level"] = "DEBUG"
        else:
            LOGGING["loggers"][""]["handlers"].remove("console")

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
