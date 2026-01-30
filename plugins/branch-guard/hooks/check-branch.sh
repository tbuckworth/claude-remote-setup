#!/bin/bash

# Block code edits when on main/master or detached HEAD.
# Approve if not in a git repo (nothing to protect).

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

if [ "$?" -ne 0 ]; then
    # Not a git repo -- nothing to protect
    echo '{"decision": "approve"}'
    exit 0
fi

if [ "$branch" = "HEAD" ] || [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    cat <<EOF
{"decision": "block", "reason": "Code changes are not allowed on $branch. Create a feature branch first: git checkout -b <branch-name>"}
EOF
else
    echo '{"decision": "approve"}'
fi
