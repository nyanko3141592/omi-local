#!/usr/bin/env bash
# Read-only health check. Exit 0 if everything is OK.
cd "$(dirname "$0")"; DATA="${OMI_DATA_DIR:-$HOME/OmiData}"; rc=0
ok(){ echo "OK   $*"; }; ng(){ echo "FAIL $*"; rc=1; }
command -v whisper-cli >/dev/null && ok whisper-cli || ng "whisper-cli (brew install whisper-cpp)"
[[ -x .venv/bin/python ]] && .venv/bin/python -c "import bleak, opuslib" 2>/dev/null && ok "venv (bleak, opuslib)" || ng "venv: run ./setup.sh"
[[ -s models/ggml-large-v3-turbo.bin ]] && ok "whisper model" || ng "whisper model missing"
[[ -s models/ggml-silero-v5.1.2.bin ]] && ok "VAD model" || ng "VAD model missing"
[[ -d "$DATA" ]] && ok "data dir $DATA" || ng "data dir $DATA"
st=$(launchctl print "gui/$(id -u)/me.omi-local.watch" 2>/dev/null | awk '/^\tstate/{print $3; exit}')
[[ "$st" == running ]] && ok "launchd me.omi-local.watch running" || ng "launchd watcher not running (state=$st)"
L=$(ls -t "$DATA"/logs/sync-*.log 2>/dev/null | head -1)
if [[ -n "$L" ]]; then tail -1 "$L" | grep -qiE "error|permission|timeout" && ng "last log line: $(tail -1 "$L")" || ok "last log: $(tail -1 "$L")"; fi
if [[ -n "$L" ]] && tail -1 "$L" | grep -q "scan error"; then
  n=$(tail -20 "$L" | grep -c "scan error")
  ng "Bluetooth permission: watcher scans time out ($n of last 20 log lines). launchd's Python needs Bluetooth: System Settings > Privacy & Security > Bluetooth > Python ON (not listed? run 'make sync' in Terminal and allow), then 'make stop && make start'"
fi
exit $rc
