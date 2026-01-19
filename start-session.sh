#!/bin/bash
# start-session.sh - Start or attach to Claude Code tmux session
# Provides persistent Claude Code sessions that survive disconnections

SESSION_NAME="claude"
WORKSPACE_DIR="${WORKSPACE:-/workspace/projects}"

# Ensure workspace exists
mkdir -p "$WORKSPACE_DIR"

# Check if tmux session exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Attaching to existing Claude session..."
    tmux attach-session -t "$SESSION_NAME"
else
    echo "Creating new Claude session..."

    # Create new tmux session
    tmux new-session -d -s "$SESSION_NAME" -c "$WORKSPACE_DIR"

    # Set up the window title
    tmux rename-window -t "$SESSION_NAME" "claude-code"

    # Send command to start Claude Code
    # Using send-keys allows the user to see Claude start up
    tmux send-keys -t "$SESSION_NAME" "cd $WORKSPACE_DIR && claude" Enter

    # Attach to the session
    tmux attach-session -t "$SESSION_NAME"
fi
