"""Reader for Omi firmware >=3.0.20 ring-buffer storage.
Per connect: sync pendant clock from the Mac, then pull ALL unread packets in chunks. Each chunk is written,
fsynced, re-read and verified (size + sha256 + opus decodable) BEFORE anything else. Only if config
`advance_pendant` is on, ADVANCE is sent for exactly that verified range (logged to logs/advance.log).
A dropped connection loses at most the in-flight chunk; the next connect resumes from the pendant read_seq /
local cursor. CLEAR is never sent."""
import argparse, asyncio, hashlib, json, os, struct, time, wave
from pathlib import Path
from bleak import BleakClient, BleakScanner
from omi_local import config
CTRL = "30295781-4301-eabd-2904-2849adfeae43"; STATUS = "30295782-4301-eabd-2904-2849adfeae43"
BATT = "00002a19-0000-1000-8000-00805f9b34fb"  # standard Battery Service 0x180F / Battery Level 0x2A19
DIS_FW = "00002a26-0000-1000-8000-00805f9b34fb"
TIME_W = "19b10031-e8f2-537e-4f6c-d104768a1214"; TIME_R = "19b10032-e8f2-537e-4f6c-d104768a1214"
DATA = config.DATA
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
    from omi_local import pairing
    saved = config.get("pendant_address")
    if address and saved and address != saved: raise SystemExit(f"refusing {address}: paired pendant is {saved} (make unpair to change)")
    if address: return address
    a = pairing.choose(await pairing.scan_all(15))
    if not a: raise SystemExit("paired pendant not found" if saved else "no single unpaired Omi found (make pair)")
    return a

async def sync_time(c):
    """Same as the official app (omi_connection.dart performSyncTime): u32 LE unix seconds -> 19b10031."""
    now = int(time.time())
    await c.write_gatt_char(TIME_W, struct.pack("<I", now), response=True)
    try:
        rb = bytes(await c.read_gatt_char(TIME_R)); dev = struct.unpack("<I", rb[:4])[0]
        msg = f"time sync wrote={now} readback={dev} diff={dev - int(time.time())}s"
    except Exception as e:
        msg = f"time sync wrote={now} readback failed: {e!r}"
    config.log("sync.log", msg); print(msg)

def fsync_write(p: Path, data: bytes):
    with open(p, "wb") as f: f.write(data); f.flush(); os.fsync(f.fileno())
    dfd = os.open(p.parent, os.O_RDONLY); os.fsync(dfd); os.close(dfd)

def save_chunk(buf, rs, meta):
    """Write .bin/.wav/.json; return (verified: bool, stem path, detail)."""
    recs = [bytes(buf[i:i + REC]) for i in range(0, len(buf) - REC + 1, REC)]
    buf = b"".join(recs)
    ts0 = struct.unpack(">I", recs[0][:4])[0] if recs else 0
    if ts0 & 0x80000000 or ts0 < 1_500_000_000: ts0 = int(time.time())
    day = time.strftime("%Y-%m-%d", time.localtime(ts0)); stem = f"{time.strftime('%H%M%S', time.localtime(ts0))}_seq{rs}"
    d = DATA / "raw" / day; d.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(buf).hexdigest()
    fsync_write(d / f"{stem}.bin", buf)
    import opuslib, io
    dec = opuslib.Decoder(16000, 1); pcmio = io.BytesIO(); pos = 0; tmap = []; ok = bad = 0
    for r in recs:
        rts = struct.unpack(">I", r[:4])[0]
        if not (rts & 0x80000000): tmap.append([pos / 16000, rts])
        for f in frames_of([r]):
            try: pcm = dec.decode(bytes(f), 960); pcmio.write(pcm); pos += len(pcm) // 2; ok += 1
            except Exception: bad += 1
    wavp = d / f"{stem}.wav"
    with wave.open(str(wavp), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcmio.getvalue())
    with open(wavp, "rb+") as f: os.fsync(f.fileno())
    back = (d / f"{stem}.bin").read_bytes()
    verified = len(back) == len(recs) * REC and hashlib.sha256(back).hexdigest() == sha and ok > 0 and bad <= 0.1 * (ok + bad)
    fsync_write(d / f"{stem}.json", json.dumps({"started_at": ts0, "packets": len(recs), "read_seq": rs, "sha256": sha,
        "frames_ok": ok, "frames_bad": bad, "verified": verified, "tmap": tmap, **meta}).encode())
    return verified, len(recs), d / stem, f"packets={len(recs)} sha256={sha[:12]} frames ok={ok} bad={bad}"

def record_battery(level):
    """Append to state/battery_history.jsonl, write battery.json {level, ts, drain_pct_per_hour}."""
    now = int(time.time()); h = DATA / "state" / "battery_history.jsonl"; h.parent.mkdir(parents=True, exist_ok=True)
    hist = [json.loads(l) for l in h.open()] if h.exists() else []
    with h.open("a") as f: f.write(json.dumps({"ts": now, "level": level}) + "\n")
    hist.append({"ts": now, "level": level})
    # drain over the latest monotonic-decreasing run (ignores charging), needs >=1h span
    run = [hist[-1]]
    for x in reversed(hist[:-1]):
        if x["level"] >= run[-1]["level"]: run.append(x)
        else: break
    drain = None
    if len(run) > 1 and now - run[-1]["ts"] >= 3600:
        drain = round((run[-1]["level"] - level) / ((now - run[-1]["ts"]) / 3600), 2)
    out = {"level": level, "ts": now, "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), "drain_pct_per_hour": drain,
           "hours_left_est": round(level / drain, 1) if drain else None}
    (DATA / "battery.json").write_text(json.dumps(out))
    config.log("battery.log", f"battery {level}% drain={drain}%/h"); print(json.dumps({"battery": out}))

async def wait_ack(q, t=5):
    end = time.time() + t
    while time.time() < end:
        m = await asyncio.wait_for(q.get(), max(.1, end - time.time()))
        if m[0] == 0x01: return m[1]
    return None

async def run(a):
    q = asyncio.Queue()
    addr = await find(a.address)
    async with BleakClient(addr, timeout=45) as c:
        fw = bytes(await c.read_gatt_char(DIS_FW)).decode(errors="ignore")
        from omi_local import pairing
        serial = await pairing.read_serial(c); want = config.get("pendant_serial")
        if want and serial != want:
            config.log("sync.log", f"serial mismatch at {addr}: got {serial!r}, paired {want!r}; aborting (no pull, no ADVANCE)")
            raise SystemExit("serial mismatch")
        if not config.get("pendant_address"):
            config.set_many({"pendant_address": addr, "pendant_serial": serial}); config.log("sync.log", f"auto-paired {addr} serial={serial}")
        elif not want and serial: config.set_many({"pendant_serial": serial})
        if config.get("sync_time") and not a.info:
            try: await sync_time(c)
            except Exception as e: config.log("sync.log", f"time sync failed: {e!r}")
        try: record_battery((await c.read_gatt_char(BATT))[0])
        except Exception as e: config.log("sync.log", f"battery read failed: {e!r}")
        st = struct.unpack("<4I", bytes(await c.read_gatt_char(STATUS))[:16])
        await c.start_notify(CTRL, lambda _, d: q.put_nowait(bytes(d)))
        async def info():
            await c.write_gatt_char(CTRL, bytes([0x10]), response=True)
            while True:
                m = await asyncio.wait_for(q.get(), 10)
                if m[0] == 0x02: return struct.unpack(">QQIQH", m[1:31])
        rs, ws, cap, dropped, psize = await info()
        meta = {"fw": fw, "used_bytes": st[0], "unread_packets": st[1], "free_bytes": st[2], "rtc_valid": st[3],
                "read_seq": rs, "write_seq": ws, "capacity": cap, "dropped": dropped, "packet_size": psize}
        print(json.dumps(meta))
        if a.info: return
        advance = config.get("advance_pendant"); chunk = a.max_packets or config.get("chunk_packets")
        stf = DATA / "state" / "ring.json"; stf.parent.mkdir(parents=True, exist_ok=True)
        st_local = json.loads(stf.read_text()) if stf.exists() else {}
        last = st_local.get("next_seq", 0)
        verified_upto = st_local.get("verified_upto", 0)
        # data already saved+verified locally but not yet advanced (e.g. advance failed last time)
        if advance and verified_upto > rs:
            await advance_to(c, q, min(verified_upto, ws), rs, "catch-up")
            rs = min(verified_upto, ws)
        if rs < last <= ws: rs = last
        total = 0
        while ws - rs > 0:
            n = min(ws - rs, chunk); buf = bytearray(); t0 = time.time()
            await c.write_gatt_char(CTRL, bytes([0x11]) + struct.pack(">QI", rs, n), response=True)
            while True:
                m = await asyncio.wait_for(q.get(), 30)
                if m[0] == 0x03: buf += m[1:]
                elif m[0] == 0x04: break
                elif m[0] == 0x01 and m[1] != 0: raise SystemExit(f"read ack error {m[1]}")
            ok, got, stem, detail = save_chunk(buf, rs, meta)
            dt = time.time() - t0
            print(json.dumps({"saved": str(stem), "verified": ok, "packets": got, "sec": round(dt, 1)}))
            if not ok or got == 0:
                config.log("sync.log", f"chunk seq {rs} NOT verified ({detail}); stopping, no advance"); return
            new = rs + got
            stf.write_text(json.dumps({"next_seq": new, "verified_upto": new}))
            if advance: await advance_to(c, q, new, rs, f"{detail} serial={serial}")
            rs = new; total += got
            if got < n: break
            ws = max(ws, (await info())[1])
        config.log("sync.log", f"pulled {total} packets, now at seq {rs}")
        try: await c.write_gatt_char(CTRL, bytes([0x03]), response=True)
        except Exception: pass

async def advance_to(c, q, new, old, detail):
    while not q.empty(): q.get_nowait()
    await c.write_gatt_char(CTRL, bytes([0x12]) + struct.pack(">Q", new), response=True)
    s = await wait_ack(q)
    config.log("advance.log", f"ADVANCE {old}->{new} ({new - old} packets) ack={s} {detail}")
    if s not in (0, 10): raise SystemExit(f"advance ack {s}")

def main():
    p = argparse.ArgumentParser(); p.add_argument("--address"); p.add_argument("--info", action="store_true")
    p.add_argument("--max-packets", type=int, default=0); asyncio.run(run(p.parse_args()))
if __name__ == "__main__": main()
