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

# Extract file_path from JSON
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)

if [ -z "$file_path" ]; then
    # No file path found in input, allow
    exit 0
fi

# Get the directory containing the file
file_dir=$(dirname "$file_path")

if [ ! -d "$file_dir" ]; then
    # Directory doesn't exist yet (new file), allow
    exit 0
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
