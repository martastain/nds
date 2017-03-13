import os
import time

from mpd import *

from nxtools import *
from .common import *

class Stream(object):
    def __init__(self, name):
        self.data_dir = settings["data_dir"]
        self.name = name
        self.segment_duration = settings["segment_duration"]
        self.timescale = settings["timescale"]
        self.manifest_path = os.path.join(self.data_dir, name + ".mpd")
        self.manifest = None
        self.manifest_mtime = 0
        self.start_time = 0
        self.age = 0
        self.load()

    def load(self):
        self.load_numbers()
        return self.load_manifest()

    def load_manifest(self):
        if not os.path.exists(self.manifest_path):
            logging.warning("Stream manifest {} does not exist".format(self.name))
            self.manifest = None
            return False

        manifest_mtime = os.path.getmtime(self.manifest_path)
        if manifest_mtime == self.manifest_mtime:
            return False

        try:
            source_manifest = xml(open(self.manifest_path).read())
            self.manifest_mitme = manifest_mtime
        except Exception:
            log_traceback("Unable to open {} manifest".format(self.name))
            return False

        prefix = "{urn:mpeg:dash:schema:mpd:2011}"
        manifest = MPD()

        manifest.set_time("availabilityStartTime", self.start_time)
        manifest.set_time("publishTime", time.time())

        source_period = source_manifest.find(prefix + "Period")
        period = manifest.add_period(**source_period.attrib)

        for source_adaptation_set in source_period.findall(prefix + "AdaptationSet"):
            adaptation_set = period.add_adaptation_set(**source_adaptation_set.attrib)

            adaptation_set["startWithSAP"] = "1"
            adaptation_set["subsegmentAlignment"] = "true"
            adaptation_set["segmentAlignment"] = "true"
            adaptation_set["subsegmentStartsWithSAP"] = "1"
            adaptation_set["bitstreamSwitching"] = "true"

#            contentType="video"
#            par="16:9"

            for source_representation in source_adaptation_set.findall(
                        prefix + "Representation"
                    ):
                representation = adaptation_set.add_representation(
                        **source_representation.attrib
                    )

                sseg = source_representation.find(prefix + "SegmentTemplate")
                mext = os.path.splitext(sseg.attrib["media"])[1]

                representation.segment_template = SegmentTemplate(
                        representation,
                        timescale=1000,
                        duration=2000,
                        startNumber=0,
                        initialization=sseg.attrib["initialization"],
                        media="{}-$Number${}".format(self.name, mext)
                        )

        self.manifest = manifest.xml
        return True


    def load_numbers(self):
        mtimes = {}
        for fname in os.listdir(self.data_dir):
            fpath = os.path.join(self.data_dir, fname)
            if not fname.startswith(self.name + "-"):
                continue
            base_name = os.path.splitext(fname)[0]
            elms = base_name.split("-")
            stream_name = elms[0]
            ident = elms[-1]
            if stream_name != self.name:
                continue
            if not ident.isdigit():
                continue
            ident = int(ident)
            if ident in mtimes:
                continue
            mtimes[ident] = os.path.getmtime(fpath)

        if not mtimes:
            return

        max_ident = max(mtimes.keys(), key=lambda x: mtimes[x])
        max_ident_mtime = mtimes[max_ident]
        numbers = {}
        for ident in sorted(mtimes.keys()):
            if ident > max_ident:
                continue # skip orphaned numbers
            number = ident / (self.segment_duration * self.timescale)
            numbers[number] = ident
        self.numbers = numbers

        self.age = max_ident / self.timescale

        # Tohle neni start time, ale takovej ten zacatek pro PVR...
        #age = len(self.numbers) * self.segment_duration

        self.start_time = time.time() - self.age + self.segment_duration
        logging.info("Start time: {}, Age: {}, Current number: {}".format(
            format_time(self.start_time),
            self.age,
            self.current_number
            ))


    @property
    def current_number(self):
        return max(self.numbers.keys())

    def number_to_time(self, number):
        try:
            return self.numbers[number]
        except KeyError:
            log_traceback()
            return None
