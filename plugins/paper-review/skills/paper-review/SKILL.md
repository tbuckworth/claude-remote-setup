---
name: paper-review
description: Run Titus's interactive paper-review workflow for a URL, paper name, or a document on reMarkable. Use for deep paper review, annotation extraction, quizzes, and reading-list follow-up.
---

Read `../../commands/paper-review.md` completely and follow it as the canonical workflow.

Codex adaptations:

- Treat the paper name or URL in the user's request as the command document's `{{argument}}`.
- Ignore Claude-only frontmatter such as `allowed-tools` and `model`.
- Ask the user conversationally whenever the document says to use `AskUserQuestion`.
- `CLAUDE_PLUGIN_ROOT` is intentionally retained because Codex supplies it for plugin compatibility.
- Follow Codex approval and filesystem rules when the workflow requests writes, browser launches, uploads, commits, or pushes.
