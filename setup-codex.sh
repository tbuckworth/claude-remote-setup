#!/bin/bash
# Install Codex plugins from the shared Claude/Codex source repositories.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APOLLO_DIR="$HOME/pyg/admin/apollo-prep"
FOOD_CLAUDE_DIR="${FOOD_CLAUDE_SOURCE_DIR:-$HOME/pyg/food-claude}"
MAIN_PLUGINS=(paper-review branch-guard commit-often lambda-experiments refactoring-radar report-email researcher sell-stuff food-claude store-transcript wrap)
VALIDATOR_PLUGINS=(assumption-debugger best-practices-validator doc-cross-checker pre-mortem review-changes)

if ! command -v codex >/dev/null 2>&1; then
    echo "Codex CLI not found in PATH." >&2
    exit 1
fi

mkdir -p "$HOME/.codex"
ln -sfn "$SCRIPT_DIR/config/AGENTS.shared.md" "$HOME/.codex/AGENTS.md"

if [ -d "$FOOD_CLAUDE_DIR/.git" ]; then
    if [ -z "$(git -C "$FOOD_CLAUDE_DIR" status --porcelain)" ]; then
        git -C "$FOOD_CLAUDE_DIR" pull --ff-only
    else
        echo "Leaving modified Food Claude checkout unchanged: $FOOD_CLAUDE_DIR" >&2
    fi
else
    mkdir -p "$(dirname "$FOOD_CLAUDE_DIR")"
    git clone https://github.com/Antovigo/food-claude.git "$FOOD_CLAUDE_DIR"
fi

# Refresh generated Codex adapters from their canonical Claude agent and hook
# sources so the two variants cannot silently drift.
cp "$SCRIPT_DIR/plugins/assumption-debugger/agents/assumption-debugger.md" "$SCRIPT_DIR/codex-marketplace/plugins/assumption-debugger/references/agent.md"
cp "$SCRIPT_DIR/plugins/best-practices-validator/agents/best-practices-validator.md" "$SCRIPT_DIR/codex-marketplace/plugins/best-practices-validator/references/agent.md"
cp "$SCRIPT_DIR/plugins/doc-cross-checker/agents/doc-cross-checker.md" "$SCRIPT_DIR/codex-marketplace/plugins/doc-cross-checker/references/agent.md"
cp "$SCRIPT_DIR/plugins/pre-mortem/agents/pre-mortem.md" "$SCRIPT_DIR/codex-marketplace/plugins/pre-mortem/references/agent.md"
cp "$SCRIPT_DIR/plugins/review-changes/agents/review-changes.md" "$SCRIPT_DIR/codex-marketplace/plugins/review-changes/references/agent.md"
cp "$SCRIPT_DIR/plugins/review-changes/hooks/review-commit.sh" "$SCRIPT_DIR/codex-marketplace/plugins/review-changes/hooks/review-commit.sh"
chmod +x "$SCRIPT_DIR/codex-marketplace/plugins/review-changes/hooks/review-commit.sh"

codex plugin marketplace add "$SCRIPT_DIR" 2>/dev/null || true
codex plugin marketplace add "$SCRIPT_DIR/codex-marketplace" 2>/dev/null || true
codex plugin marketplace add "$APOLLO_DIR" 2>/dev/null || true

# The initial migration installed assumption-debugger from the mixed Claude
# source, which made Codex warn about its unsupported prompt hook.
codex plugin remove assumption-debugger@custom-plugins-codex 2>/dev/null || true

for plugin in "${MAIN_PLUGINS[@]}"; do
    codex plugin add "$plugin@custom-plugins-codex"
done

for plugin in "${VALIDATOR_PLUGINS[@]}"; do
    codex plugin add "$plugin@custom-validators-codex"
done

codex plugin add interview-prep@apollo-prep-codex

echo "Codex plugins installed. Review and trust plugin hooks with /hooks, then start a new thread."
codex plugin list
