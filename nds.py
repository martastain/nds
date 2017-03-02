#!/usr/bin/env python

import os
import sys
import rex
import time
import cherrypy

from xml.etree import ElementTree as ET

from nxtools import *
from mpd import *

settings = {
        "data_dir" : "/mnt/cache/origin_dash",
        "host" : "127.0.0.1",
        "port" : 51100
    }

DASH_MIMES = {
        "mpd" : "application/dash+xml",
        "m4v" : "video/mp4",
        "m4a" : "audio/mp4"
    }

def xml(data):
    return ET.XML(data)

class StreamData(object):
    def __init__(self, stream_name):
        self.stream_name = stream_name
        self.mtime = 0
        self.timescale = 1000
        self.start_time = 0
        self.segment_duration = 2
        self.stream_deviation = None
        self.manifest = None

    @property
    def current_number(self):
        return int((time.time() - self.start_time) / self.segment_duration) + 1

    def number_to_time(self, number):
        return int(number * self.segment_duration * self.timescale) + self.stream_deviation

    def get_start_time(self):
        ident_max = 0
        ident_mtime = 0
        for fname in os.listdir(settings["data_dir"]):
            fpath = os.path.join(settings["data_dir"], fname)
            if not fname.startswith(self.stream_name + "-"):
                continue
            base_name = os.path.splitext(fname)[0]
            stream_name, ident = base_name.split("-")
            if stream_name != self.stream_name:
                continue
            if not ident.isdigit():
                continue
            ident = ident
            mtime = os.path.getmtime(fpath)
            if mtime > ident_mtime:
                ident_max = ident
                ident_mtime = mtime

        stream_age = float(ident_max) / self.timescale
#        self.stream_deviation = int((stream_age - int(stream_age)) * self.timescale)
        if self.stream_deviation is None:
            self.stream_deviation =  int(ident_max) % self.timescale

            #self.stream_deviation =  int( (stream_age*self.timescale) - (int(stream_age+0.5)*self.timescale))
        self.start_time = time.time() - stream_age
        logging.info(
                "{} start time is {}, age: {}, deviation: {}".format(
                    self.stream_name,
                    self.start_time,
                    stream_age,
                    self.stream_deviation
                )
            )

    @property
    def source_manifest_path(self):
        return os.path.join(settings["data_dir"], self.stream_name + ".mpd")

    def load(self):
        prefix = "{urn:mpeg:dash:schema:mpd:2011}"
        source_manifest_path = self.source_manifest_path

        if not os.path.exists(source_manifest_path):
            return False

        try:
            source_manifest = xml(open(source_manifest_path).read())
        except Exception:
            log_traceback()
            return False

        if not self.start_time:
            self.get_start_time()

        manifest = MPD()

        manifest["type"] = "dynamic"
        manifest["minimumUpdatePeriod"] = "PT3M"
        manifest["minBufferTime"] = "PT4S"
        manifest["timeShiftBufferDepth"] = "PT3M"
        manifest["maxSegmentDuration"] = "PT2S"

        manifest.set_time("availabilityStartTime", self.start_time)
        manifest.set_time("publishTime", self.start_time)

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

            for source_representation in source_adaptation_set.findall(prefix + "Representation"):
                representation = adaptation_set.add_representation(**source_representation.attrib)

                sseg = source_representation.find(prefix + "SegmentTemplate")
                mext = os.path.splitext(sseg.attrib["media"])[1]

                representation.segment_template = SegmentTemplate(
                        representation,
                        timescale=1000,
                        duration=2000,
                        startNumber=0,
                        initialization=sseg.attrib["initialization"],
                        media="{}-$Number${}".format(self.stream_name, mext)
                        )

        self.mtime = os.path.getmtime(source_manifest_path)
        self.manifest = manifest.xml
        return True





class ManifestTranslator(object):
    def __init__(self):
        self.streams = {}

    def load_stream(self, stream_name):
        logging.debug("Updating stream {} source manifest".format(stream_name))
        stream = StreamData(stream_name)
        if not stream.load():
            return False
        self.streams[stream_name] = stream
        return True

    def __getitem__(self, stream_name):
        if not stream_name in self.streams:
            logging.info("Loading stream {} data".format(stream_name))
            if not self.load_stream(stream_name):
                logging.error("Unable to load stream {}".format(stream_name))
                return False
        if self.streams[stream_name].mtime != os.path.getmtime(self.streams[stream_name].source_manifest_path):
            self.load_stream(stream_name)
        return self.streams[stream_name]


manifest_translator = ManifestTranslator()

#
# HTTP interface
#

def mk_error(response=500, message="Something went bad"):
    cherrypy.response.status = response
    cherrypy.response.headers['Content-Type'] = "text/txt"
    logging.error("{}:{}".format(response, message))
    return "Error {}: {}".format(response, message)

def serve_file(file_name):
    file_path = os.path.join(settings["data_dir"], file_name)
    if not os.path.exists(file_path):
        return mk_error(404, message="File {} not found".format(file_name))
    return open(file_path, "rb").read()

class NMPDServer(object):
    @cherrypy.expose
    def default(self, *args, **kwargs):
        if not args:
            return mk_error(400, "Bad request. Media unspecified.")
        file_name = args[-1]
        base_name, ext = os.path.splitext(file_name)
        ext = ext.lstrip(".")
        if ext not in DASH_MIMES:
            return mk_error(400, "Bad request. Unknown file type requested")

        stream_name = base_name.split("-")[0]
        stream_data = manifest_translator[stream_name]
        if not stream_data:
            return mk_error(404, "Requested stream {} not found".format(file_name))

        cherrypy.response.headers['Content-Type'] = DASH_MIMES[ext]
        if ext == "mpd":
            return stream_data.manifest
        elif base_name.find("init") > -1:
            return serve_file(file_name)

        stream_name, number = base_name.split("-")
        number = int(number)
        if number > stream_data.current_number:
            return mk_error(404, "{} not found. Requested segment is from the future".format(file_name))
        ts = stream_data.number_to_time(number)
        fname = "{}-{}.{}".format(stream_name, ts, ext)
        logging.info("Serving {} as {}".format(fname, file_name))
        return serve_file(fname)


if __name__ == "__main__":
    cherrypy.config.update({
            'server.socket_host': str(settings["host"]),
            'server.socket_port': int(settings["port"]),
        })
    access_log = cherrypy.log.access_log
    for handler in tuple(access_log.handlers):
        access_log.removeHandler(handler)
    cherrypy.quickstart(NMPDServer())
