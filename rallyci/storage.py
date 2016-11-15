# Copyright 2016: Mirantis Inc.
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

import dbm


class DBMStorage:

    def __init__(self, service_name, storage_name, **kwargs):
        path = os.path.join(kwargs["path"], service_name)
        os.makedirs(path, exist_ok=True)
        self.db = dbm.open(os.path.join(path, storage_name + ".db"), "cs")
