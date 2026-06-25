#!/usr/bin/env bash
set -euo pipefail

LABEL="${REFERENCE_LAUNCHD_LABEL:-com.marctsai.reference-bot.refresh}"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"

echo "Uninstalled $LABEL"
