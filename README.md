# omi-local

Use an Omi pendant with **no subscription and no cloud**: pull offline recordings over Bluetooth to a Mac,
transcribe locally with whisper.cpp (Metal), and write agent-readable Markdown/JSONL. See `AGENTS.md`.

```
pendant --BLE storage service--> omi_local.pull --> ~/OmiData/raw/<day>/*.bin,*.wav
                                  omi_local.transcribe (whisper.cpp) --> ~/OmiData/days/<day>.md + index.jsonl
                                  any agent (cron / bot) --> summaries, ToDos, Notion ...
```

## Setup (Apple Silicon)
```bash
brew install whisper-cpp ffmpeg opus
git clone https://github.com/nyanko3141592/omi-local ~/Dev/omi-local && cd ~/Dev/omi-local
git clone https://github.com/cgallic/omi-pendant-chronicle   # BLE storage protocol (used as a library)
python3 -m venv .venv && .venv/bin/pip install -e ./omi-pendant-chronicle/desktop-collector opuslib
mkdir -p models && curl -L -o models/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
```
Grant Bluetooth permission to your terminal / python when macOS asks.
The pendant accepts **one** BLE central: close the phone Omi app (or turn off phone Bluetooth) while syncing.

## Use
```bash
.venv/bin/pendant-collector scan          # find pendant
.venv/bin/python -m omi_local.pull --list # list stored recordings (count/bytes)
.venv/bin/python -m omi_local.pull --max-files 1
.venv/bin/python -m omi_local.transcribe
```
`pull` never deletes recordings from the pendant (trial phase). Already-pulled files are tracked in
`~/OmiData/state/pulled.json`.

## Auto-sync when home (launchd)
`launchd/me.omi-local.sync.plist.template` runs pull+transcribe every 15 min; when the pendant is in range
(= you're home) it syncs. Install: copy to `~/Library/LaunchAgents/me.omi-local.sync.plist`, then
`launchctl load ~/Library/LaunchAgents/me.omi-local.sync.plist`.

## Privacy
`.gitignore` excludes audio, transcripts, models, logs, keys. Data lives in `~/OmiData` outside the repo.

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

## Automatic sync (launchd)

`omi_local/sync.py` runs every 15 min (label `me.omi-local.sync`): ~20s BLE scan → if the pendant is present, pull new unread audio (never ADVANCE/CLEAR) → transcribe (Whisper + Silero VAD + hallucination filter) → append to `~/OmiData/days/` and `index.jsonl`. Absent = silent exit. File lock prevents overlap; 60s watchdog on the scan. Logs: `~/OmiData/logs/`.

```sh
sed "s|__REPO__|$PWD|g; s|__HOME__|$HOME|g" launchd/me.omi-local.sync.plist.template > ~/Library/LaunchAgents/me.omi-local.sync.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/me.omi-local.sync.plist   # enable
launchctl kickstart -k gui/$(id -u)/me.omi-local.sync                              # run now
launchctl bootout gui/$(id -u)/me.omi-local.sync                                   # disable
```

If the log shows `timeout (Bluetooth permission prompt pending?)`, grant Bluetooth to Python in System Settings → Privacy & Security → Bluetooth.

VAD model: `curl -L -o models/ggml-silero-v5.1.2.bin https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin`

## iPhoneを自動で手放す（ショートカット）

The pendant connects to only one BLE central at a time, so the iPhone must release it for the Mac's launchd sync to work. Use iOS Shortcuts → オートメーション:

1. **Wi-Fi**（自宅のSSIDを選択）→ **接続時** → **すぐに実行** → アクション「Bluetoothを設定: **オフ**」
2. **Wi-Fi**（同じSSID）→ **接続解除時** → **すぐに実行** → 「Bluetoothを設定: **オン**」

Caveat: while at home, AirPods / Apple Watch etc. are also disconnected from the iPhone.
