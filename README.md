# omi-local

Free, local alternative to Omi's paid sync: your Mac pulls recordings from the **Omi pendant** over BLE when you get home,
transcribes them on-device (whisper.cpp + Silero VAD), and writes per-day Markdown + JSONL that any AI agent can read.
Nothing is uploaded. Nothing is ever deleted from the pendant.

## AIに渡すだけ / Just hand it to your AI agent

Copy-paste this to an AI agent that has shell access to your Mac (Claude Code, Codex, Cursor, …):

```
Set up https://github.com/nyanko3141592/omi-local on this Mac by following AGENTS.md exactly
(section "Setup procedure"). Run ./setup.sh, then make doctor, and tell me which manual steps
I must do myself (Bluetooth permission, iPhone Shortcut). Never delete anything from the pendant.
```

日本語: 上の文をそのままエージェントに貼れば、AGENTS.md の手順通りにセットアップします。人間がやるのは「Bluetooth許可」と「iPhoneショートカット」だけです。

## First-time setup / 初回セットアップ (human steps, in order)

After `./setup.sh` (or your agent) finishes:
1. Delete the Omi iPhone app / iPhoneのOmiアプリを削除
2. iOS Settings → Bluetooth → Omi (i) → **Forget This Device** / このデバイスの登録を解除
3. ⚠️ **Bluetooth permission for Python (required) / PythonのBluetooth許可（必須）** — the watcher is Python started by launchd and cannot scan without it. System Settings → Privacy & Security → Bluetooth → **Python** on. If Python isn't listed, run `cd ~/Dev/omi-local && make sync` in Terminal and allow the prompt. Then `make stop && make start`.
   Symptom if missing: every log line is `scan error (TimeoutError())`, and `make doctor` reports `Bluetooth permission`. ターミナルからの `make sync` は動くのに自動同期が動かない場合はこれです。
4. Press the pendant button once / ペンダントのボタンを1回押す
5. After a few minutes: `make logs` → confirm `time sync`, `pulled`, and (if enabled) `tail ~/OmiData/logs/advance.log` shows `ADVANCE … ack=0`.
6. Optional: don't sleep on power — System Settings → Battery → Options, or `sudo pmset -c sleep 0`.

### Verified run / 実機確認 (2026-10, Omi CV 1, fw 3.0.21, Apple Silicon Mac)
First real sync: ~45k packets (~20 MB) pulled and verified in ~7.5 min, 24 verified ADVANCEs (all ack=0), clock skew −1 s after time sync,
23 recordings transcribed; the one recording with an empty transcript kept its audio as designed.

Daily use, config, troubleshooting, firmware updates, backup: **[docs/OPERATIONS.md](docs/OPERATIONS.md)**.

## How it works / 仕組み

Design: **the Mac is the pendant's only BLE central** (delete the Omi iPhone app and forget the device in iOS Bluetooth settings).

1. `me.omi-local.watch` (launchd, KeepAlive) runs a duty-cycled BLE scan (8 s on / 52 s off, ~0% CPU).
2. When the pendant appears (and every 15 min while it stays visible) one sync pass runs:
   set the pendant clock from the Mac → pull **all** unread audio in verified chunks (a dropped link resumes next time) →
   optional ADVANCE of exactly the verified range → disconnect → transcribe → append to `~/OmiData/days/` + `index.jsonl` →
   optional deletion of the local audio once the transcript is verified.
3. Between syncs nothing is connected.

## Data retention / 削除設定 (`~/OmiData/config.json`)

| key | default | meaning |
|---|---|---|
| `advance_pendant` | `false` | After a chunk is written, fsynced, re-read (size + sha256) and opus-decodable, send ADVANCE for exactly that range so the pendant frees space. Never past unverified data. Logged to `logs/advance.log`. |
| `delete_audio_after_transcript` | `false` | Delete `.bin`/`.wav` once the transcript is non-empty and present in both `days/*.md` and `index.jsonl`. Failed or empty transcripts keep their audio. Logged to `logs/delete.log`. |
| `sync_time` | `true` | Write the Mac's unix time to the pendant on each connect (same as the official app: u32 LE → `19b10031-…`), read back from `19b10032-…`. |

Example (transcripts only, nothing kept on the pendant): `{"advance_pendant": true, "delete_audio_after_transcript": true}`.
Env `OMI_ADVANCE_PENDANT=0` etc. overrides per run. CLEAR is never sent.

## Mac sleep / スリープ (human step)

Sync only happens while the Mac is awake. Recommended for a desktop/always-plugged Mac (needs your password, do it yourself):
- System Settings → Battery/Energy → Options → **Prevent automatic sleeping on power adapter when the display is off** = on
- or `sudo pmset -c sleep 0` (on charger only; revert with `sudo pmset -c sleep 1`). Leave battery settings alone.

## Commands / コマンド

| | |
|---|---|
| `./setup.sh` | idempotent install (brew deps, venv, models, launchd watcher) |
| `make doctor` | health check |
| `make sync` | sync now (manual, 20 s scan) |
| `make stop` / `make start` | stop / start the watcher |
| `make logs` | recent log lines (`~/OmiData/logs/`) |
| `make uninstall` | remove the watcher (keeps code and data) |

Tunables (env in the plist): `OMI_SCAN_ON_S`, `OMI_SCAN_OFF_S`, ``OMI_RESYNC_MIN`, `OMI_DATA_DIR`.

## Optional: keep the Omi iPhone app / iPhoneアプリを残す場合（ショートカット）

Only if you keep the official app: the pendant accepts one central, so make the iPhone let go at home.
Shortcuts → オートメーション: **Wi-Fi** (home network) **接続時 / When joining** → **すぐに実行** → **Bluetoothを設定: オフ**;
same network **接続解除時 / When leaving** → **Bluetoothを設定: オン**. Caveat: AirPods / Apple Watch disconnect at home.
Don't enable `advance_pendant` in this mode if you also want the app to get the recordings.

## Privacy
`.gitignore` excludes audio, transcripts, models, logs, keys. Data lives only in `~/OmiData`.

## Transcription quality
whisper large-v3-turbo + Silero VAD + `--suppress-nst`, then a filter drops repeated-token hallucinations
(e.g. `どんどんどん…`) and stock phrases (`ご視聴ありがとうございました`). No speaker labels.


## Firmware 3.0.20+ (ring-buffer storage) — use `omi_local.ring`
Omi CV 1 / fw 3.0.21 does NOT use the old file protocol (`pull.py` / pendant-collector stall at 0 bytes).
It uses the ring protocol (omi `app/lib/services/devices/ring_protocol.dart`): status read on `...5782`,
commands on `...5781` (`0x10` INFO, `0x11` READ start_seq+count, `0x12` ADVANCE = reclaim). Records are 444 B
(`[ts:4 BE][440 B packed opus]`). `ring.py` reads unread packets and **never sends ADVANCE/CLEAR**, so the
pendant keeps everything (it will re-read from read_seq each time until advance is enabled later).
```bash
.venv/bin/python -m omi_local.ring --info      # fw, unread packets, free bytes
.venv/bin/python -m omi_local.ring             # pull unread -> ~/OmiData/raw/<day>/
.venv/bin/python -m omi_local.transcribe
```
Measured: ~38 KB/s over BLE on M-series Mac (≈ 0.2 MB per minute of audio).

## Troubleshooting
- LED: solid red = on, not connected; blinking red = time not synced; solid blue = connected (to phone *or* Mac);
  green+red/blue blinking = charging; purple = factory reset in progress.
- Only one BLE central at a time: if the phone Omi app is connected the pendant won't show up. Turn off phone
  Bluetooth or kill the app, press the button once, scan again (`pendant-collector scan` or `ring --info`).
- No pairing/bonding needed on macOS; no factory reset needed.
- Without phone time sync, record timestamps may carry the uptime flag; ring.py then falls back to pull time.
