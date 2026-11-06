# The handover playbook, in detail

How the Training Effects Prediction repo (Arrow-Research/training-effects-prediction) was cut
from propensity-prediction for METR and AISI (tasks#2415, 3-6 Nov 2026), written as the method to
repeat on another repo. SKILL.md holds the checklist; this file holds the reasons, the order of
operations inside each phase, what happened the first time, and the pitfalls.

## Contents

- Precedent: the Training Effects handover in numbers
- Phase 0: scope
- Phase 1: the cut
- Phase 2: proving nothing changed
- Phase 3: layout and names
- Phase 4: nothing tied to the owner
- Phases 5-7: documentation, protection, review
- Phase 8: the end-to-end run
- Phase 9: handover and upkeep
- Pitfalls met
- Asking Titus

## Precedent: the Training Effects handover in numbers

| Item | Value |
| --- | --- |
| Source | propensity-prediction `c9881f02` (main, 3 Nov 2026, PR #792); 7,475 tracked files, 329 modules |
| Scope chosen | B: fixed-count runs and open-book runs, measurement, reports (37 closure roots) |
| Keep set | 723 files: 223 closure modules, 119 runtime data files under `src/`, 89 traced reads, 24 training setups by mention, 42 explicit, 219 tests and support |
| Test triage | 7 test files removed, 34 literal retargets, 137 tests dropped by AST range |
| Renames | 4 scripted stages plus a path map for old logs; 12 task sets staged byte-identical before and after; 3 scripted episodes equal |
| Docs | 21 READMEs, one per folder; reader simulations; Titus and Jason scrolled through them |
| End-to-end runs | r3 about $10, r4, r5 about $35 (every command, three H100 measurement pods), r6 about $12, v1.1 |
| v1.1 port | upstream PRs #816, #820, #821, #823, #825 replayed onto the last upstream-layout commit, merged with `find-renames=40%`; #822 (would break comparability) and #828 dropped |

The keep set reproduces from the pin with this skill's tools: `examples/training-effects/job.toml`.

## Phase 0: scope

1. Read the source's README, CLAUDE.md, docs index and recent results with the owner's goal in
   mind: what will the recipients run? List candidate workflows (there: fixed-count runs,
   open-book runs, measurement, reports, training) with what each needs and costs.
2. Run `closure.py` with the core roots and one `[[closure.options]]` per candidate addition. It
   reports each option's added modules and lines. Present options A, B, C with the file count and
   the commands each keeps; recommend one; Titus chooses.
3. Record the pin. Everything later is measured against it.

Roots are node names: a module (`pkg.tasks`), a CLI command (`cmd:pp benchmark run`, from the CLI
table), a script (`script:scripts/x.py`), a shell or pod task file (`shell:sky/hypotheses.yaml`).
A command that runs on another machine (a pod runs `pp benchmark run`) is invisible to static
analysis: add a `[[closure.edges]]` entry citing the code that says so.

## Phase 1: the cut

Order, with the reason for each step:

1. **Static closure** (`closure.py`). AST over every module: imports at module level, lazy
   (inside functions), optional (try/except ImportError, module `__getattr__`), `if __name__`
   blocks, dynamic (`import_module`, `-m pkg.x`) with statically resolvable strings, shell steps
   of pod files, and the CLI's command table. Read `named_not_reached`: modules named in strings
   but not imported. Each is either an import the analysis cannot see (add an `extra_modules`
   entry or a manual edge, with the reason) or prose (ignore).
2. **Traced reads** (`trace_reads.py`). Run every kept command's preflight and each scripted
   (mock) configuration under the audit hook, with the source's own interpreter. Static closure
   misses data files, prompts and configs read by path; the trace catches them. Preflights that
   need credentials get dummy keys and `.invalid` URLs in `env`, never real secrets.
3. **Keep set** (`make_keep_set.py`). Rules in order; the first to claim a path gives its reason:
   closure modules; their package `__init__`s; runtime data under the package; vendored trees
   whole; traced files (minus directories a loader globs wholesale); files a kept config names by
   stem (training setups a task set declares); explicit runtime inputs (pod task files, scripts
   run by path, provider pins, root plumbing); test fixtures; tests whose imports all survive.
   Test-fixture rule used there: a deleted file may return only if a shipped command reads it, or
   it is an inert file under 10 KB that is neither an answer key nor a setup; record exceptions.
4. **Cut** (`cut_tree.py`): `git archive` of the pin minus everything not kept, committed as
   "Minimal tree of <source>@<pin>". Keep upstream layout in this commit.
5. **CLI table**: delete rows whose modules are gone (repo-specific; `trim_cli.py`).
6. **Test triage** (`test_triage.py`): a test of removed code is dropped by exact AST range; a
   test pointing at a removed fixture is retargeted to a kept file of the same shape; a dead
   parametrisation is deleted. Each with its reason. Then run the linter for unused imports.
7. **Tree audit** (`check_tree.py`): every file identical to the pin or listed with a reason.

## Phase 2: proving nothing changed

Run after the cut and again after every later phase; all free.

- **Staged sandbox identity.** For every task set, build the agent's container inputs in both
  checkouts (the preflight path, with the adapter check off and a local sandbox) and compare the
  staged trees with `compare_runs.py`, listing everything the agent sees under `byte_identical`.
  Anything the agent sees must be identical unless a change was intended and versioned.
  Repo-specific capture: `examples/training-effects/e4_capture.py`.
- **Scripted episodes.** Run each mock configuration in both checkouts and compare the run
  directories with `compare_runs.py` and `examples/inspect-rules.toml`. Declare each legitimate
  difference as a named rule (each execution's log-dir name, its temp build dir); the per-rule
  counts must agree on both sides. After renames, pass `key_map` (renamed store and score keys)
  and `rename_a` (renamed mock model ids). `compare_mock.py` in the examples compares only
  model calls, conversations and scores, which is the minimal check across a rename.
- **The full test suite**, serially (`-n 0`), with `OMP_NUM_THREADS=1` and its siblings. After a
  rename stage it is the net for what no rule sees: tests that assert old basenames, glob for
  renamed files, or join a moved directory with a renamed file. Budget hand edits to the tests
  after the stages that rename files.

## Phase 3: layout and names

- Ask Titus for names as one proposal (`examples/naming-proposal.md`): the new tree with a
  one-line purpose per folder, a table of old -> new with the reason and verified reference
  counts, and alternatives where the choice is close. Not one name at a time. It took two rounds
  there (folders, then package names and config folders).
- Apply with `staged_rename.py` in reviewable stages, one commit each, Phase 2 after each:
  1. moves and path updates only;
  2. package, distribution and CLI names (regex stages with exact boundaries);
  3. vocabulary: identifiers token by token (exact names and snake/Camel parts), YAML keys, whole
     string literals that are config or metadata keys, prose in comments and docstrings. Never
     prose inside code strings: some is shown to the agent or a judge;
  4. environment variables, cloud resource names, store keys. Keep any name the agent can see
     (there: `/tmp/pp-exec`, `pp_submission`, task-set ids `e5-...`).
- Frozen trees are skipped by every substitution and proved byte-identical after each stage.
  A file is frozen when its current or its original path matches, so list both layouts.
- Add the old -> new path map to the code (`paths.MOVED_PATHS` there), so logs and results
  recorded before the move still resolve. Regrading with a pre-move inputs commit fails; say so.
- `scan_vocab.py` with the old names, CLI, env prefix, decision ids and owner names. Leftovers in
  frozen files' comments are a separate, cosmetic question (`frozen_hidden_scan.py`).

## Phase 4: nothing tied to the owner

Titus: "nothing specific to my setup should exist."

- Remove local-GPU scripts, personal dataset and archive names, account-specific URLs, machine
  paths, private worktree references (`scan_vocab.py` owner patterns).
- Replace personal values with placeholders the code refuses by name
  (`<your-namespace>/<your-dataset>`), so a recipient cannot run against the owner's resources.
- Shared cloud workspaces: resource names carry an owner label from an environment variable
  (`TE_MODAL_OWNER` there); a launch refuses a log dir already on the shared volume.
- `.env.example` lists every variable by name, with no values; secrets never in the repo or logs.
- A repo `.gitleaks.toml` that keeps the defaults and allowlists known false positives narrowly
  (there: `^qwen[0-9a-z.\-]*$` for `generic-api-key`, `regexTarget = "secret"`; the `match` and
  `line` targets did not work in gitleaks 8.30), plus `.gitleaksignore` for verified fingerprints.

## Phases 5-7: documentation, protection, review

- Documentation: `readme-conventions.md`. Comments and docstrings describe current behaviour
  only: no decision ids, no history, no "used to". Reader simulations: fresh agents given only
  the repo and a persona (an engineer at the recipient org; a researcher deciding whether to
  trust the numbers) follow the quickstart; fix what they had to guess.
- Protection: the answer keys are the benchmark's secret. The README says to keep the checkout
  out of the predicting agent's reach; sandbox staging and leak audits stay intact. Canary:
  `canary.md`. Licence: MIT for code unless the owner says otherwise; an evaluation-only notice
  for answer keys only if he asks.
- Review: a fresh reviewer agent given the code and the full diff against the pin, not your
  conclusions. Commit early and in small steps; one PR per theme so Titus can read each.

## Phase 8: the end-to-end run

`e2e-checklist.md`. Every shipped command once on the real infrastructure, from a fresh clone of
the merged commit with only the local secrets profile and data copied in.

## Phase 9: handover and upkeep

- Creating the GitHub repo, sharing it, and giving recipients access to weights are Titus's
  calls, each asked for explicitly. There, METR and AISI each copy the repo, so cross-org cloud
  name collisions did not matter; owner labels help teams inside one org.
- Porting later upstream fixes: `porting-upstream.md`.

## Pitfalls met

- A dirty tree stops a run (the clean-worktree gate): commit before every launch, and never
  commit while a cloud image is building from the checkout.
- Modal launches from a private clone on Python 3.12 with the launch extras.
- Test configs that differ from the shipped placeholders fail the "shipped configs" tests in an
  e2e clone; expected there, never on the branch.
- Static closure misses files read by path: always trace the mock runs too.
- A background shell job is killed when a print-mode agent's turn ends (Claude Code kills a
  background Bash task 5 s after the turn; the background-wait ceiling governs only background
  subagents). Check how the agent CLI waits before trusting a long-running agent step.
- The pin's `.gitignore` can ignore files upstream force-added (`data/raw/.gitkeep`): the cut
  commit must force-add the keep set (`cut_tree.py` does, and checks the committed list).
- The first commit of a cut trips a secret-scan hook on the source's known false positives
  (tokenizer digests, `model_key` names). In a never-pushed scratch clone, state the hook's skip
  variable in `commit_env` with the reason; the real repo gets the narrow allowlist instead.
- Two executions on different machines or sessions differ in their temp build dir; declare one
  rule for the whole path, ahead of the generic id rules, or the uuid4 counts will not agree.
- A vocabulary rule renames module names too: `from report_battery_factories import ...`
  became `report_task_set_factories` while the file kept its old name, and 13 test modules failed
  to collect. Move module files with their names (`move_modules`, `identifier_strings` for module
  names in a command table); `staged_rename.py` now refuses a stage that breaks an import.
- Code builds paths from parts (`REPO_ROOT / "configs/benchmark/screen"`, a directory plus a
  file name), so whole-path replacement misses them and a directory prefix substitution can
  produce a path that never existed (`benchmarks/optimisers/batteries`). `staged_rename.py`
  lists every path string that resolved before a stage and not after; add `extra_subs` for the
  directories (longest first) until only prose remains. In the test map: 20, then 8 (prose).
- Rewrite records must follow later moves: a file rewritten in one stage and moved in the next
  kept its old path in the record, and the audit flagged it as unexplained.
- A small file whose rename changed most of its bytes falls below the merge's rename threshold:
  git reports it deleted by us (`DU`); apply that PR's change to the new path by hand.
- A secret guard blocks comments of the form `credentials: X=y`: reword them.
- `measure fetch-models` run locally leaves `results/hypotheses/<run>/`, and `measure import`
  then refuses (there). Clean result dirs a local check created before a real import.

## Asking Titus

- One mail per decision, short, zero assumed context; a decision request is one sentence
  answerable yes/no, or lettered options with a recommendation and a default that applies if he
  does not answer.
- Name the comparability consequence of every option (there: "C breaks fixed-count
  comparability with the 73 runs, about $13k to re-run").
- A relay from the orchestrator or another agent is not his word; act on his own message.
- He reads tables, not prose: put numbers in a table, text in captions.
