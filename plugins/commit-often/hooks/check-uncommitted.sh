#!/bin/bash

# Check for uncommitted changes before session end
# Blocks session exit if there are uncommitted changes

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # Not a git repo, allow exit
    echo '{"decision": "approve"}'
    exit 0
fi

# Count uncommitted changes (staged + unstaged + untracked)
changes=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

if [ "$changes" -gt 0 ]; then
    # Changes exist - block exit and remind to commit
    cat <<EOF
{
    "decision": "block",
    "reason": "You have $changes uncommitted change(s). Please commit your changes before ending the session. Use 'git status' to see what needs to be committed."
}
EOF
else
    # No changes, allow exit
    echo '{"decision": "approve"}'
fi
