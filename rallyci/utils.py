import random
import string


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

