"""Resident, event-driven watcher (run by launchd KeepAlive).

Duty-cycled passive BLE scan (CoreBluetooth via bleak). When the Omi pendant
advertises (i.e. the iPhone released it), run one sync pass in a subprocess:
pull new unread audio (never ADVANCE/CLEAR), disconnect, transcribe, append.
Cooldown: re-sync only after the pendant disappears and reappears, or at most
every OMI_RESYNC_MIN (default 60) minutes while it stays visible.
"""
import asyncio, os, subprocess, sys, time
from bleak import BleakScanner
from omi_local.sync import log

SCAN_ON = float(os.environ.get("OMI_SCAN_ON_S", "8"))       # seconds scanning per cycle
SCAN_OFF = float(os.environ.get("OMI_SCAN_OFF_S", "52"))    # seconds idle per cycle
GONE_AFTER = float(os.environ.get("OMI_GONE_AFTER_S", "600"))
RESYNC = float(os.environ.get("OMI_RESYNC_MIN", "60")) * 60

def is_omi(d, ad):
    return (ad.local_name or d.name or "") in ("Omi", "Friend") or any(u.lower().startswith("19b10000") for u in ad.service_uuids)

async def scan_once():
    found = None
    def cb(d, ad):
        nonlocal found
        if found is None and is_omi(d, ad): found = d.address
    async with BleakScanner(detection_callback=cb):
        t = time.monotonic()
        while found is None and time.monotonic() - t < SCAN_ON:
            await asyncio.sleep(0.5)
    return found

async def loop():
    log("watcher started")
    last_seen = 0.0; last_sync = 0.0; fails = 0
    while True:
        try:
            addr = await asyncio.wait_for(scan_once(), SCAN_ON + 30); fails = 0
        except Exception as e:
            fails += 1
            log(f"scan error ({e!r}); Bluetooth off or permission missing? backing off")
            await asyncio.sleep(min(600, 30 * fails)); continue
        now = time.monotonic()
        if addr:
            reappeared = now - last_seen > GONE_AFTER
            last_seen = now
            if reappeared or now - last_sync > RESYNC:
                log(f"pendant visible ({addr}) -> sync")
                subprocess.run([sys.executable, "-m", "omi_local.sync", "--address", addr], timeout=2400)
                last_sync = time.monotonic(); last_seen = last_sync
        await asyncio.sleep(SCAN_OFF)  # wall-clock sleep: robust to system sleep/wake

if __name__ == "__main__":
    asyncio.run(loop())
