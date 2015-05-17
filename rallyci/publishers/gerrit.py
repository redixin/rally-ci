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


from rallyci.common import asyncssh
from rallyci import base

class Class(base.Class):

    def publish(self, cr):
        cmd = "gerrit review -m '{summary}' {verified} {id}"
        if self.config.get("vote"):
            verified = "--verified=-1" if not success else "--verified=+1"
        summary = [self.cfg["job-format"].format(j=j) for j in cr.jobs]
        cmd = ["gerrit", "review", "-m", "'%s'" % summary, verified]
        cmd.append(cr.event["patchSet"]["revision"])
        asyncssh.AsyncSSH(self.cfg["ssh"]).run(cmd)
