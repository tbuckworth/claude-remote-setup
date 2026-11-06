# training-effects

The Training Effects Prediction handover (propensity-prediction `c9881f02` to
Arrow-Research/training-effects-prediction, 3-6 Nov 2026): the job config for this skill's tools,
and the original scripts that stay specific to that repo. The originals are reference
implementations: they name its package, CLI table, task-set layout and the session's scratch
paths, and are kept as they ran, not generalised.

## The job, for this skill's tools

| File | What it is for | Needed when |
| --- | --- | --- |
| [`job.toml`](job.toml) | The cut as a job config: closure roots, CLI table, manual edges, keep rules, cut, triage, audit, rename sections. Its header says how to reproduce the keep set. | Reproducing the cut, or as a worked example of every section. |
| [`traced-reads.txt`](traced-reads.txt) | The files the source's preflights and mock runs opened (recorded 3 Nov 2026 with the original tracer). | Reproducing the keep set without re-tracing. |
| [`keep.expected.tsv`](keep.expected.tsv) | The recorded keep set: 723 paths with reasons. | Checking a reproduction: it must be byte-identical. |
| [`triage-drops.tsv`](triage-drops.tsv), [`triage-retargets.toml`](triage-retargets.toml) | The original test triage in `test_triage.py`'s formats: 7 file removals and 137 drops; 34 retargets. | An example of each triage form. |
| [`rename-map.toml`](rename-map.toml), [`rename-moves.tsv`](rename-moves.tsv) | A three-stage map in the shape of stages 1-3 (part of the real renames), as tested with `staged_rename.py`. | An example map file. |

## The originals, repo-specific

| File | What it is for | Needed when |
| --- | --- | --- |
| [`trim_cli.py`](trim_cli.py) | Deletes rows of the `_COMMANDS` table whose command module was cut. | A CLI with a literal command table. |
| [`stage1_moves.py`](stage1_moves.py) ... [`stage4_names.py`](stage4_names.py), [`stage3_cli.py`](stage3_cli.py) | The real rename stages: moves, package/CLI, CLI groups, vocabulary (with special cases such as `ceiling` only as a config field), env vars and cloud names (keeping names the agent sees). | Seeing what a full vocabulary stage needed beyond the map file. |
| [`key-map.tsv`](key-map.tsv) | Old -> new store, score and mock model keys. | Comparing logs across the rename (`compare_runs.py` `key_map`, `rename_a`). |
| [`e4_capture.py`](e4_capture.py), [`e4_run_new.sh`](e4_run_new.sh) | Stage every task set's sandboxes in one checkout and list each file's digest. | Building the staged-sandbox identity check for another harness. |
| [`mock_check.sh`](mock_check.sh), [`compare_mock.py`](compare_mock.py) | Run the three scripted episodes and compare model calls, conversations and scores, rename-aware. | A minimal equivalence check across a rename. |
| [`compare_runs_with_digest_proof.py`](compare_runs_with_digest_proof.py) | The original run comparison, with a proof that a hypotheses artifact's digest differs only by the harness SHA. | A derived value that must be proved, not normalised away. |
| [`equivalence.sh`](equivalence.sh) | The old-vs-new checks shipped in the handover repo (`tools/audit/`). | Shipping the checks with the repo. |
| [`sync_upstream.sh`](sync_upstream.sh) | Upstream sync while the layout was unchanged (porting method B). | Porting before any rename. |
| [`apply_up.sh`](apply_up.sh), [`resolve_conflicts.py`](resolve_conflicts.py) | The v1.1 PR replay that `replay_upstream.py` generalises, and a conflict-block resolver (ours/theirs/both per block). | Resolving many conflict blocks by recorded choice. |
| [`frozen_hidden_scan.py`](frozen_hidden_scan.py) | Old vocabulary in comments and docstrings inside frozen files, which nobody downstream reads. | Judging whether frozen files' comments are worth a versioned change. |
