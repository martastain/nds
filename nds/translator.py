from nxtools import *

from .common import *
from .stream import *

__all__ = ["ManifestTranslator"]


class ManifestTranslator(object):
    def __init__(self):
        self.streams = {}

    def __getitem__(self, name):
        if not name in self.streams:
            logging.info("Loading stream {} data".format(name))
            stream = Stream(name)
            if not stream.load():
                return False
            self.streams[name] = stream
        else:
            if not self.streams[name].load():
                return False
        return self.streams[name]

