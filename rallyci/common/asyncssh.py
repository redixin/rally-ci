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
import subprocess
import sys
import tempfile
import time
import logging

LOG = logging.getLogger(__name__)


class SSHError(Exception):
    pass


class AsyncSSH:
    _ready = False

    def __init__(self, username=None, hostname=None, key=None, port=22, cb=None):
        if cb:
            self.cb = cb
        self.key = key
        self.username = username if username else "root"
        self.hostname = hostname
        self.port = str(port)

    def cb(self, line):
        LOG.debug(repr(line))

    @asyncio.coroutine
    def run(self, command, stdin=None, return_output=False,
            strip_output=True, raise_on_error=True, user=None):
        if not self._ready:
            try:
                yield from self.wait()
            except Exception:
                if raise_on_error:
                    raise
                else:
                    return -1
        if not user:
            user = self.username
        output = b""
        if isinstance(stdin, str):
            f = tempfile.TemporaryFile()
            f.write(stdin.encode())
            f.flush()
            f.seek(0)
            stdin = f
        cmd = ["ssh", "-T", "-o", "StrictHostKeyChecking=no",
               "%s@%s" % (user, self.hostname), "-p", self.port]
        if self.key:
            cmd += ["-i", self.key]
        if isinstance(command, str):
            cmd += command.split(" ")
        else:
            cmd += command
        LOG.debug("Running '%s'" % cmd)
        process = asyncio.create_subprocess_exec(*cmd,
                                                 stdin=stdin,
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.STDOUT)
        process = yield from process
        try:
            while not process.stdout.at_eof():
                line = yield from process.stdout.readline()
                self.cb(line)
                if return_output:
                    output += line
        except asyncio.CancelledError:
            LOG.debug("Terminated. Killing child process.")
            process.terminate()
            asyncio.async(process.wait(), loop=asyncio.get_event_loop())
            raise

        yield from process.wait()

        if process.returncode and raise_on_error:
            LOG.error("Command failed: %s" % line)
            msg = "Cmd '%s' failed. Exit code: %d" % (" ".join(cmd),
                                                      process.returncode)
            raise SSHError(msg)

        if return_output:
            output = output.decode()
            if strip_output:
                return output.strip()
            return output

        LOG.debug("Returning %s" % process.returncode)
        return process.returncode

    @asyncio.coroutine
    def wait(self, timeout=300):
        start = time.time()
        while 1:
            try:
                r, w = yield from asyncio.open_connection(self.hostname,
                                                          int(self.port))
                self._ready = True
                w.close()
                return
            except ConnectionError:
                pass
            if time.time() - start > timeout:
                raise Exception("Timeout waiting for "
                                "%s:%s" % (self.hostname, self.port))
            LOG.debug("Waiting for ssh %s:%s" % (self.hostname, self.port))
            yield from asyncio.sleep(1)

    @asyncio.coroutine
    def scp_get(self, src, dst):
        cmd = ["scp", "-B", "-o", "StrictHostKeyChecking no"]
        if self.key:
            cmd += ["-i", self.key]
        cmd += ["-P", self.port]
        cmd += ["-r", "%s@%s:%s" % (self.username, self.hostname, src), dst]
        LOG.debug("Runnung %s" % " ".join(cmd))
        process = asyncio.create_subprocess_exec(*cmd,
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.STDOUT)
        process = yield from process
        try:
            while not process.stdout.at_eof():
                line = yield from process.stdout.read()
                LOG.debug("scp: %s" % line)
        except asyncio.CancelledError:
            process.terminate()
            asyncio.async(process.wait(), loop=asyncio.get_event_loop())
            raise
        return process.returncode
