#!/usr/bin/env python

import os
import time
import cherrypy

import rex

from nds import *


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
            return mk_error(404, "Requested stream {} not found".format(stream_name))

        cherrypy.response.headers['Content-Type'] = DASH_MIMES[ext]
        if ext == "mpd":
            return stream_data.manifest
        elif base_name.find("init") > -1:
            return serve_file(file_name)

        stream_name, number = base_name.split("-")
        number = int(number)
        if number > stream_data.current_number:
            return mk_error(
                    404,
                    "{} not found. Requested segment is from the future".format(file_name)
                )
        ts = stream_data.number_to_time(number)
        if ts is None:
            return mk_error(404, "{} not found. Creation in progress??".format(file_name))
        fname = "{}-{}.{}".format(stream_name, ts, ext)
#        logging.debug("Serving {} as {}".format(fname, file_name))
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
