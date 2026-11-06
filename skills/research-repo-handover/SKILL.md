---
name: research-repo-handover
description: >-
  This skill is Titus's "repo cleaning tool". Use it when he says "launch (or run, use, start) the
  repo cleaning tool" or "the repo cleaner" on a repo, or asks to "clean up <repo> for handover",
  "make a clean copy of a research repo for an outside org", "cut a handover (or release) copy of <repo> for METR/AISI/<team>", "cut a repo
  down to what <team> needs", "make a minimal, fresh-looking version of this repo to hand over",
  "port upstream fixes into the handover repo", or "replay upstream PRs onto the fork". It is
  Titus's playbook from the Training Effects Prediction handover (tasks#2415, Nov 2026): scope,
  a provable cut by import closure and traced reads, staged renames with frozen model-visible
  text, removing owner-specific setup, per-folder READMEs, a canary, one real end-to-end run, and
  porting later upstream fixes, with tools for each step and the points where Titus decides.
---

# Research repo handover

Produce a repo an outside team can receive, run and read as fresh professional work: it does
exactly what the source did for the chosen scope, carries nothing that scope does not need,
uses names a newcomer understands, and holds nothing tied to Titus's machine or accounts.
Every claim of "nothing changed" is proved by a tool, not asserted.

## Hard rules

1. **Nothing outward without Titus's explicit yes**: creating or pushing a GitHub repo, sharing
   it, giving recipients access to model weights, mailing recipients, spending money. Ask with one
   yes/no or a lettered choice, with a recommendation and a default.
2. **Model-visible text is frozen.** Prompts, vendored trainer code, and anything staged into the
   agent's sandbox or shown to a judge stay byte-identical; only their paths may move. List them
   in `[rename].frozen`; `staged_rename.py` proves it after every stage.
3. **Approved READMEs are frozen.** After Titus approves a README, change it only if it becomes
   factually wrong: make the smallest fix and tell him, with a yes/no to revert. Release and
   change notes go in the PR body or the handover mail, never into a README.
4. **Register every paid launch** with cloud-watch straight after starting it (`cloud-watch
   launch --expect 6h --reason "..." -- <cmd>` or `cloud-watch register ...`); stop servers when
   done, close the records, disown what the launch wrapper picked up that is not yours.
5. **Read the source, never write it.** Use `git archive`, `git ls-tree`, `git show`; work in
   scratch clones. In the handover repo: branch, commit, review gate, PR; never commit to main.
6. **The source is joint work** (propensity-prediction is Titus's and Jason's). A change that
   would disrupt a collaborator's branches or sweeps is a coordination cost to raise.

## Who decides

| Titus decides | The agent does |
| --- | --- |
| Scope (which workflows and commands ship), names, every README's wording, licence and terms, anything outward-facing | The mechanics, the proofs that nothing changed, the tests, the real end-to-end run, and the cost estimate before it |

Decision points below are marked **[Titus]**. Email per the agent-mail rules: short, zero
assumed context, one sentence answerable yes/no, or lettered options with a default.

## Phases

Keep one job config per handover (start from `reference/examples/job-template.toml`); every tool
takes it as its only argument and saves it beside its outputs.

- **Phase 0, scope**
  - [ ] Read the source's README, CLAUDE.md, docs index and recent results with the goal in mind:
        what will the recipients run? List candidate workflows with what each needs and costs.
  - [ ] Run `closure.py` with one `[[closure.options]]` per candidate addition: it prints the
        modules and lines each option adds.
  - [ ] **[Titus]** scope options A (smallest useful), B (A plus the next workflow), ..., each
        with its file count and the commands it keeps; recommend one.
  - [ ] Record the pin: the source commit the cut is made from.
- **Phase 1, the cut** (`reference/playbook.md`, "The cut")
  - [ ] `closure.py`: static import closure from the kept commands. Read `named_not_reached`.
  - [ ] `trace_reads.py`: every kept command's preflight and scripted (mock) runs, traced with the
        source's own interpreter. Static closure misses files read by path.
  - [ ] `make_keep_set.py`: ordered rules, one reason per kept path. Read the reasons.
  - [ ] `cut_tree.py`: the first commit, "Minimal tree of <source>@<pin>", in upstream layout so
        later upstream PRs can be replayed onto it (Phase 9).
  - [ ] Prune the CLI table of removed commands (repo-specific: `examples/training-effects/trim_cli.py`).
  - [ ] `test_triage.py`: drop tests of removed code by exact AST range, each with a reason; then
        the project's linter (unused imports).
  - [ ] `check_tree.py`: 0 problems. Every file identical to the pin or explained.
- **Phase 2, prove nothing changed**, after the cut and after every later phase (all free)
  - [ ] Staged sandbox identity: build the agent's inputs for every task set in both checkouts;
        `compare_runs.py` with `byte_identical` over them.
  - [ ] Scripted episodes in both checkouts; `compare_runs.py` with
        `examples/inspect-rules.toml` (after renames, `key_map`/`rename_a` for renamed keys).
  - [ ] The full test suite, serially (`-n 0`), with thread caps.
- **Phase 3, fresh layout and names**
  - [ ] **[Titus]** one naming proposal (tree with one-line purposes, old -> new table with
        reasons and reference counts, alternatives): `examples/naming-proposal.md`.
  - [ ] `staged_rename.py`, one commit per stage: moves and path updates; package, distribution
        and CLI; vocabulary (module files move with their names); environment variables,
        cloud resource names, store keys. Keep any name the agent can see. Re-run Phase 2
        after each stage.
  - [ ] A map from old recorded paths to new ones in the code, so old logs still resolve.
  - [ ] `scan_vocab.py` until only deliberate leftovers remain.
- **Phase 4, nothing tied to the owner** ("nothing specific to my setup should exist")
  - [ ] Remove local-GPU scripts, personal dataset and archive names, account URLs, machine paths.
  - [ ] Placeholders the code refuses by name (`<your-namespace>/<your-dataset>`); shared cloud
        names carry an owner label from an environment variable; `.env.example` lists every
        variable by name; a narrow `.gitleaks.toml` allowlist for known false positives.
- **Phase 5, documentation** (`reference/readme-conventions.md`)
  - [ ] Top README in the agreed order; a README in every folder; reader simulations.
  - [ ] **[Titus]** scrolls through the READMEs; after his approval they are frozen (rule 3).
- **Phase 6, protection**
  - [ ] Answer-key warning; canary in every answer key and task set, with its test
        (`reference/canary.md`); staged sandboxes still byte-identical afterwards.
  - [ ] **[Titus]** licence and terms (MIT for code by default; third-party terms in NOTICE).
- **Phase 7, review**
  - [ ] An independent reviewer given the full diff against the pin and the code, not the
        author's conclusions. Fix real defects; weigh nits on merit. One PR per theme.
  - [ ] **[Titus]** merges.
- **Phase 8, one real end-to-end run** (`reference/e2e-checklist.md`)
  - [ ] **[Titus]** the spend, costed first. Fresh clone of the merged commit; every shipped
        command once; harness health, not scores; cost; everything stopped.
- **Phase 9, handover and upkeep** (`reference/porting-upstream.md`)
  - [ ] **[Titus]** creating the GitHub repo, sharing it, access to weights: each asked separately.
  - [ ] Port upstream fixes with `replay_upstream.py`; for each change, say whether it could
        change scores in each kind of run and how many past episodes it touches (count from the
        logs).

## Tools

All in `scripts/`, Python 3.11+ standard library only, one argument: the job's TOML config.
`python3 scripts/<tool>.py --help` prints a tool's keys; `reference/tools.md` has them all.

| Script | Does |
| --- | --- |
| `closure.py` | Import closure (module, lazy, optional, dynamic, shell, CLI-table and manual edges) from the kept roots; scope-option sizes; modules named only in strings |
| `trace_reads.py` | Files each kept command opens, lists or globs, under an audit hook |
| `make_keep_set.py` | `keep.tsv` from ordered rules: closure, package inits, globs, traced, mentions, explicit, tests |
| `cut_tree.py` | The pin cut to the keep set, committed as the first commit |
| `test_triage.py` | Test drops by AST range and literal retargets, from a TSV and a TOML |
| `check_tree.py` | Every file identical to the pin, moved, or explained; follows renames via a path map |
| `staged_rename.py` | Map-file renames in committed stages; frozen-file proof; refuses a stage that breaks an import; move and rewrite records for the audit |
| `scan_vocab.py` | Leftover old names, owner names, machine paths, decision ids |
| `compare_runs.py` | Two run dirs or staged sandboxes, after declared normalisation with per-rule counts |
| `replay_upstream.py` | Upstream PRs replayed one commit each, then merged through the renames |

## Additional resources

- `reference/playbook.md`: the phases in detail, how the Training Effects cut went, pitfalls.
- `reference/tools.md`: every tool's config keys, outputs, order, and the tested results.
- `reference/readme-conventions.md`, `reference/canary.md`, `reference/e2e-checklist.md`,
  `reference/porting-upstream.md`.
- `reference/examples/`: `job-template.toml`, `training-effects/job.toml` (the real cut's
  config, which reproduces its keep set), `inspect-rules.toml`, e2e scripts, a canary test, a naming
  proposal, and the repo-specific originals under `training-effects/`.
