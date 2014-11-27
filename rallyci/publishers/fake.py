
import base

class Publisher(base.Publisher):

    @staticmethod
    def check_config(config):
        pass

    def publish_line(self, stream, line):
        pass

    def publish_summary(self, jobs):
        pass
