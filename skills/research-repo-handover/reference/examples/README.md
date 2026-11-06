# examples

Templates to copy and the files of the one real handover so far.

| Folder or file | What it is for | Needed when |
| --- | --- | --- |
| [`job-template.toml`](job-template.toml) | A job config with every tool's section and `<...>` values to fill. | Starting a new handover. |
| [`inspect-rules.toml`](inspect-rules.toml) | Normalisation rules for comparing two executions of an Inspect run with `compare_runs.py`. | Proving two checkouts behave the same on an Inspect task. |
| [`naming-proposal.md`](naming-proposal.md) | The first naming proposal Titus approved (with changes): new tree, old -> new table with reasons, reference counts, trade-offs. | Asking Titus for names (Phase 3). |
| [`canary_test.py`](canary_test.py) | The canary test, with its repo-specific lines marked. | Adding the canary (Phase 6). |
| [`e2e-env.example.sh`](e2e-env.example.sh), [`e2e-step.sh`](e2e-step.sh) | The end-to-end run's environment (copy to `e2e-env.sh`) and per-step wrapper. | The real end-to-end run (Phase 8). |
| [`training-effects/`](training-effects/) | The Training Effects Prediction job: its config, inputs and expected keep set, and the original repo-specific scripts. | Reproducing that cut, or adapting a repo-specific step. |
