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

from rallyci.common import asyncssh
from rallyci import base

INTERVALS = [1, 60, 3600, 86400]
NAMES = [('s', 's'),
         ('m', 'm'),
         ('h', 'h'),
         ('day', 'days')]


def human_time(seconds):
    seconds = int(seconds)
    result = []
    for i in range(len(NAMES) - 1, -1, -1):
        a = seconds // INTERVALS[i]
        if a > 0:
            result.append((a, NAMES[i][1 % a]))
            seconds -= a * INTERVALS[i]
    return ' '.join(''.join(str(x) for x in r) for r in result)


class Class(base.Class):
    def publish(self, cr):
        cmd = ["gerrit", "review"]
        fail = any([j.failed for j in cr.jobs if j.voting])
        if self.cfg.get("vote"):
            cmd.append("--verified=-1" if fail else "--verified=+1")
        succeeded = "failed" if fail else "succeeded"
        summary = self.cfg["header"].format(succeeded=succeeded)
        for job in cr.jobs:
            success = "FAILURE" if job.failed else "SUCCESS"
            success += "" if job.voting else " (non voting)"
            time = human_time(job.finished_at - job.started_at)
            summary += self.cfg["job-template"].format(success=success,
                                                       name=job.name,
                                                       time=time,
                                                       log_path=job.log_path)
            summary += "\n"
        cmd += ["-m", "'%s'" % summary, cr.event["patchSet"]["revision"]]
        asyncio.async(asyncssh.AsyncSSH(**self.cfg["ssh"]).run(" ".join(cmd)))
