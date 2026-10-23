"""Small durable files shared by the host controller and Docker workers."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with Path(path).open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()


def read_json(path, default=None):
    try: return json.loads(Path(path).read_text())
    except FileNotFoundError: return default


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as handle:
            json.dump(value,handle,indent=2,allow_nan=False); handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
        os.replace(name,path)
        directory = os.open(path.parent,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


def status(path, state, **values):
    value = {'state':state,'updated_unix':time.time(),**values}
    atomic_json(path,value)
    return value
