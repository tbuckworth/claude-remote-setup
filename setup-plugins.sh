#!/bin/bash
# setup-plugins.sh - Install Claude Code plugins via marketplace system
# Can be run standalone or called from setup-server.sh
#
# Custom plugins are installed from the local marketplace in this repo.
# Official plugins are installed from claude-plugins-official.

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

echo ""
echo "=== Claude Code Plugin Setup ==="
echo ""

# --- Preflight: check for claude CLI ---
if ! command -v claude &> /dev/null; then
    log_error "Claude CLI not found in PATH."
    echo ""
    echo "Install it first:  npm install -g @anthropic-ai/claude-code"
    echo ""
    echo "Once installed, re-run this script."
    exit 1
fi

# --- Step 1: Register this repo as a local marketplace (idempotent) ---
log_info "Registering local marketplace from $SCRIPT_DIR ..."
claude plugin marketplace add "$SCRIPT_DIR" 2>/dev/null \
    || log_warn "Marketplace may already be registered (continuing)"

# --- Step 2: Clean up stale plugin directories ---
# Previous versions of this script used cp -r which put plugins in
# ~/.claude/plugins/<name>/ -- a location the system never reads from.
# Remove those dead copies so they don't cause confusion.
STALE_DIRS=(
    "assumption-debugger"
    "best-practices-validator"
    "branch-guard"
    "commit-often"
    "doc-cross-checker"
    "pre-mortem"
    "refactoring-radar"
    "review-changes"
)

for dir in "${STALE_DIRS[@]}"; do
    stale_path="$HOME/.claude/plugins/$dir"
    if [ -d "$stale_path" ]; then
        log_info "Removing stale plugin directory: $stale_path"
        rm -rf "$stale_path"
    fi
done

# --- Step 3: Install + enable custom plugins from local marketplace ---
CUSTOM_PLUGINS=(
    "assumption-debugger"
    "best-practices-validator"
    "branch-guard"
    "commit-often"
    "doc-cross-checker"
    "pre-mortem"
    "refactoring-radar"
    "review-changes"
)

log_info "Installing custom plugins from local marketplace..."
for plugin in "${CUSTOM_PLUGINS[@]}"; do
    log_info "  Installing: $plugin@custom-plugins"
    claude plugin install "$plugin@custom-plugins" 2>/dev/null \
        || log_warn "  Failed to install $plugin (may already be installed)"
    claude plugin enable "$plugin@custom-plugins" 2>/dev/null \
        || log_warn "  Failed to enable $plugin (may already be enabled)"
done

# --- Step 4: Install + enable official marketplace plugins ---
MARKETPLACE_PLUGINS=(
    "plugin-dev@claude-plugins-official"
    "code-simplifier@claude-plugins-official"
    "context7@claude-plugins-official"
)

log_info "Installing official marketplace plugins..."
for mp in "${MARKETPLACE_PLUGINS[@]}"; do
    log_info "  Installing: $mp"
    claude plugin install "$mp" 2>/dev/null \
        || log_warn "  Failed to install $mp (may already be installed)"
    claude plugin enable "$mp" 2>/dev/null \
        || log_warn "  Failed to enable $mp (may already be enabled)"
done

# --- Step 5: Merge enabledPlugins into settings.json ---
SETTINGS_SRC="$SCRIPT_DIR/config/settings.json"
SETTINGS_DEST="$HOME/.claude/settings.json"

if [ -f "$SETTINGS_SRC" ]; then
    if [ ! -f "$SETTINGS_DEST" ]; then
        log_info "Copying settings.json to $SETTINGS_DEST..."
        cp "$SETTINGS_SRC" "$SETTINGS_DEST"
    else
        log_warn "Settings file already exists at $SETTINGS_DEST (not overwriting)"
        log_info "Ensure enabledPlugins entries are present for all custom plugins."
    fi
else
    log_warn "No settings.json found in config/ (skipping)"
fi

# --- Step 6: Ensure hook scripts are executable ---
PLUGINS_CACHE="$HOME/.claude/plugins/cache/custom-plugins"

log_info "Setting hook script permissions..."
chmod +x "$PLUGINS_CACHE/branch-guard/1.0.0/hooks/check-branch.sh" 2>/dev/null || true
chmod +x "$PLUGINS_CACHE/commit-often/1.0.0/hooks/check-uncommitted.sh" 2>/dev/null || true
chmod +x "$PLUGINS_CACHE/review-changes/1.0.0/hooks/review-commit.sh" 2>/dev/null || true

# --- Done ---
echo ""
echo "============================================"
log_info "Plugin setup complete!"
echo "============================================"
echo ""

# Verify installation
log_info "Installed plugins:"
claude plugin list 2>/dev/null || true
echo ""
echo "Start a new Claude Code session to activate plugins."
echo ""
