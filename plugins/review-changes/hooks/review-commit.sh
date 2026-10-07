#!/bin/bash
# Review git commits using claude -p
# Triggered on PostToolUse for Bash commands
#
# The reviewer is its own `claude -p`: a fixed model (REVIEW_CHANGES_MODEL, default sonnet), no tools, and
# --safe-mode (no plugins, hooks, CLAUDE.md or MCP servers), so it can only read the diff and answer; nothing
# is saved (--no-session-persistence). Only a successful answer reaches the agent, labelled as this hook's.
# A failed call is logged and dropped: on 2026-10-07 the user's default model (fable) had no usage credits
# left, `claude -p` printed "You're out of usage credits. Switch to another model, ..." and exited 1, the hook
# passed that on as a systemMessage, and the agent, believing its own session was out, stopped mid-task.
# The reviewer also used to load every plugin: the commit-often Stop hook then had it commit the agent's
# unfinished work itself.

set -e

LOG=/tmp/hook-debug.log
MODEL="${REVIEW_CHANGES_MODEL:-sonnet}"

# Read hook input from stdin
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only process git commits: `git commit` / `git -C DIR commit` at the start of a command (best effort: a quoted
# mention after a space still matches, which costs one review and nothing else)
COMMIT_RE='(^|[;&|({[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit([[:space:]]|$)'
if ! [[ "$COMMAND" =~ $COMMIT_RE ]]; then
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

echo "[review-changes] calling claude -p --model $MODEL..." >> "$LOG"

STATUS=0
REVIEW=$(echo "$DIFF_TRUNCATED" | command claude -p --safe-mode --tools "" --no-session-persistence \
    --model "$MODEL" "You review git diffs. Rules: (1) ONLY report bugs, security issues, or logic errors. (2) If none found, respond with exactly: none. (3) No preamble, no 'Here'\''s my review', no style suggestions. Just bullet points or 'none'." \
    2>>"$LOG") || STATUS=$?

echo "[review-changes] result (exit $STATUS): $REVIEW" >> "$LOG"

# A failed call is not a review: never hand its error text (a usage limit, an API error) to the agent
if [ "$STATUS" -ne 0 ]; then
    echo "[review-changes] claude -p failed, nothing passed on" >> "$LOG"
    exit 0
fi
case "$REVIEW" in
    "You're out of usage credits"*|"You've hit your"*|"API Error"*|"Claude AI usage limit reached"*)
        echo "[review-changes] claude -p answered with a limit or API error, nothing passed on" >> "$LOG"
        exit 0
        ;;
esac

# Skip empty or "none" responses
REVIEW_TRIMMED=$(echo "$REVIEW" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
if [ -z "$REVIEW" ] || [ "$REVIEW_TRIMMED" = "none" ] || [ "$REVIEW_TRIMMED" = "none." ]; then
    echo "[review-changes] nothing to report, skipping" >> "$LOG"
    exit 0
fi

ESCAPED_REVIEW=$(printf '[review-changes hook: an automatic review of the commit just made, by a separate claude -p (%s); not a message about this session]\n%s' "$MODEL" "$REVIEW" | jq -Rs '.')

OUTPUT="{\"systemMessage\": ${ESCAPED_REVIEW}}"
echo "[review-changes] OUTPUT: $OUTPUT" >> "$LOG"
echo "$OUTPUT"
