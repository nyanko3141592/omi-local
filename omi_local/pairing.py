"""Pendant identity: only the paired pendant (config `pendant_address`, plus `pendant_serial` from the Device
Information service) is ever pulled or ADVANCEd. Other Omis nearby are ignored and logged.

  python -m omi_local.pairing list            # show visible Omis
  python -m omi_local.pairing pair [ADDRESS]  # pair (ADDRESS required if several are visible)
  python -m omi_local.pairing unpair
"""
import asyncio, json, sys, time
from bleak import BleakClient, BleakScanner
from omi_local import config
SERIAL = "00002a25-0000-1000-8000-00805f9b34fb"
_last_other_log = {}

def is_omi(d, ad):
    return (ad.local_name or d.name or "") in ("Omi", "Friend") or any(u.lower().startswith("19b10000") for u in ad.service_uuids)

async def scan_all(timeout=8.0):
    found = {}
    def cb(d, ad):
        if is_omi(d, ad): found[d.address] = ad.rssi
    async with BleakScanner(detection_callback=cb):
        await asyncio.sleep(timeout)
    return found

def choose(found):
    """Return the address to sync, or None. Never picks a stranger's pendant."""
    saved = config.get("pendant_address")
    others = [a for a in found if a != saved]
    now = time.time()
    for a in others if saved else []:
        if now - _last_other_log.get(a, 0) > 3600:
            config.log("sync.log", f"ignoring other Omi {a} (rssi {found[a]}); paired is {saved}"); _last_other_log[a] = now
    if saved: return saved if saved in found else None
    if len(found) == 1: return next(iter(found))
    if len(found) > 1 and now - _last_other_log.get("_multi", 0) > 3600:
        config.log("sync.log", f"{len(found)} unpaired Omis visible {list(found)}; refusing. Run `make pair` and pick one.")
        _last_other_log["_multi"] = now
    return None

async def read_serial(c):
    try: return bytes(await c.read_gatt_char(SERIAL)).decode(errors="ignore").strip("\x00 ") or None
    except Exception: return None

async def pair(address=None):
    found = await scan_all(10)
    if not found: sys.exit("no Omi visible. Press the pendant button and retry.")
    if address is None:
        if len(found) > 1:
            print("Several Omis visible — pick yours (strongest RSSI is usually the one in your hand):")
            for a, r in sorted(found.items(), key=lambda x: -x[1]): print(f"  {a}  rssi {r}")
            sys.exit("then: make pair ADDR=<address>")
        address = next(iter(found))
    async with BleakClient(address, timeout=30) as c:
        serial = await read_serial(c)
    config.set_many({"pendant_address": address, "pendant_serial": serial})
    config.log("sync.log", f"paired pendant {address} serial={serial}"); print(f"paired {address} serial={serial}")

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        for a, r in asyncio.run(scan_all(10)).items():
            print(a, "rssi", r, "(paired)" if a == config.get("pendant_address") else "")
    elif cmd == "pair": asyncio.run(pair(sys.argv[2] if len(sys.argv) > 2 else None))
    elif cmd == "unpair":
        config.set_many({"pendant_address": None, "pendant_serial": None}); config.log("sync.log", "unpaired"); print("unpaired")
if __name__ == "__main__": main()
