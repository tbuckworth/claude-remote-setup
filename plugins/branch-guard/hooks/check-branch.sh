#!/bin/bash

# Block code edits when on main/master or detached HEAD.
# Approve if not in a git repo (nothing to protect).
#
# PreToolUse hooks use exit codes:
#   exit 0 = allow
#   exit 2 = block (stderr is shown to Claude as the reason)

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

if [ "$?" -ne 0 ]; then
    # Not a git repo -- nothing to protect
    exit 0
fi

if [ "$branch" = "HEAD" ] || [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    echo "Code changes are not allowed on $branch. Create a feature branch first: git checkout -b <branch-name>" >&2
    exit 2
fi

exit 0
