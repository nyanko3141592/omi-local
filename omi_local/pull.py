"""Pull offline recordings from an Omi pendant over BLE. NEVER deletes from the pendant
unless --delete-after-save is given (not used by default)."""
import argparse, asyncio, json, os, struct, sys, time, wave
from pathlib import Path
from pendant_collector.collector import OmiDesktopCollector

DATA = Path(os.environ.get("OMI_DATA_DIR", Path.home() / "OmiData"))
RAW = DATA / "raw"

def decode_to_wav(frames, out: Path, rate=16000):
    import opuslib
    dec = opuslib.Decoder(rate, 1)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        for f in frames:
            try: w.writeframes(dec.decode(bytes(f[3:]), 960))
            except Exception: pass

async def run(args):
    c = OmiDesktopCollector(agent_url="http://127.0.0.1:9/none", secret="x", address=args.address,
                            dry_run_delete=True, use_lease=False)
    dev = await c._resolve_device()
    client = await c._open_client(c._connect_target(dev))
    try:
        files = await c.list_files(client)
        print(json.dumps({"device": getattr(dev, "address", str(dev)), "files": len(files),
                          "total_bytes": sum(f.size for f in files)}))
        if args.list: return
        state = DATA / "state" / "pulled.json"; state.parent.mkdir(parents=True, exist_ok=True)
        done = set(json.loads(state.read_text())) if state.exists() else set()
        for f in files[: args.max_files or None]:
            if f.key in done: continue
            t0 = time.time(); data = await c.read_file(client, f, index=f.index); dt = time.time() - t0
            ts = f.timestamp if 1_500_000_000 <= f.timestamp <= 4_102_444_800 else int(time.time())
            day = time.strftime("%Y-%m-%d", time.localtime(ts)); stem = time.strftime("%H%M%S", time.localtime(ts)) + f"_{f.size}"
            d = RAW / day; d.mkdir(parents=True, exist_ok=True)
            (d / f"{stem}.bin").write_bytes(data)
            decode_to_wav(c.build_storage_frames(data), d / f"{stem}.wav")
            (d / f"{stem}.json").write_text(json.dumps({"started_at": ts, "size": f.size, "pendant_ts": f.timestamp}))
            done.add(f.key); state.write_text(json.dumps(sorted(done)))
            print(json.dumps({"saved": str(d / stem), "bytes": len(data), "sec": round(dt, 1), "kBps": round(len(data) / 1024 / max(dt, .01), 1)}))
            # deletion intentionally not implemented in trial phase
    finally:
        await client.disconnect()

def main():
    p = argparse.ArgumentParser(); p.add_argument("--address"); p.add_argument("--list", action="store_true")
    p.add_argument("--max-files", type=int, default=0)
    asyncio.run(run(p.parse_args()))

if __name__ == "__main__": main()
