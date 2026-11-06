# research-repo-handover

A Claude Code skill for cutting a clean handover copy of a research repo for an outside team,
proving it does what the source did, and porting later upstream fixes into it. Built from the
Training Effects Prediction handover (tasks#2415) for tasks#2421. `SKILL.md` is what the agent
loads; this file is for people.

| Folder or file | What it is for | Needed when |
| --- | --- | --- |
| [`SKILL.md`](SKILL.md) | The trigger description, the hard rules, the phase checklist with Titus's decision points, and the tool list. | Always: the agent reads it when the skill triggers. |
| [`scripts/`](scripts/) | The tools, one per step: closure, tracing, keep set, cut, test triage, tree audit, staged renames, vocabulary scan, run comparison, upstream replay. | Doing the steps: each takes the job's TOML config. |
| [`reference/`](reference/) | The playbook in detail, every tool's config keys, README conventions, the canary, the end-to-end checklist, the porting method. | Working a phase in detail. |
| [`reference/examples/`](reference/examples/) | A job template, Inspect comparison rules, patterns, and the Training Effects job with its repo-specific originals. | Starting a job, or reproducing the Training Effects cut. |

**Language.** Python (standard library only, 3.11+), not Rust: the tools parse the source
repo's Python with `ast` and `tokenize` and read Inspect logs, which have no Rust equivalents.

**Install.** `cp -r research-repo-handover ~/.claude/skills/` (Titus installs it after review).

**Tested** (6 Nov 2026, free, local): from propensity-prediction at the recorded pin,
`closure.py` and `make_keep_set.py` reproduce the Training Effects keep set byte for byte
(723 rows, paths and reasons); the other tools were run on scratch copies and toy repos.
`reference/tools.md` has the results table.
