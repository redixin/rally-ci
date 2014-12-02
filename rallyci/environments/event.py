
import base


class Environment(base.Environment):

    def check_config(config):
        pass

    def build(self):
        for k, v in self.config["export-event"].items():
            value = dict(self.job.event)
            for key in v.split("."):
                value = value[key]
            self.env[k] = value

    def cleanup(self):
        pass
