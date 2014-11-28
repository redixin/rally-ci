
import abc

class Runner:
    __metaclass__ = abc.ABCMeta

    def __init__(self, config):
        self.config = config

    @abc.abstractmethod
    def init(self, **kwargs):
        pass

    @abc.abstractmethod
    def build(self):
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
