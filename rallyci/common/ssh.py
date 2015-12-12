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


import asyncio
import functools
import logging
import os
import pwd
import sys
import time

import asyncssh

LOG = logging.getLogger(__name__)


class SSHError(Exception):
    pass


class SSHProcessFailed(SSHError):
    pass


class SSHProcessKilled(SSHProcessFailed):
    pass


class SSHClient(asyncssh.SSHClient):

    def __init__(self, ssh, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ssh = ssh

    def connection_made(self, conn):
        pass

    def connection_lost(self, ex):
        self._ssh._connected.clear()
        self._ssh.client = None
        self._ssh.conn = None
        self._ssh = None


class SSHClientSession(asyncssh.SSHClientSession):

    def __init__(self, callbacks, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stdout_cb, self._stderr_cb = callbacks

    def data_received(self, data, datatype):
        if self._stdout_cb and datatype is None:
            self._stdout_cb(data)
        elif self._stderr_cb and (datatype == asyncssh.EXTENDED_DATA_STDERR):
            self._stderr_cb(data)

    def connection_lost(self):
        self._stdout_cb = None
        self._stderr_cb = None


class SSH:

    def __init__(self, loop, hostname, username=None, keys=None, port=22,
                 cb=None):
        self.loop = loop
        self.username = username or pwd.getpwuid(os.getuid()).pw_name
        self.hostname = hostname
        self.keys = keys
        self.port = port
        self.cb = cb
        self._connecting = asyncio.Lock(loop=loop)
        self._connected = asyncio.Event(loop=loop)

    def client_factory(self, *args, **kwargs):
        return SSHClient(self, *args, **kwargs)

    def close(self):
        if hasattr(self, "conn"):
            if self._connected.is_set():
                self.conn.close()

    @asyncio.coroutine
    def _ensure_connected(self):
        with (yield from self._connecting):
            if self._connected.is_set():
                return
            LOG.debug("Connecting %s@%s with keys %s" % (self.username, self.hostname, self.keys))
            self.conn, self.client = yield from asyncssh.create_connection(
                functools.partial(SSHClient, self), self.hostname,
                username=self.username, known_hosts=None,
                client_keys=self.keys, port=self.port)
            LOG.debug("Connected %s@%s" % (self.username, self.hostname))
            self._connected.set()

    @asyncio.coroutine
    def run(self, cmd, stdin=None, stdout=None, stderr=None, check=True,
            env=None):
        """Run command on remote server.

        :param string cmd: command to be executed
        :param stdin: either string, bytes or file like object
        :param stdout: executable (e.g. sys.stdout.write)
        :param stderr: executable (e.g. sys.stderr.write)
        :param boolean check: Raise an exception in case of non-zero exit status.
        """
        if isinstance(cmd, list):
            cmd = _escape_cmd(cmd)
        cmd = _escape_env(env) + cmd
        LOG.debug("Running %s" % cmd)
        yield from self._ensure_connected()
        session_factory = functools.partial(SSHClientSession, (stdout, stderr))
        chan, session = yield from self.conn.create_session(session_factory,
                                                            cmd, env=env or {})
        if stdin:
            if hasattr(stdin, "read"):
                while True:
                    chunk = stdin.read(4096).decode("ascii")
                    if not chunk:
                        break
                    chan.write(chunk)
                    # TODO: drain
            else:
                chan.write(stdin)
            chan.write_eof()
        yield from chan.wait_closed()
        status = chan.get_exit_status()
        if check and status == -1:
            raise SSHProcessKilled(chan.get_exit_signal())
        if check and status != 0:
            raise SSHProcessFailed(status)
        return status

    @asyncio.coroutine
    def out(self, cmd, stdin=None, check=True, env=None):
        stdout = []
        stderr = []
        status = yield from self.run(cmd, stdout=stdout.append,
                                     stderr=stderr.append,
                                     stdin=stdin, check=check, env=env)
        stdout = "".join(stdout)
        stderr = "".join(stderr)
        return (status, stdout, stderr)

    @asyncio.coroutine
    def wait(self, timeout=180, delay=2):
        _start = time.time()
        while True:
            try:
                yield from self._ensure_connected()
                return
            except Exception:
                pass
            if time.time() > (_start + timeout):
                raise SSHError("timeout %s:%s" % (self.hostname, self.port))
            yield from asyncio.sleep(delay)

def _escape(string):
    return string.replace(r"'", r"'\''")


def _escape_env(env):
    cmd = ""
    if env:
        for key, val in env.items():
            # TODO: safe variable name
            cmd += "%s='%s' " % (key, _escape(val))
    return cmd


def _escape_cmd(cmd):
   return " ".join(["'%s'" % _escape(arg) for arg in cmd])
