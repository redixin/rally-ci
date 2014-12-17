
import abc

class Runner:
    __metaclass__ = abc.ABCMeta

    def __init__(self, config, global_config):
        self.config = config
        self.global_config = global_config

    @abc.abstractmethod
    def setup(self, **kwargs):
        pass

    def boot(self):
        pass

    @abc.abstractmethod
    def build(self):
        """Build VM/Container to run job.

        Raise exception if build failed.
        """
        pass

    @abc.abstractmethod
    def run(self, cmd, stdout_callback, stdin=None, env=None):
        """Run command.

        :param cmd: string command
        :param stdout_callback: callback to be called for every out/err string
        :param env: environment variables dict
        """
        pass

    @abc.abstractmethod
    def cleanup(self):
        pass
