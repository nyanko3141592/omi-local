# How agents consume this (Grok Bots, Codex "dots", anything with Mac shell)

Data lives OUTSIDE this repo, in `~/OmiData/` (override with `OMI_DATA_DIR`). Never commit it.

| Path | What |
|---|---|
| `~/OmiData/days/YYYY-MM-DD.md` | One file per day. YAML frontmatter (`date`, `source: omi-pendant`, `format: omi-local/v1`), then one `## HH:MM:SS <!-- id:... -->` section per recording with `- [HH:MM:SS] text` segments (local time, Asia/Tokyo). Append-only. |
| `~/OmiData/index.jsonl` | One JSON line per recording: `id, date, started_at (unix), segments, md, wav, text`. Append-only. |
| `~/OmiData/raw/YYYY-MM-DD/` | Raw pendant bytes (`.bin`), decoded `.wav`, whisper `.json`, metadata. |
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
New data arrives only while the iPhone has released the pendant (see README「iPhoneを自動で手放す（ショートカット）」) and the Mac's `me.omi-local.sync` launchd job runs (every 15 min). Treat `index.jsonl` as append-only.
