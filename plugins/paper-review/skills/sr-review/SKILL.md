---
name: sr-review
description: Run a spaced-repetition session for previously reviewed papers using Titus's SM-2 paper database. Use when asked to review due papers or revisit a specific paper.
---

Read `../../commands/sr-review.md` completely and follow it as the canonical workflow.

Treat any paper slug in the user's request as `{{argument}}`, ignore Claude-only frontmatter, and ask questions conversationally where the document names `AskUserQuestion`. Codex supplies `CLAUDE_PLUGIN_ROOT` for plugin compatibility.
