#!/bin/bash

set -euo pipefail

state="$CLAUDE_PLUGIN_ROOT/state/active.md"

approve() {
    if [ -n "${PLUGIN_ROOT:-}" ]; then
        echo '{"continue": true}'
    else
        echo '{"ok": true}'
    fi
}

if [ ! -f "$state" ]; then
    approve
    exit 0
fi

phase=$(grep '^current_phase:' "$state" | head -1 | sed 's/current_phase: *//;s/"//g')
if [ -z "$phase" ] || [ "$phase" = "done" ]; then
    approve
    exit 0
fi

ip=$(grep '^ip:' "$state" | head -1 | sed 's/ip: *//;s/"//g')
cost=$(grep '^estimated_cost_usd:' "$state" | head -1 | sed 's/estimated_cost_usd: *//')
reason="Active Lambda instance (phase: $phase, IP: $ip, cost: ~\$$cost). Check status or terminate it before ending."

if [ -n "${PLUGIN_ROOT:-}" ]; then
    jq -n --arg reason "$reason" '{continue: false, stopReason: $reason, systemMessage: $reason}'
else
    jq -n --arg reason "$reason" '{ok: false, reason: $reason}'
fi
