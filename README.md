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

## How it works / 仕組み

1. iPhone Shortcut turns iPhone Bluetooth **off** when you join home Wi-Fi → the pendant is released (it accepts only one BLE central).
2. `me.omi-local.watch` (launchd, KeepAlive) does a duty-cycled passive BLE scan (8 s on / 52 s off). When the pendant advertises it pulls **new unread** audio (no ADVANCE/CLEAR), disconnects, transcribes, appends.
3. Cooldown: re-syncs only after the pendant disappears (>10 min) and reappears, or at most every 60 min while visible.
4. Output in `~/OmiData/` (outside the repo) → see AGENTS.md "Consuming the data".

## Commands / コマンド

| | |
|---|---|
| `./setup.sh` | idempotent install (brew deps, venv, models, launchd watcher) |
| `make doctor` | health check |
| `make sync` | sync now (manual, 20 s scan) |
| `make stop` / `make start` | stop / start the watcher |
| `make logs` | recent log lines (`~/OmiData/logs/`) |
| `make uninstall` | remove the watcher (keeps code and data) |

Tunables (env in the plist): `OMI_SCAN_ON_S`, `OMI_SCAN_OFF_S`, `OMI_GONE_AFTER_S`, `OMI_RESYNC_MIN`, `OMI_DATA_DIR`.

## iPhoneを自動で手放す（ショートカット） / Release the pendant from iPhone automatically

Shortcuts app → オートメーション / Automation:
1. **Wi-Fi** (select your home network) → **接続時 / When joining** → **すぐに実行 / Run Immediately** → action **Bluetoothを設定: オフ / Set Bluetooth: Off**
2. **Wi-Fi** (same network) → **接続解除時 / When leaving** → **すぐに実行** → **Bluetoothを設定: オン / On**

Caveat: AirPods / Apple Watch are also disconnected from the iPhone while you're home.

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
