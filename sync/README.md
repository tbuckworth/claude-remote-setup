# Instructions sync

The global agent instructions are `config/AGENTS.shared.md` and `config/AGENTS.email.md`. Claude reads
them straight from `~/pyg/claude-remote-setup` (`~/.claude/CLAUDE.md` imports them); Codex reads
`~/.codex/AGENTS.md`, which is the two files joined.

**main on GitHub is the only source.** To change the instructions, edit them on a branch, open a pull
request and merge it. Never edit the checkout on either machine in place. Within the hour each machine
pulls main and rebuilds its `~/.codex/AGENTS.md`. Nothing is copied from one machine to the other.

`sync_instructions.py` does one run:

1. Fetch `origin/main` and fast-forward the checkout. It leaves the checkout as it is, and reports why,
   if the checkout is on another branch, has uncommitted edits to tracked files, or has commits GitHub
   lacks.
2. Rebuild `~/.codex/AGENTS.md` from the checkout, so Codex matches Claude on that machine. A block that
   another installer appended between `<!-- name -->` and `<!-- /name -->` lines (such as the Arrow Board
   one) is kept. The file is replaced, never written through, because a symlink there once truncated
   `AGENTS.shared.md`.

Problems are written to `~/.local/state/sync-instructions/status.json`. The desktop emails Titus from the
agents account once per new problem, its own or the Mac's; it reads the Mac's status over ssh. GitHub
being unreachable counts only after a day. The Mac also shows a notification.

| | Runs | Log |
|---|---|---|
| Desktop | systemd user timer `sync-instructions.timer`, hourly | `journalctl --user -u sync-instructions` |
| Mac | launchd agent `com.titus.sync-instructions`, hourly | `~/Library/Logs/sync-instructions.log` |

Install or reinstall on either machine with `bash sync/install.sh`. On the Mac this also retires
`~/.claude/sync-config.sh`, the old push from the Mac. That script copied the Mac's instructions over the
desktop's, which deleted edits made on the desktop. It also overwrote the desktop's `settings.json` and
removed its hooks. Settings, hooks and credentials are no longer copied between the machines.

Other commands:

```bash
python3 sync/sync_instructions.py --status   # this machine's last run
python3 sync/sync_instructions.py --codex    # rebuild ~/.codex/AGENTS.md only
python3 -m unittest sync/test_sync_instructions.py
```
