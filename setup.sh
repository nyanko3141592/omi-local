#!/usr/bin/env bash
# Idempotent setup for omi-local on macOS (Apple Silicon). Safe to re-run.
#   ./setup.sh            install everything + launchd watcher
#   ./setup.sh --no-agent install without the launchd watcher
set -euo pipefail
cd "$(dirname "$0")"; REPO="$PWD"
DATA="${OMI_DATA_DIR:-$HOME/OmiData}"; LABEL=me.omi-local.watch
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
say(){ printf '\n==> %s\n' "$*"; }
[[ "$(uname)" == Darwin ]] || { echo "macOS only"; exit 1; }
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
say "brew deps"; for f in python whisper-cpp opus ffmpeg; do brew list --formula "$f" >/dev/null 2>&1 || brew install "$f"; done
PY="$(brew --prefix)/bin/python3"
say "venv"; [[ -x .venv/bin/python ]] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip; .venv/bin/pip install -q -r requirements.txt
say "models"; mkdir -p models
[[ -s models/ggml-large-v3-turbo.bin ]] || curl -fL -o models/ggml-large-v3-turbo.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
[[ -s models/ggml-silero-v5.1.2.bin ]] || curl -fL -o models/ggml-silero-v5.1.2.bin https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin
mkdir -p "$DATA"/{raw,days,state,logs,processed}
if [[ "${1:-}" != --no-agent ]]; then
  say "launchd watcher ($LABEL)"
  launchctl bootout "gui/$(id -u)/me.omi-local.sync" 2>/dev/null || true; rm -f "$HOME/Library/LaunchAgents/me.omi-local.sync.plist"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  sed "s|__REPO__|$REPO|g; s|__DATA__|$DATA|g" launchd/$LABEL.plist.template > "$PLIST"
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
fi
say "done. Run: make doctor"
