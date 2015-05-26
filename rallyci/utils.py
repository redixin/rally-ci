# Copyright 2015: Mirantis Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import errno
import os
import random
import string
import time
import logging

LOG = logging.getLogger(__name__)


def get_rnd_name(prefix="rci_", length=12):
    return prefix + "".join(random.sample(string.ascii_letters, length))


def get_rnd_mac():
    mac5 = ["%02x" % random.randint(0, 255) for i in range(5)]
    return "02:" + ":".join(mac5)


def makedirs(*args):
    """Create directories.

    Do not raise exception if directory already exists.
    """
    try:
        os.makedirs(os.path.join(*args))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


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
