# Plugin & Hook Development Guide

## Hooks without plugins (simplest)

For hooks that just run a shell command on an event (Stop, UserPromptSubmit, etc.), skip the plugin system entirely — add them directly to `~/.claude/settings.json`:

```json
"hooks": {
  "Stop": [{ "hooks": [{ "type": "command", "command": "/path/to/script.sh" }] }]
}
```

Available events: `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreCompact`, `Notification`.

## When you DO need a plugin

Only create a plugin when you need agents, slash commands, skills, or MCP servers alongside hooks. If it's hooks-only, use `settings.json`.

## Creating a plugin (custom-plugins marketplace)

The `custom-plugins` marketplace source is **this repo**: `~/pyg/claude-remote-setup/plugins/`.

### Steps

1. Create in the **marketplace source**: `plugins/<name>/`
2. Add the required structure:
   ```
   plugins/<name>/
   ├── .claude-plugin/
   │   └── plugin.json        # {"name": "<name>", "version": "1.0.0", "description": "..."}
   ├── hooks/
   │   ├── hooks.json          # hook event → script mappings
   │   └── my-hook.sh          # executable script
   ├── agents/                 # optional
   ├── commands/               # optional
   └── skills/                 # optional
   ```
3. `git add` and `git commit` in this repo
4. Install via Claude Code: `claude plugin install <name>` from the `custom-plugins` marketplace
5. Enable in `~/.claude/settings.json` under `enabledPlugins`: `"<name>@custom-plugins": true`

### hooks.json format

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/my-hook.sh"
          }
        ]
      }
    ]
  }
}
```

Use `${CLAUDE_PLUGIN_ROOT}` to reference files relative to the plugin directory.

## Common mistakes

- **Never create files directly in `~/.claude/plugins/cache/`** — that directory is a cache populated by Claude Code from the marketplace source. Files created there get flagged as orphaned and ignored.
- **Never manually edit `~/.claude/plugins/installed_plugins.json`** — Claude Code manages this file. Manual edits get validated against the marketplace and fail.
- **Always create plugins in the marketplace source** (`~/pyg/claude-remote-setup/plugins/`), commit, then install through Claude Code's plugin system.
