# Operations guide / 運用ガイド

## Daily flow / 毎日の流れ

1. Wear the pendant when you go out. It records speech to its own storage (no phone needed).
2. Come home near the Mac. Within ~1 min the watcher (`me.omi-local.watch`) sees it advertise.
3. Sync pass: set the pendant clock → pull all unread audio → verify (size, sha256, decodable) →
   ADVANCE exactly the verified range on the pendant (if `advance_pendant`) → disconnect.
4. Transcribe (whisper.cpp + VAD) → append to `~/OmiData/days/YYYY-MM-DD.md` and `index.jsonl` →
   delete local `.bin`/`.wav` once the transcript is verified (if `delete_audio_after_transcript`).
5. While the pendant stays near the Mac it re-syncs every 15 min.
6. Your agent reads new transcripts (e.g. a nightly summary + ToDos) → see "Agents".

## Commands / コマンド (run in the repo dir)

| command | what |
|---|---|
| `make start` / `make stop` | start / stop the watcher (`launchctl bootstrap|bootout gui/$(id -u)/me.omi-local.watch`) |
| `make sync` | one sync pass now (20 s scan) |
| `make logs` | last 30 lines of `~/OmiData/logs/sync-*.log` |
| `make doctor` | health check (exit 0 = OK) |
| `make uninstall` | remove the watcher (keeps code and data) |

## Config / 設定 (`~/OmiData/config.json`)

```json
{"advance_pendant": true, "delete_audio_after_transcript": true, "sync_time": true}
```
- Turn deletion off: set `advance_pendant` and/or `delete_audio_after_transcript` to `false` (takes effect next sync, no restart needed).
- One-off override: `OMI_ADVANCE_PENDANT=0 make sync`.
- Repo defaults (no file) delete nothing. CLEAR is never sent.

## Where things live / 保存場所

| path | contents |
|---|---|
| `~/OmiData/days/YYYY-MM-DD.md` | transcripts per day (frontmatter + `- [HH:MM:SS] text`) |
| `~/OmiData/index.jsonl` | one line per recording (append-only) |
| `~/OmiData/raw/YYYY-MM-DD/` | metadata `.json`, `.whisper.json`; audio only until transcribed (if deletion on) |
| `~/OmiData/state/ring.json` | pendant read cursor (`next_seq`, `verified_upto`) — don't edit |
| `~/OmiData/processed/<agent>.json` | per-agent "already processed" cursor |
| `~/OmiData/logs/` | `sync-YYYY-MM.log`, `advance.log`, `delete.log`, `launchd.{out,err}.log` |

## Battery / 電池残量

- Every sync reads the pendant battery (standard 0x180F/0x2A19) → `~/OmiData/battery.json`
  (`level`, `time`, `drain_pct_per_hour`, `hours_left_est` once ≥1 h of discharge history), history in `state/battery_history.jsonl`, log `logs/battery.log`.
- On the go: iPhone app [ios/OmiBattery](../ios/OmiBattery/README.md) — one tap, reads and disconnects (doesn't block the Mac sync).

## Agents / エージェントの読み方

Read `index.jsonl`, skip ids listed in your own `~/OmiData/processed/<agent>.json` (`{"processed_ids": [...]}`),
summarize, then append the ids to that file. Never edit or delete `days/` or `index.jsonl`. Details: [AGENTS.md](../AGENTS.md).

## Is it healthy? / 正常確認

- `make doctor` all OK (it also detects the missing Bluetooth permission).
- After coming home, `make logs` shows `pendant appeared … -> sync`, `time sync … diff=0s`, `pulled N packets`, `transcribe ok`.
- `tail ~/OmiData/logs/advance.log` shows `ADVANCE a->b … ack=0`.
- `ls ~/OmiData/days/` has today's file.

## Troubleshooting / トラブル

| symptom | fix |
|---|---|
| Not detected | LED blue = connected to something else (phone). LED solid red = advertising. Press the button once; check battery/charging. |
| ⚠️ **Every scan times out** (`scan error (TimeoutError())` on every line; `make doctor`: `Bluetooth permission`) — most common | launchd's Python has no Bluetooth permission (Terminal `make sync` may still work). System Settings → Privacy & Security → Bluetooth → Python on. If Python isn't listed, run `cd ~/Dev/omi-local && make sync` in Terminal and allow the prompt. Then `make stop && make start`. |
| Phone still paired | Delete the Omi app; iOS Settings → Bluetooth → Omi (i) → Forget This Device. Only one central can connect. |
| Nothing syncs overnight | Mac was asleep. System Settings → Battery → Options → prevent sleep on power adapter, or `sudo pmset -c sleep 0`. |
| Transcription failed | Logged as `transcribe failed … (audio kept, retry later)`; it retries on the next sync. Run `make sync` or `.venv/bin/python -m omi_local.transcribe`. Check `make doctor` (model/whisper-cli). |
| Empty transcript | Audio is kept (`delete.log: KEEP … empty transcript`); delete manually if you're sure. |
| Pendant storage full | `.venv/bin/python -m omi_local.ring --info` → `free_bytes`. Ensure `advance_pendant` is on and `advance.log` shows `ack=0`. |
| Clock wrong | Needs `sync_time: true`; check `time sync … diff=` in the log. Timestamps recorded before the first sync may fall back to pull time. |
| Read/advance ack error | Logged; nothing unverified is advanced. Next sync resumes. Persistent → `make stop`, power-cycle pendant, `make start`. |

## Firmware updates / ファームウェア更新

Reinstall the Omi iPhone app temporarily → update the firmware → delete the app → iOS Bluetooth → Omi (i) → Forget This Device →
press the pendant button. Run `make sync` to confirm. (Ring protocol requires firmware ≥ 3.0.20.)

## Backup / バックアップ

With deletion on, the only remaining copy is the transcript in `~/OmiData` (audio is gone from the pendant and the Mac).
Back up `~/OmiData` yourself (Time Machine, etc.) if you want it. Nothing is uploaded anywhere.

## Uninstall / アンインストール

`make uninstall` (removes the launchd agent). Then optionally delete the repo dir. `~/OmiData` is never removed automatically.
