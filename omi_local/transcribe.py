"""Transcribe new WAVs in ~/OmiData/raw/<day>/ with whisper.cpp and write agent-readable outputs:
~/OmiData/days/YYYY-MM-DD.md (frontmatter + timestamped segments) and ~/OmiData/index.jsonl."""
import json, os, subprocess, time
from pathlib import Path
DATA = Path(os.environ.get("OMI_DATA_DIR", Path.home() / "OmiData"))
MODEL = os.environ.get("WHISPER_MODEL", str(Path(__file__).resolve().parent.parent / "models/ggml-large-v3-turbo.bin"))
WHISPER = os.environ.get("WHISPER_BIN", "/opt/homebrew/bin/whisper-cli")

def hhmmss(sec): return time.strftime("%H:%M:%S", time.localtime(sec))

def transcribe(wav: Path):
    out = wav.with_suffix("")
    subprocess.run([WHISPER, "-m", MODEL, "-l", os.environ.get("WHISPER_LANG", "ja"), "-oj", "-of", str(out), "-np", str(wav)], check=True)
    return json.loads(Path(str(out) + ".json").read_text())["transcription"]

def main():
    days = DATA / "days"; days.mkdir(parents=True, exist_ok=True)
    for wav in sorted((DATA / "raw").glob("*/*.wav")):
        if Path(str(wav.with_suffix("")) + ".json").exists() and (wav.parent / (wav.stem + ".done")).exists(): continue
        meta = json.loads((wav.with_suffix(".json")).read_text()); base = meta["started_at"]
        segs = []
        for s in transcribe(wav):
            t = s["text"].strip()
            if t: segs.append({"t": base + s["offsets"]["from"] / 1000, "text": t})
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

if __name__ == "__main__": main()
