"""Non-destructive reader for Omi firmware >=3.0.20 ring-buffer storage (omi PR #7216).
Reads unread packets WITHOUT sending ADVANCE/CLEAR, so nothing on the pendant is reclaimed."""
import argparse, asyncio, json, os, struct, time, wave
from pathlib import Path
from bleak import BleakClient, BleakScanner
CTRL = "30295781-4301-eabd-2904-2849adfeae43"; STATUS = "30295782-4301-eabd-2904-2849adfeae43"
DIS_FW = "00002a26-0000-1000-8000-00805f9b34fb"
DATA = Path(os.environ.get("OMI_DATA_DIR", Path.home() / "OmiData"))
REC = 444

def frames_of(records):
    out = []
    for r in records:
        a = r[4:]; o = 0
        while o < len(a) - 1:
            s = a[o]
            if s == 0: o += 1; continue
            if o + 1 + s >= len(a): break
            out.append(a[o + 1:o + 1 + s]); o += s + 1
    return out

async def find(address=None):
    if address: return address
    d = await BleakScanner.find_device_by_filter(lambda dv, ad: (ad.local_name or "") in ("Omi", "Friend"), timeout=30)
    if not d: raise SystemExit("pendant not found")
    return d

async def run(a):
    q = asyncio.Queue()
    async with BleakClient(await find(a.address), timeout=45) as c:
        fw = bytes(await c.read_gatt_char(DIS_FW)).decode(errors="ignore")
        st = struct.unpack("<4I", bytes(await c.read_gatt_char(STATUS))[:16])
        await c.start_notify(CTRL, lambda _, d: q.put_nowait(bytes(d)))
        await c.write_gatt_char(CTRL, bytes([0x10]), response=True)
        info = None
        while info is None:
            m = await asyncio.wait_for(q.get(), 10)
            if m[0] == 0x02: info = struct.unpack(">QQIQH", m[1:31])
        rs, ws, cap, dropped, psize = info
        meta = {"fw": fw, "used_bytes": st[0], "unread_packets": st[1], "free_bytes": st[2], "rtc_valid": st[3],
                "read_seq": rs, "write_seq": ws, "capacity": cap, "dropped": dropped, "packet_size": psize}
        print(json.dumps(meta))
        if a.info: return
        stf = DATA / "state" / "ring.json"; stf.parent.mkdir(parents=True, exist_ok=True)
        last = json.loads(stf.read_text()).get("next_seq", 0) if stf.exists() else 0
        if last > rs and last <= ws: rs = last  # skip packets already saved locally (pendant untouched)
        if ws - rs <= 0: print(json.dumps({"new_packets": 0})); return
        n = min(ws - rs, a.max_packets or (ws - rs))
        buf = bytearray(); t0 = time.time()
        await c.write_gatt_char(CTRL, bytes([0x11]) + struct.pack(">QI", rs, n), response=True)
        while True:
            m = await asyncio.wait_for(q.get(), 30)
            if m[0] == 0x03: buf += m[1:]
            elif m[0] == 0x04: break
            elif m[0] == 0x01 and m[1] != 0: raise SystemExit(f"ack error {m[1]}")
        dt = time.time() - t0
        recs = [buf[i:i + REC] for i in range(0, len(buf) - REC + 1, REC)]
        ts0 = struct.unpack(">I", recs[0][:4])[0] if recs else 0
        if ts0 & 0x80000000 or ts0 < 1_500_000_000: ts0 = int(time.time())
        day = time.strftime("%Y-%m-%d", time.localtime(ts0)); stem = f"{time.strftime('%H%M%S', time.localtime(ts0))}_seq{rs}"
        d = DATA / "raw" / day; d.mkdir(parents=True, exist_ok=True)
        (d / f"{stem}.bin").write_bytes(buf)
        import opuslib
        dec = opuslib.Decoder(16000, 1)
        with wave.open(str(d / f"{stem}.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            pos = 0; tmap = []  # [audio_sec, record_unix_ts] so gaps (VAD) map back to wall clock
            for r in recs:
                rts = struct.unpack(">I", r[:4])[0]
                if not (rts & 0x80000000): tmap.append([pos / 16000, rts])
                for f in frames_of([r]):
                    try: pcm = dec.decode(bytes(f), 960); w.writeframes(pcm); pos += len(pcm) // 2
                    except Exception: pass
        (d / f"{stem}.json").write_text(json.dumps({"started_at": ts0, "packets": len(recs), "read_seq": rs, "tmap": tmap, **meta}))
        stf.write_text(json.dumps({"next_seq": rs + len(recs)}))
        print(json.dumps({"saved": str(d / stem), "bytes": len(buf), "packets": len(recs), "sec": round(dt, 1), "kBps": round(len(buf) / 1024 / max(dt, .01), 1)}))
        # No ADVANCE sent: pendant keeps everything.

def main():
    p = argparse.ArgumentParser(); p.add_argument("--address"); p.add_argument("--info", action="store_true")
    p.add_argument("--max-packets", type=int, default=0); asyncio.run(run(p.parse_args()))
if __name__ == "__main__": main()
