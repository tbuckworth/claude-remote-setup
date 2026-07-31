#!/bin/bash

# Block code edits when on main/master or detached HEAD.
# Approve if not in a git repo (nothing to protect).
#
# PreToolUse hooks receive tool context as JSON on stdin.
# The file path is at .tool_input.file_path or .tool_input.notebook_path
#
# Exit codes:
#   exit 0 = allow
#   exit 2 = block (stderr is shown to Claude as the reason)

# Read tool input from stdin
input=$(cat)

# Extract file_path from JSON. Claude edit tools provide it directly; Codex's
# apply_patch payload does not, so use the documented session cwd as a safe
# fallback and protect the repository containing that directory.
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)

if [ -z "$file_path" ]; then
    file_dir=$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null)
    if [ -z "$file_dir" ] || [ ! -d "$file_dir" ]; then
        exit 0
    fi
else
    file_dir=$(dirname "$file_path")
    if [ ! -d "$file_dir" ]; then
        # For a new file, walk up to the nearest existing parent directory.
        while [ ! -d "$file_dir" ] && [ "$file_dir" != "/" ]; do
            file_dir=$(dirname "$file_dir")
        done
    fi
fi

# Check git branch for the file's directory
branch=$(git -C "$file_dir" rev-parse --abbrev-ref HEAD 2>/dev/null)

if [ "$?" -ne 0 ]; then
    # Not a git repo -- nothing to protect
    exit 0
fi

if [ "$branch" = "HEAD" ] || [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    echo "Code changes are not allowed on $branch. Create a feature branch first: git checkout -b <branch-name>" >&2
    exit 2
fi

exit 0
