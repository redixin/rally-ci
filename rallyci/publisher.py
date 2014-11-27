
import abc

class Publisher:
    """Abstract class of Publisher object.

    Publisher is used for jobs results publishing.

    """
    __metaclass__ = abc.ABCMeta

    @staticmethod
    @abc.abstractmethod
    def check_config(config):
        """Check configuration
        Should return None if success, or string with error description.
        :param config: Publisher's configuration dictionary
        """
        pass

    @abc.abstractmethod
    def publish_line(self, stream, line):
        """Publish line in stream
        :param stream: stream name, e.g. "build.log" or "console.log"
        """
        pass

    @abc.abstractmethod
    def publish_summary(self, jobs):
        """Publish project jobs summary.
        :param jobs: list of Job instances
        """
        pass
