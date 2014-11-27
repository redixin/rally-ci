
import json
import base

class Stream(base.Stream):
    def generate(self):
        for line in open(self.config["path"]):
            yield(json.loads(line))
