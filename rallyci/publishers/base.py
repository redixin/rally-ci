
import abc


class Publisher:
    """Abstract class of Publisher object.

    Publisher is used for jobs results publishing.

    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, run_id, event, config):
        """Initialise publisher.

        :param run_id: unique id of jobs run
        :param event: Event object (dict)
        :param config: publisher's config dictionary from config file

        """
        self.run_id = run_id
        self.event = event
        self.config = config

    @staticmethod
    @abc.abstractmethod
    def check_config(config):
        """Check configuration.

        Should return None if success, or string with error description.
        :param config: Publisher's configuration dictionary
        """
        pass

    @abc.abstractmethod
    def publish_line(self, stream, line):
        """Publish line in stream.

        :param stream: stream name (script name)
        :line: tuple (number, line) where number is 1 or 2 for stdout or stderr
        """
        pass

    @abc.abstractmethod
    def publish_summary(self, jobs):
        """Publish project jobs summary.

        :param jobs: list of Job instances
        """
        pass
