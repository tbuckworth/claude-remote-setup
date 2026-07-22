#!/bin/bash

# Check for uncommitted changes before session end
# Blocks session exit if there are uncommitted changes

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [ -n "${PLUGIN_ROOT:-}" ]; then
        echo '{"continue": true}'
    else
        echo '{"decision": "approve"}'
    fi
    exit 0
fi

# Count uncommitted changes (staged + unstaged + untracked)
changes=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

if [ "$changes" -gt 0 ]; then
    reason="You have $changes uncommitted change(s). Please commit your changes before ending the session. Use 'git status' to see what needs to be committed."
    if [ -n "${PLUGIN_ROOT:-}" ]; then
        jq -n --arg reason "$reason" '{continue: false, stopReason: $reason, systemMessage: $reason}'
    else
        # Claude Code output schema.
        jq -n --arg reason "$reason" '{decision: "block", reason: $reason}'
    fi
else
    if [ -n "${PLUGIN_ROOT:-}" ]; then
        echo '{"continue": true}'
    else
        echo '{"decision": "approve"}'
    fi
fi
