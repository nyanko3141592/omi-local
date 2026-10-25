"""Transcribe new WAVs in ~/OmiData/raw/<day>/ with whisper.cpp and write agent-readable outputs:
~/OmiData/days/YYYY-MM-DD.md (frontmatter + timestamped segments) and ~/OmiData/index.jsonl."""
import json, os, re, subprocess, time
from pathlib import Path
from omi_local import config
DATA = Path(os.environ.get("OMI_DATA_DIR", Path.home() / "OmiData"))
MODEL = os.environ.get("WHISPER_MODEL", str(Path(__file__).resolve().parent.parent / "models/ggml-large-v3-turbo.bin"))
VAD = os.environ.get("WHISPER_VAD_MODEL", str(Path(MODEL).parent / "ggml-silero-v5.1.2.bin"))
WHISPER = os.environ.get("WHISPER_BIN", "/opt/homebrew/bin/whisper-cli")

HALLU = ["ご視聴ありがとうございました", "チャンネル登録", "字幕", "おやすみなさい"]
def is_garbage(t):
    core = re.sub(r"[\s、。!?！？・…ー〜]", "", t)
    if len(core) < 2: return True
    if re.search(r"(.{1,4})\1{3,}", core): return True          # どんどんどんどん
    if len(core) >= 6 and len(set(core)) <= 3: return True
    return any(h in t for h in HALLU) and len(core) < 20

def hhmmss(sec): return time.strftime("%H:%M:%S", time.localtime(sec))

def transcribe(wav: Path):
    out = Path(str(wav.with_suffix("")) + ".whisper")
    cmd = [WHISPER, "-m", MODEL, "-l", os.environ.get("WHISPER_LANG", "ja"), "-oj", "-of", str(out), "-np", "-sns", "-nth", "0.6"]
    if Path(VAD).exists(): cmd += ["--vad", "-vm", VAD, "-vt", "0.5"]
    subprocess.run(cmd + [str(wav)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return json.loads(Path(str(out) + ".json").read_text())["transcription"]

def main():
    days = DATA / "days"; days.mkdir(parents=True, exist_ok=True)
    for wav in sorted((DATA / "raw").glob("*/*.wav")):
        if (wav.parent / (wav.stem + ".done")).exists():
            maybe_delete_audio(wav, f"{wav.parent.name}_{wav.stem}", days / f"{wav.parent.name}.md", None); continue
        meta = json.loads((wav.with_suffix(".json")).read_text()); base = meta["started_at"]
        tmap = meta.get("tmap") or []
        def wall(sec):
            best = None
            for a, ts in tmap:
                if a <= sec: best = ts + (sec - a)
                else: break
            return best if best is not None else base + sec
        segs = []
        try: tr = transcribe(wav)
        except Exception as e:
            config.log("sync.log", f"transcribe failed {wav.name}: {e!r} (audio kept, retry later)"); continue
        for s in tr:
            t = s["text"].strip()
            if t and not is_garbage(t): segs.append({"t": wall(s["offsets"]["from"] / 1000), "text": t})
        day = wav.parent.name; rec_id = f"{day}_{wav.stem}"
        md = days / f"{day}.md"
        if not md.exists():
            md.write_text(f"---\ndate: {day}\nsource: omi-pendant\nformat: omi-local/v1\n---\n\n# {day}\n")
        with md.open("a") as f:
            f.write(f"\n## {hhmmss(base)} <!-- id:{rec_id} -->\n\n" + "".join(f"- [{hhmmss(s['t'])}] {s['text']}\n" for s in segs))
        with (DATA / "index.jsonl").open("a") as f:
            f.write(json.dumps({"id": rec_id, "date": day, "started_at": base, "segments": len(segs),
                                "md": str(md), "wav": str(wav), "text": " ".join(s["text"] for s in segs)}, ensure_ascii=False) + "\n")
        (wav.parent / (wav.stem + ".done")).touch()
        print("transcribed", rec_id, len(segs))
        maybe_delete_audio(wav, rec_id, md, len(segs))

def maybe_delete_audio(wav, rec_id, md, nsegs):
    """Delete .bin/.wav only when the transcript is saved and verified. Metadata/whisper json are kept."""
    if not config.get("delete_audio_after_transcript"): return
    if nsegs is None:
        nsegs = max([json.loads(l).get("segments", 0) for l in (DATA / "index.jsonl").open() if json.loads(l).get("id") == rec_id] or [0])
    if nsegs == 0:
        config.log("delete.log", f"KEEP {rec_id}: empty transcript"); return
    in_md = md.exists() and f"id:{rec_id}" in md.read_text()
    in_idx = any(json.loads(l).get("id") == rec_id and json.loads(l).get("segments", 0) > 0 for l in (DATA / "index.jsonl").open())
    if not (in_md and in_idx):
        config.log("delete.log", f"KEEP {rec_id}: verify failed md={in_md} index={in_idx}"); return
    for ext in (".bin", ".wav"):
        p = wav.with_suffix(ext)
        if p.exists(): sz = p.stat().st_size; p.unlink(); config.log("delete.log", f"DELETE {p} ({sz} B) transcript verified")

if __name__ == "__main__": main()
