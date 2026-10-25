"""Resident, event-driven watcher (launchd KeepAlive). Assumes the Mac is the pendant's only BLE central.

Duty-cycled scan (default 8 s on / 52 s off). Sync when the pendant (re)appears, and every OMI_RESYNC_MIN
(default 15) minutes while it stays visible. Each sync runs in a subprocess: time sync, pull ALL unread to
completion (chunked; a drop resumes next time), optional verified ADVANCE, disconnect, transcribe.
Between syncs nothing stays connected, so the pendant and Mac idle.
"""
import asyncio, os, subprocess, sys, time
from bleak import BleakScanner
from omi_local.sync import log
from omi_local import pairing

SCAN_ON = float(os.environ.get("OMI_SCAN_ON_S", "8"))       # seconds scanning per cycle
SCAN_OFF = float(os.environ.get("OMI_SCAN_OFF_S", "52"))    # seconds idle per cycle
RESYNC = float(os.environ.get("OMI_RESYNC_MIN", "15")) * 60

async def scan_once():
    return pairing.choose(await pairing.scan_all(SCAN_ON))

async def loop():
    log("watcher started")
    visible = False; last_sync = 0.0; fails = 0
    while True:
        try:
            addr = await asyncio.wait_for(scan_once(), SCAN_ON + 30); fails = 0
        except Exception as e:
            fails += 1
            log(f"scan error ({e!r}); Bluetooth off or permission missing? backing off")
            await asyncio.sleep(min(600, 30 * fails)); continue
        now = time.monotonic()
        if addr and (not visible or now - last_sync > RESYNC):
            log(f"pendant {'visible' if visible else 'appeared'} ({addr}) -> sync")
            try: subprocess.run([sys.executable, "-m", "omi_local.sync", "--address", addr], timeout=3600)
            except Exception as e: log(f"sync subprocess error {e!r}")
            last_sync = time.monotonic()
        visible = bool(addr)
        await asyncio.sleep(SCAN_OFF)  # wall-clock sleep: robust to system sleep/wake

if __name__ == "__main__":
    asyncio.run(loop())
