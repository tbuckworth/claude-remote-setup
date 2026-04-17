---
name: yulia-report-email
description: Use this skill when the user asks to "email eval results", "send eval report", "email me the results", "send results with charts", or any request to email control-arena eval scores, training curves, or comparison tables. Also trigger when sending experiment summaries or analysis via email.
version: 3.0.0
---

# Eval Email Report

Use `/ship-eval <path>` to parse eval(s), upload to Drive, and email a comparison report in one command. Pass a `.eval` file or a directory of them.

```bash
# Local evals
/ship-eval /path/to/sweep_dir
/ship-eval /path/to/single.eval

# Download from Modal and ship
/ship-eval --modal /remote/sweep/path

# Poll Modal every 30m until 11 evals land, then ship
/ship-eval --modal /remote/sweep/path --poll 30 --expect 11

# Poll until count stabilises (no --expect = wait for 2 consecutive same-count checks)
/ship-eval --modal /remote/sweep/path --poll 30
```

Flags: `--dry-run`, `--skip-drive`, `--sweep-name <name>`, `--glob '<pattern>'`, `--since <iso>`, `--modal <remote>`, `--poll <mins>`, `--expect <N>`.

Config at `~/.config/claude-eval-ship/config.json` (recipient, Drive parent folder, Gmail label).

## One-off email (no Drive upload, no parsing pipeline)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/send_report_email.py \
  --to RECIPIENT --subject "..." --html /tmp/report.html \
  --image chart:/tmp/chart.png --label Evals
```

## Prerequisites

- OAuth token at `~/.config/google-docs-mcp/token.json` with `gmail.send`, `gmail.modify`, `drive.file` scopes
- Gmail API + Drive API enabled in the Google Cloud project
- Python packages: `google-api-python-client`, `google-auth`, `matplotlib`
