---
description: "Parse eval(s), upload to Drive, email comparison report. Pass a path, or --modal <remote> to download from Modal first. Add --poll 30 --expect N to wait for a sweep to finish."
argument-hint: "<path-or-flags>"
---
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ship_eval.py "$ARGUMENTS"`
