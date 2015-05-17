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

class Class(base.Class):

    def publish(self, cr):
        cmd = ["gerrit", "review"]
        fail = any([j.failed for j in cr.jobs if j.voting])
        if self.cfg.get("vote"):
            cmd.append("--verified=-1" if fail else "--verified=+1")
        summary = self.cfg["header"].format(succeeded="failed" if fail else "succeeded")
        for job in cr.jobs:
            voting = "" if job.voting else " (non voting)"
            human_time = "..."
            summary += self.cfg["job-template"].format(j=job, voting=voting, human_time=human_time)
        cmd += ["-m", "'%s'" % summary, cr.event["patchSet"]["revision"]]
        asyncio.async(asyncssh.AsyncSSH(**self.cfg["ssh"]).run(" ".join(cmd)))
