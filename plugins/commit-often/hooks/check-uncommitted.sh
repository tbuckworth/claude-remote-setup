#!/bin/bash

# Check for uncommitted changes before session end
# Blocks session exit if there are uncommitted changes, once per stop

# Codex and Claude Code both send the hook payload on stdin as JSON.
input=$(cat)

allow() {
    if [ -n "${PLUGIN_ROOT:-}" ]; then
        echo '{"continue": true}'
    else
        echo '{"decision": "approve"}'
    fi
}

# stop_hook_active means this stop follows a Stop hook's block, so the agent has already been
# reminded. It may be unable to commit (a review gate refusing the commit, a failing pre-commit
# hook); blocking again would keep it turning for ever.
if [ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)" = "true" ]; then
    allow
    exit 0
fi

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    allow
    exit 0
fi

# Count uncommitted changes (staged + unstaged + untracked)
changes=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

if [ "$changes" -gt 0 ]; then
    reason="You have $changes uncommitted change(s). Please commit your changes before ending the session. Use 'git status' to see what needs to be committed."
    # Codex continues the turn only for the Stop-specific block decision; Claude Code reads the
    # same shape.
    jq -n --arg reason "$reason" '{decision: "block", reason: $reason}'
else
    allow
fi
