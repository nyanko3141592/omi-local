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
