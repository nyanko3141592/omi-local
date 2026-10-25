# AGENTS.md — for AI agents

Two parts: **Setup procedure** (install on a user's Mac) and **Consuming the data** (read transcripts).
Hard rules: never send CLEAR; ADVANCE/audio deletion only via the config flags in code (never manually); never delete `~/OmiData` transcripts; never commit data.

## Setup procedure (deterministic)

1. **Prereqs** — check and stop with a clear message if missing:
   `uname -sm` → `Darwin arm64` (Intel works but slower); `command -v brew` (else ask the human to install https://brew.sh); ~3 GB free disk.
2. **Install** — `git clone https://github.com/nyanko3141592/omi-local ~/Dev/omi-local && cd ~/Dev/omi-local && ./setup.sh`
   (idempotent: brew `python whisper-cpp opus ffmpeg`, `.venv` + `requirements.txt`, models into `models/`
   (large-v3-turbo 1.5 GB, Silero VAD), `~/OmiData/*`, launchd `me.omi-local.watch`). Re-run safely on any failure.
3. **Human step: Bluetooth permission (required, most common failure)** — the watcher is Python started by launchd and
   needs its own Bluetooth permission; Terminal runs can work while the watcher fails. Tell the human: System Settings → Privacy & Security → Bluetooth → **Python** on. If Python isn't listed, run `cd ~/Dev/omi-local && make sync` in Terminal and allow the prompt. Then `make stop && make start`.
   Symptom: every line in `~/OmiData/logs/sync-*.log` is `scan error (TimeoutError())`. **Always run `make doctor` after setup and after the
   first sync**; it FAILs with `Bluetooth permission` in this case. Don't treat the setup as done until it passes.
4. **Human steps: make the Mac the only central** — tell the human to:
   (a) delete the Omi iPhone app, (b) iOS Settings → Bluetooth → Omi (i) → **Forget This Device**,
   (c) press the pendant button once (LED solid red = advertising, not connected).
   Firmware updates need the app: reinstall it temporarily, update, then delete + forget again.
   (Alternative if they keep the app: README "Optional: keep the Omi iPhone app" Shortcut; then leave `advance_pendant` off.)
4b. **Retention** — ask the human, then write `~/OmiData/config.json` (see README "Data retention"). Defaults delete nothing.
   `{"advance_pendant": true, "delete_audio_after_transcript": true}` = pendant freed after verified transfer, only transcripts kept.
4c. **Human step: Mac sleep** — recommend README "Mac sleep" (needs sudo; never run pmset yourself).
5. **Verify** — `make doctor` must exit 0. Then `.venv/bin/python -m omi_local.ring --info` should print firmware/unread
   counts, and `make sync` should create `~/OmiData/days/<today>.md`. If the pendant isn't found: LED blue = still connected to the phone.
6. **Report** to the human: label `me.omi-local.watch`, stop with `make stop` (`launchctl bootout gui/$(id -u)/me.omi-local.watch`),
   data at `~/OmiData`. State the retention config. If `advance_pendant` is off, the pendant eventually fills (≈0.2 MB/min audio). Logs: `~/OmiData/logs/{sync,advance,delete}.log`.
6b. **Operations** — for day-to-day questions follow `docs/OPERATIONS.md` (commands, config, troubleshooting).
7. **Uninstall** — `make uninstall` (keeps code and data).

## Consuming the data (Grok Bots, Codex, any agent with shell on the Mac)

Data lives OUTSIDE this repo, in `~/OmiData/` (override with `OMI_DATA_DIR`). Never commit it.

| Path | What |
|---|---|
| `~/OmiData/days/YYYY-MM-DD.md` | One file per day. YAML frontmatter (`date`, `source: omi-pendant`, `format: omi-local/v1`), then one `## HH:MM:SS <!-- id:... -->` section per recording with `- [HH:MM:SS] text` segments (local time, Asia/Tokyo). Append-only. |
| `~/OmiData/index.jsonl` | One JSON line per recording: `id, date, started_at (unix), segments, md, wav, text`. Append-only. |
| `~/OmiData/raw/YYYY-MM-DD/` | Metadata `.json`, whisper `.whisper.json`; `.bin`/`.wav` audio only until transcribed if `delete_audio_after_transcript` is on (the `wav` path in index may no longer exist). |
| `~/OmiData/processed/<agent>.json` | Per-agent cursor. |

## Rules
- Read-only on `days/`, `index.jsonl`, `raw/`. Do not edit or delete.
- Mark progress WITHOUT deleting: keep your own cursor in `~/OmiData/processed/<agent-name>.json`,
  e.g. `{"processed_ids": ["2026-10-25_120000_12345"], "updated_at": "..."}`. Each agent has its own file,
  so multiple agents can process the same data independently.
- To find new work: read `index.jsonl`, skip ids already in your cursor file.
- Transcripts are raw ASR (whisper large-v3-turbo, ja); expect errors and no speaker labels.

## Example (nightly summary)
```bash
python3 - <<'PY'
import json, pathlib
d = pathlib.Path.home()/"OmiData"; cur = d/"processed"/"keiki.json"
seen = set(json.loads(cur.read_text())["processed_ids"]) if cur.exists() else set()
new = [json.loads(l) for l in open(d/"index.jsonl") if json.loads(l)["id"] not in seen]
print(len(new))
PY
```

## Sync timing
New data appears only after the pendant was released by the iPhone and the watcher synced (usually within ~1 min of arriving home + transfer/transcribe time). `index.jsonl` is append-only.
