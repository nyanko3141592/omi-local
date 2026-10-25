"""One sync pass for launchd: short scan -> if pendant present, pull new unread (no ADVANCE) -> transcribe.
Quiet (exit 0) when pendant absent. Uses a lock so runs never overlap."""
import asyncio, fcntl, os, signal, sys, time
from pathlib import Path
from bleak import BleakScanner
DATA = Path(os.environ.get("OMI_DATA_DIR", Path.home() / "OmiData"))
LOGD = DATA / "logs"

def log(msg):
    LOGD.mkdir(parents=True, exist_ok=True)
    with open(LOGD / f"sync-{time.strftime('%Y-%m')}.log", "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")

async def present(timeout=20):
    d = await BleakScanner.find_device_by_filter(
        lambda dv, ad: (ad.local_name or "") in ("Omi", "Friend") or any(u.startswith("19b10000") for u in ad.service_uuids),
        timeout=timeout)
    return d

def main(address=None):
    DATA.mkdir(parents=True, exist_ok=True)
    lock = open(DATA / ".sync.lock", "w")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: return
    def _to(*_): log("timeout (Bluetooth permission prompt pending?) - exiting"); os._exit(0)
    signal.signal(signal.SIGALRM, _to); signal.alarm(60)
    if address is None and len(sys.argv) > 2 and sys.argv[1] == "--address": address = sys.argv[2]
    if address:
        class dev: pass
        dev.address = address
    else:
        dev = asyncio.run(present(float(os.environ.get("OMI_SCAN_SECONDS", "20"))))
        if not dev: print("pendant not found"); return  # away: stay quiet
    signal.alarm(3500)
    log(f"pendant found {dev.address}")
    from omi_local import ring, transcribe
    class A: address = dev.address; info = False; max_packets = 0
    try:
        asyncio.run(asyncio.wait_for(ring.run(A), 3000))
        log("pull ok")
    except BaseException as e:
        log(f"pull error: {e!r}")
    try:
        transcribe.main(); log("transcribe ok")
    except Exception as e:
        log(f"transcribe error: {e!r}")

if __name__ == "__main__": main()
