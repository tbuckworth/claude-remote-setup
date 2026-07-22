---
name: web2pdf
description: Convert a web article into a clean PDF and optionally send it to Titus's reMarkable. Use when asked to save, print, or send an HTML article to reMarkable.
---

Read `../../commands/web2pdf.md` completely and follow it as the canonical workflow.

Treat the URL and options in the user's request as `{{argument}}`, ignore Claude-only frontmatter, and ask conversationally where the document names `AskUserQuestion`. Codex supplies `CLAUDE_PLUGIN_ROOT` for plugin compatibility.
