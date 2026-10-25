"""Config: ~/OmiData/config.json overrides defaults; env OMI_<KEY> (0/1) overrides both.
Repo defaults are conservative (nothing deleted). Example config.json:
{"advance_pendant": true, "delete_audio_after_transcript": true, "sync_time": true}"""
import json, os
from pathlib import Path
DATA = Path(os.environ.get("OMI_DATA_DIR", Path.home() / "OmiData"))
DEFAULTS = {"advance_pendant": False, "delete_audio_after_transcript": False, "sync_time": True, "chunk_packets": 2000, "pendant_address": None, "pendant_serial": None}
def get(key):
    v = DEFAULTS[key]
    f = DATA / "config.json"
    if f.exists():
        try: v = json.loads(f.read_text()).get(key, v)
        except Exception: pass
    e = os.environ.get("OMI_" + key.upper())
    if e is not None and key not in ("pendant_address", "pendant_serial"): v = int(e) if key == "chunk_packets" else e.lower() in ("1", "true", "yes", "on")
    return v
def log(name, msg):
    d = DATA / "logs"; d.mkdir(parents=True, exist_ok=True)
    import time
    with open(d / name, "a") as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n"); f.flush(); os.fsync(f.fileno())

def set_many(kv):
    f = DATA / "config.json"; cur = json.loads(f.read_text()) if f.exists() else {}
    cur.update(kv); cur = {k: v for k, v in cur.items() if v is not None}
    DATA.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(cur, indent=1))
