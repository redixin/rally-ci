import random
import string
import time
import logging

LOG = logging.getLogger(__name__)


def get_rnd_name(prefix="rci_", length=12):
    return prefix + "".join(random.sample(string.letters, length))


class Stdout(object):
    """For using with sshutils"""

    def __init__(self, cb, num=1):
        self.cb = cb
        self.num = num

    def write(self, line):
        self.cb((self.num, line))


def get_stdouterr(cb):
    return {"stdout": Stdout(cb),
            "stderr": Stdout(cb, 2)}


def retry(fun, *args, **kwargs):
    for i in range(4):
        try:
            return fun(*args, **kwargs)
        except Exception as e:
            LOG.warning("Raised %s. Retrying (%s)." % (e, i))
            time.sleep(1)
    raise e
