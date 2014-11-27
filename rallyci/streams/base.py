
import abc

class Stream:
    __metaclass__ = abc.ABCMeta

    def __init__(self, config):
        self.config = config

    @abc.abstractmethod
    def generate(self):
        """Yield event dicts."""
        pass
