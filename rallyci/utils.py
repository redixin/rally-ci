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
import socket
import string
import time
import logging

LOG = logging.getLogger(__name__)

SAFE_CHARS = string.ascii_letters + string.digits + "_"

INTERVALS = [1, 60, 3600, 86400]
NAMES = [("s", "s"),
         ("m", "m"),
         ("h", "h"),
         ("day", "days")]


def _merge(child, parent):
    for key in parent:
        if key not in child:
            child[key] = parent[key]


def _check_parent(config, job):
    parent = job.pop("parent", None)
    if parent:
        _check_parent(config, config["job"][parent])
        _merge(job, config["job"][parent])


def get_local_address(remote_address):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((remote_address, 0))
    return s.getsockname()[0]


def expand_jobs(config):
    for job in config["job"]:
        _check_parent(config, config["job"][job])


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def human_time(seconds):
    seconds = int(seconds)
    result = []
    for i in range(len(NAMES) - 1, -1, -1):
        a = seconds // INTERVALS[i]
        if a > 0:
            result.append((a, NAMES[i][1 % a]))
            seconds -= a * INTERVALS[i]
    return " ".join("".join(str(x) for x in r) for r in result)


def get_safe_filename(name):
    name = name.replace(" ", "_")
    return "".join([c for c in name if c in SAFE_CHARS])


def get_rnd_name(prefix, length=12):
    prefix = "_rci_" + prefix
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


class LogDel:
    def __del__(self):
        print("DELETED %s" % self)
