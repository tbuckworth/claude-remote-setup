#!/bin/bash
# Review git commits using claude -p
# Triggered on PostToolUse for Bash commands

set -e

LOG=/tmp/hook-debug.log

# Read hook input from stdin
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only process git commits
if [[ "$COMMAND" != *"git commit"* ]]; then
    exit 0
fi

echo "[review-changes] git commit detected at $(date)" >> "$LOG"

# Get the diff of the last commit
DIFF=$(git diff HEAD~1..HEAD 2>/dev/null || echo "")
if [ -z "$DIFF" ]; then
    echo "[review-changes] no diff, exiting" >> "$LOG"
    exit 0
fi

# Limit diff size
DIFF_TRUNCATED=$(echo "$DIFF" | head -c 8000)

echo "[review-changes] calling claude -p..." >> "$LOG"

# Use default model (no --model flag = uses user's configured model)
REVIEW=$(echo "$DIFF_TRUNCATED" | command claude -p "You review git diffs. Rules: (1) ONLY report bugs, security issues, or logic errors. (2) If none found, respond with exactly: none. (3) No preamble, no 'Here'\''s my review', no style suggestions. Just bullet points or 'none'." 2>/dev/null || echo "")

echo "[review-changes] result: $REVIEW" >> "$LOG"

# Skip empty or "none" responses
REVIEW_TRIMMED=$(echo "$REVIEW" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
if [ -z "$REVIEW" ] || [ "$REVIEW_TRIMMED" = "none" ] || [ "$REVIEW_TRIMMED" = "none." ]; then
    echo "[review-changes] nothing to report, skipping" >> "$LOG"
    exit 0
fi

ESCAPED_REVIEW=$(echo "$REVIEW" | jq -Rs '.')

OUTPUT="{\"systemMessage\": ${ESCAPED_REVIEW}}"
echo "[review-changes] OUTPUT: $OUTPUT" >> "$LOG"
echo "$OUTPUT"
