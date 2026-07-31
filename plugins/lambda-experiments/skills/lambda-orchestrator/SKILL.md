---
name: lambda-orchestrator
description: Orchestrate a Lambda Cloud GPU experiment from a natural-language request. Use for launching, configuring, monitoring, collecting, emailing, or safely terminating Control Arena experiment runs.
---

Read `../../commands/lambda.md` completely and follow it as the canonical workflow.

Treat the user's request as the command document's argument. Ignore Claude-only frontmatter and translate `AskUserQuestion` into normal conversation. Map Claude tasks or cron operations to Codex subagents, scheduled work, or direct execution only when those capabilities are available and authorized. Codex supplies `CLAUDE_PLUGIN_ROOT` for compatibility.
