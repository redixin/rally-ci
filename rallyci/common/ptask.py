"""
Aleksandr Kuchuk
"""
import asyncio
import resource
import logging

LOG = logging.getLogger(__name__)

class PeriodicTask(object):
    def __init__(self, interval, method):
        self.active = False
        self._interval = interval
        self.method = method
        self._loop = asyncio.get_event_loop()

    def _run(self):
        self.run()
        self._handler = self._loop.call_later(self._interval, self._run)

    def run(self):
        stat = self._daemon_stat()
        LOG.debug(stat)
        self.method(stat)

    def start(self):
        self._handler = self._loop.call_later(self._interval, self._run)

    def stop(self):
        self._handler.cancel()

    def get_loop(self):
        return self._loop

    def _daemon_stat(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {"type": "daemon-statistics", "memory-used": getattr(usage, "ru_maxrss")}
