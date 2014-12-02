
import abc


class Environment:
    __metaclass__ = abc.ABCMeta

    def __init__(self, global_config, config, job):
        self.global_config = global_config
        self.config = config
        self.job = job
        self.env = config.get("export", {})

    @staticmethod
    @abc.abstractmethod
    def check_config(config):
        """Check configuration

        Should return None if success, or string with error description.
        :param config: configuration dictionary
        """
        pass

    @abc.abstractmethod
    def build(self):
        pass

    @abc.abstractmethod
    def cleanup(self):
        pass
