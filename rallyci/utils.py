import random
import string


def get_rnd_name(prefix="rci_", length=12):
    return prefix + "".join(random.sample(string.letters, length))
