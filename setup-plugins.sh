#!/bin/bash
# setup-plugins.sh - Deploy Claude Code custom plugins and marketplace plugins
# Can be run standalone or called from setup-server.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Determine script directory (where the repo lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGINS_SRC="$SCRIPT_DIR/plugins"
PLUGINS_DEST="$HOME/.claude/plugins"

echo ""
echo "=== Claude Code Plugin Setup ==="
echo ""

# --- Step 1: Create plugins directory ---
log_info "Creating plugins directory at $PLUGINS_DEST..."
mkdir -p "$PLUGINS_DEST"

# --- Step 2: Copy custom plugins ---
CUSTOM_PLUGINS=(
    "assumption-debugger"
    "best-practices-validator"
    "commit-often"
    "doc-cross-checker"
    "refactoring-radar"
    "review-changes"
    "branch-guard"
)

for plugin in "${CUSTOM_PLUGINS[@]}"; do
    if [ -d "$PLUGINS_SRC/$plugin" ]; then
        log_info "Installing custom plugin: $plugin"
        cp -r "$PLUGINS_SRC/$plugin" "$PLUGINS_DEST/"
    else
        log_warn "Plugin source not found: $PLUGINS_SRC/$plugin (skipping)"
    fi
done

# Make all .sh files in plugins executable
find "$PLUGINS_DEST" -name "*.sh" -exec chmod +x {} \;
log_info "Made all .sh files in plugins executable"

# --- Step 3: Install marketplace plugins ---
MARKETPLACE_PLUGINS=(
    "plugin-dev@claude-plugins-official"
    "code-simplifier@claude-plugins-official"
    "context7@claude-plugins-official"
)

if command -v claude &> /dev/null; then
    log_info "Claude CLI found, installing marketplace plugins..."
    for mp in "${MARKETPLACE_PLUGINS[@]}"; do
        log_info "Installing marketplace plugin: $mp"
        claude plugin install "$mp" 2>/dev/null || log_warn "Failed to install $mp (may already be installed)"
        claude plugin enable "$mp" 2>/dev/null || log_warn "Failed to enable $mp (may already be enabled)"
    done
else
    log_warn "Claude CLI not found. Marketplace plugins must be installed manually:"
    for mp in "${MARKETPLACE_PLUGINS[@]}"; do
        echo "  claude plugin install $mp && claude plugin enable $mp"
    done
fi

# --- Step 4: Copy settings.json if it doesn't exist ---
SETTINGS_SRC="$SCRIPT_DIR/config/settings.json"
SETTINGS_DEST="$HOME/.claude/settings.json"

if [ -f "$SETTINGS_SRC" ]; then
    if [ ! -f "$SETTINGS_DEST" ]; then
        log_info "Copying settings.json to $SETTINGS_DEST..."
        cp "$SETTINGS_SRC" "$SETTINGS_DEST"
    else
        log_warn "Settings file already exists at $SETTINGS_DEST (not overwriting)"
    fi
else
    log_warn "No settings.json found in config/ (skipping)"
fi

# --- Done ---
echo ""
echo "============================================"
log_info "Plugin setup complete!"
echo "============================================"
echo ""
echo "Custom plugins installed:"
for plugin in "${CUSTOM_PLUGINS[@]}"; do
    if [ -d "$PLUGINS_DEST/$plugin" ]; then
        echo -e "  ${GREEN}✓${NC} $plugin"
    fi
done
echo ""
echo "Start a new Claude Code session to activate plugins."
echo ""
