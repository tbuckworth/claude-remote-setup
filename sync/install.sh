#!/bin/bash
# Run sync/sync_instructions.py every hour on this machine: a systemd user timer on Linux (the desktop),
# a launchd agent on macOS. On the Mac it also retires ~/.claude/sync-config.sh, which used to copy the
# Mac's instructions, settings and credentials over the desktop's.
set -euo pipefail

REPO="$HOME/pyg/claude-remote-setup"
SCRIPT="$REPO/sync/sync_instructions.py"
[ -f "$SCRIPT" ] || { echo "missing $SCRIPT: clone tbuckworth/claude-remote-setup to $REPO first" >&2; exit 1; }

case "$(uname)" in
Linux)
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT_DIR/sync-instructions.service" <<EOF
[Unit]
Description=Pull agent instructions from GitHub and rebuild ~/.codex/AGENTS.md (claude-remote-setup/sync)

[Service]
Type=oneshot
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 $SCRIPT
TimeoutStartSec=600
EOF
    cat > "$UNIT_DIR/sync-instructions.timer" <<EOF
[Unit]
Description=Pull agent instructions from GitHub every hour

[Timer]
OnBootSec=5min
OnCalendar=hourly
RandomizedDelaySec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now sync-instructions.timer
    systemctl --user start sync-instructions.service
    journalctl --user -u sync-instructions.service -n 3 --no-pager -o cat
    ;;
Darwin)
    PLIST="$HOME/Library/LaunchAgents/com.titus.sync-instructions.plist"
    LOG="$HOME/Library/Logs/sync-instructions.log"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.titus.sync-instructions</string>
    <key>ProgramArguments</key>
    <array><string>/usr/bin/python3</string><string>$SCRIPT</string></array>
    <key>EnvironmentVariables</key>
    <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
    <key>StartInterval</key><integer>3600</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    OLD="$HOME/.claude/sync-config.sh"
    if [ -f "$OLD" ] && ! grep -q "sync-config.sh is retired" "$OLD"; then
        RETIRED="$OLD.retired-$(date +%F)"
        mv "$OLD" "$RETIRED"
        cat > "$OLD" <<EOF
#!/bin/bash
echo "sync-config.sh is retired. Agent instructions now come from GitHub: merge changes to config/AGENTS.*.md" >&2
echo "in tbuckworth/claude-remote-setup and each machine pulls them within the hour (sync/README.md there)." >&2
echo "Settings, hooks and credentials are no longer copied to the desktop. The old script: $RETIRED" >&2
exit 1
EOF
        chmod +x "$OLD"
        echo "retired $OLD (old copy: $RETIRED)"
    fi
    sleep 5
    tail -n 3 "$LOG"
    ;;
*)
    echo "unsupported OS: $(uname)" >&2
    exit 1
    ;;
esac
