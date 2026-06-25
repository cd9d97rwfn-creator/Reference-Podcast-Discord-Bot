#!/usr/bin/env bash
set -euo pipefail

LABEL="${REFERENCE_LAUNCHD_LABEL:-com.marctsai.reference-bot.refresh}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${REFERENCE_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$REFERENCE_PYTHON_BIN"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON_BIN="$VIRTUAL_ENV/bin/python"
elif [[ -x "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" ]]; then
  PYTHON_BIN="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
else
  PYTHON_BIN="$(command -v python3)"
fi
HOUR="${REFERENCE_REFRESH_HOUR:-6}"
MINUTE="${REFERENCE_REFRESH_MINUTE:-10}"
LIMIT="${REFERENCE_REFRESH_LIMIT:-3}"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$REPO_DIR/data"

mkdir -p "$PLIST_DIR" "$LOG_DIR"

"$PYTHON_BIN" - "$PLIST_PATH" "$LABEL" "$REPO_DIR" "$PYTHON_BIN" "$HOUR" "$MINUTE" "$LIMIT" <<'PY'
from pathlib import Path
import plistlib
import sys

plist_path, label, repo_dir, python_bin, hour, minute, limit = sys.argv[1:]
program = (
    f"cd {repo_dir!r} && "
    f"{python_bin!r} -m reference_bot.local_refresh_deploy "
    f"--repo-dir {repo_dir!r} --limit {limit}"
)
payload = {
    "Label": label,
    "ProgramArguments": ["/bin/zsh", "-lc", program],
    "WorkingDirectory": repo_dir,
    "StartCalendarInterval": {"Hour": int(hour), "Minute": int(minute)},
    "StandardOutPath": str(Path(repo_dir) / "data" / "local-refresh.log"),
    "StandardErrorPath": str(Path(repo_dir) / "data" / "local-refresh.err.log"),
    "RunAtLoad": False,
}
with Path(plist_path).open("wb") as handle:
    plistlib.dump(payload, handle)
PY

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "Installed $LABEL"
echo "Schedule: daily at ${HOUR}:${MINUTE}"
echo "Log: $LOG_DIR/local-refresh.log"
echo "Error log: $LOG_DIR/local-refresh.err.log"
echo
echo "Run now with:"
echo "launchctl start $LABEL"
