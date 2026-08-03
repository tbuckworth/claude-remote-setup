---
name: store-transcript
description: Archive the current session's transcript into Titus's private deception-transcripts repo, with a log of why it was stored plus the source repo's commit hash and remote, then PR and merge. Use when asked to "store this transcript", "save this session", "archive this conversation", or /store-transcript.
---

Read `../../commands/store-transcript.md` completely and follow it as the canonical workflow.

Treat the user's stated reason as `{{argument}}`, ignore the Claude-only frontmatter, and
ask conversationally where the document says to ask.

Codex specifics:

- `CLAUDE_PLUGIN_ROOT` is supplied for plugin compatibility; if it is unset, use the
  plugin directory containing this skill (`../../scripts/store_transcript.py`).
- Pass `--agent codex` so the script looks in `~/.codex/sessions/` rather than
  `~/.claude/projects/`. It identifies the live session as the most recently written
  rollout file whose recorded `cwd` matches the current working directory, so run it from
  the directory the session started in.
