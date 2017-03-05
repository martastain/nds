import os
import json

import rex

from nxtools import *

DASH_MIMES = {
        "mpd" : "application/dash+xml",
        "m4v" : "video/mp4",
        "m4a" : "audio/mp4"
    }

settings = {
        "data_dir" : "/mnt/cache/dash",
        "segment_duration" : 2,
        "timescale" : 1000,
        "host" : "127.0.0.1",
        "port" : 51100
    }

settings_path = "settings.json"
if os.path.exists(settings_path):
    try:
        new_settings = json.load(open(settings_path))
    except Exception:
        log_traceback("Unable to parse settings file")
        new_settings = {}
    settings.update(new_settings)

