# The tools: config keys, outputs, order

Every script in `scripts/` takes one argument, the job's TOML config, and reads its own section.
Relative paths resolve against the config file's directory. Each run copies the config into its
output directory as `<tool>.config.toml` and writes `<tool>.run.json` (config digest, inputs,
counts, time), so an output never travels without the parameters that made it. Output goes to
the section's `out_dir`, else `[job].out_dir`; give each tool its own `out_dir` when several
share a config. Python 3.11+ standard library only (`tomllib`), except where noted.

## Data flow

```text
[source] repo + pin --closure.py--> closure.json --+
source checkout --trace_reads.py--> traced-reads.txt -+--make_keep_set.py--> keep.tsv
keep.tsv --cut_tree.py--> cut tree, first commit
cut tree --test_triage.py--> triaged.tsv          (audit reasons)
cut tree --staged_rename.py--> moved-paths.tsv, rewritten.tsv   (audit path map, reasons)
keep.tsv + path maps + reasons --check_tree.py--> files.tsv, audit.json
any tree --scan_vocab.py--> hits.tsv
two run dirs / staged sandboxes --compare_runs.py--> compare.json
upstream PRs --replay_upstream.py--> one commit per PR, merged through the renames
```

## Shared sections

```toml
[job]
name = "..."            # free text
out_dir = "out"         # default output directory

[source]
repo = "/path/to/source/clone"   # read only: git ls-tree, git archive, git show
pin = "<full commit sha>"
tree = "src-pin"                 # optional: an extracted `git archive <pin>`; else closure.py
                                 # extracts one into its out_dir/source-tree
```

## closure.py (`[closure]`)

| Key | Meaning |
| --- | --- |
| `packages` | internal top-level packages (`["propensity_prediction"]`) |
| `source_roots` | directories holding them (`["src"]`) |
| `scripts` | globs of standalone scripts, parsed like modules (`["scripts/**/*.py"]`) |
| `shell` | globs of shell and pod task files, scanned line by line |
| `roots` | the kept entry points, as node names (see below) |
| `[closure.cli]` | `module`, `variable` (a dict literal `{group: {name: (...)}}` or `{name: (...)}`), `command` (`"pp {group} {name}"`), `target` (module template from the row's tuple, `"pkg.{0}.commands.{1}"`), `also` (modules every command loads), `shell_pattern` (regex whose groups give group and name in shell text) |
| `[closure.entrypoint]` | `root` and `triggers` `{module = [names]}`: a plugin registry that imports an entry-point module when a reached module uses a trigger name (Inspect's `eval`, `get_model`, ...) |
| `[[closure.shell_rules]]` | `pattern`, `to` (targets; `{1}` is the first group): extra edges from shell text |
| `[[closure.edges]]` | `from`, `to`, `why` (required: the code that says so): manual edges for what runs elsewhere |
| `[[closure.options]]` | `name`, `roots`: scope options, reported as added modules and lines |

Node names: `pkg.mod`, `script:<path>`, `shell:<path>`, `cmd:<command>`, or any name a manual
edge introduces (`task:e5_report`). Variants: `runtime` (imports of every kind that runs, dynamic,
shell, manual), `entrypoint` (+ the registry root when triggered), `typing` (+ `TYPE_CHECKING`).
Output `closure.json`: `variants.<v>.modules` and `.files` (by node type), `module_files`,
`why_reached` (shortest chain per module), `unreached` (by package, with lines),
`named_not_reached`, `unresolved_internal`, `third_party_runtime`, `options`, `totals`, `edges`.

## trace_reads.py (`[trace]`)

Run with the source checkout's own interpreter. Keys: `repo`, `entry` (`"pkg.cli:app"` or
`"-m pkg"`), `prog`, `env` (dummy values only), `[[trace.runs]]` with `name`, `args`, `env`.
Output: `traced-reads.txt` (`path<TAB>kind<TAB>runs`) and per-run traces and logs. Subprocesses
are not traced: add their commands as runs.

## make_keep_set.py (`[keep]`)

`[[keep.rule]]` tables, applied in order; the first rule to claim a path gives its reason.

| `type` | Keys |
| --- | --- |
| `closure` | `closure_json`, `variant` (runtime), `node_types` (["module"]; add "script", "shell"), `reason`, `extra_modules` {module = reason} |
| `package_inits` | `reason` |
| `glob` | `include`, `exclude`, `reason` (an empty match is an error) |
| `traced` | `files`, `exclude`, `reason` |
| `mentions` | `candidates` (globs), `declared_in` (files), `reason` with `{stem}` |
| `explicit` | `paths` {path = reason}, `default_reason` (an untracked path is an error) |
| `tests` | `include`, `support`, `support_reason`, `reason`, `excluded_imports` (prefixes) |

Output: `keep.tsv` (`path<TAB>reason`, sorted) and a count per reason.

## cut_tree.py (`[cut]`)

`keep`, `tree` (a new directory), `commit` (bool), `message` (`{repo}`, `{pin}`; put trailer
lines here), `branch` (main), `commit_env` (state why). Force-adds the keep set and checks the
committed file list equals it.

## test_triage.py (`[triage]`)

`tree`, `drops` (TSV `path<TAB>name<TAB>reason`; name is a function, class, `Class.method`, or
`*` for the whole file), `retargets` (TOML `[[retarget]]` `path`, `old`, `new`, `reason`, optional
`count`). Output: `triage-report.json`, `triaged.tsv` (audit reasons).

## check_tree.py (`[audit]`)

`repo`, `rev` (HEAD), `keep`, `reasons` (TSVs `path-or-glob<TAB>reason`; exact wins over glob),
`path_map` (TSVs `old<TAB>new`; a trailing `/` maps a prefix). Statuses: identical, moved,
changed, moved+changed, added. Output: `files.tsv`, `audit.json`; exit 1 on any problem.

## staged_rename.py (`[rename]` plus a map file)

`repo` (a clean scratch working copy), `map`, `frozen`, `unfrozen`, `missing` (error|skip),
`commit`, `trailer`, `commit_env`. The map file holds `[[stage]]` tables: `name`, `moves` (TSV
relative to the map, or inline pairs), `path_updates`, `extra_subs`, `delete`, `[[stage.sub]]`
with `mode` = `literal` (`old`, `new`), `regex` (`pattern`, `replace`, `flags`), `python-names`
(`names`, `parts`, `keep`, `strings`, `identifier_strings`, `comments`, `move_modules`),
`yaml-keys` (`keys`, `comments`); each sub takes `files`, `exclude`, `label`. Every stage's
rewrites are checked before any is written: Python must still parse, and every module reference
(imports, and string literals that are dotted chains such as `import_module("a.b")`) that named a
repo module before the stage must name one after it, frozen files included. A rule that renames a
module's name must move its file (`move_modules`) and its dotted strings (`identifier_strings`),
or the stage is refused. Path strings that resolved before a stage and no longer do are
reported, not refused (`dangling-paths.tsv`): prose may cite old paths, but code that builds a
path from parts needs an `extra_subs` entry. Output: `rename-report.json` (start commit, per-stage moves, per-rule
counts, rules that matched nothing, frozen-file proof, dangling-path count, commit),
`moved-paths.tsv`, `rewritten.tsv`, `dangling-paths.tsv`.

## scan_vocab.py (`[scan]`)

`repo`, `patterns` ([[name, regex]]), `files`, `exclude`, `allow` (regexes for deliberate
leftovers), `ignore_case`, `fail_on_hits`. Output: `hits.tsv`.

## compare_runs.py (`[compare]`)

`a`, `b`, `roots_a`, `roots_b`, `shas_a`, `shas_b`, `rules` (TOML files with `path_rules` and
`text_rules`), `path_rules`, `text_rules` (the job's run first), `rename_a`, `key_map`,
`uncounted`, `verify_text_digests`, `byte_identical`, `ignore`, `cap`. Reads `.eval` with
inspect_ai when the interpreter has it (run it with a checkout's own Python): recent Inspect
writes zstd, which the standard library reads only from 3.14. Output: `compare.json`; exit 1 on
any difference, including a counted rule whose A and B counts differ.

## replay_upstream.py (`[replay]`)

`repo` (scratch clone), `fetch_from`, `base`, `branch`, `exclude`, `add`, `message`, `trailer`,
`[[replay.pr]]` (`merge`, `label`, `only`), `[replay.merge]` (`into`, `from`, `find_renames`).
Exit 3 at a conflict; rerunning skips PRs already on the branch. Output: one patch per PR,
`replay-report.json`.

## How they were tested (6 Nov 2026, free, local)

| Check | Result |
| --- | --- |
| `closure.py` on the pin vs the original tool | identical module sets in all three variants (222 modules) |
| `make_keep_set.py` with `examples/training-effects/job.toml` vs the recorded `keep.tsv` | byte-identical: 723 rows, paths and reasons |
| `cut_tree.py` then `check_tree.py` | 723 files committed, 723 identical, 0 problems |
| `test_triage.py` vs the original triage on a second clone | identical trees (7 removed, 34 retargets, 137 drops) |
| `staged_rename.py`, three stages | 378 files rewritten, 416 paths moved (7 module files by `move_modules`), 286 frozen files unchanged; audit through the path map: 0 problems; a negative branch: 2 problems found; the same map without `move_modules` refused (14 imports named) |
| `compare_runs.py` on two executions of one mock config | 0 differences after declared rules; a perturbed copy: 1 found |
| `replay_upstream.py` on a toy upstream and renamed fork | the fix landed in the renamed file; rerun skipped both PRs |
| `trace_reads.py` on a toy CLI | `__file__`-relative and globbed reads recorded; the unread file not |
| Full test suite (pin's venv, `PYTHONPATH=src`, `-n 0`) on the triaged cut | 2283 passed, 11 failed, 4 skipped: the 11 need run configs the handover repo added after the cut |
| The same on the renamed tree (the partial three-stage map) | first run: 13 modules failed to collect (renamed imports, modules not moved: led to the import guard and `move_modules`); final: 2263 passed, 29 failed (the 11, plus 18 from the map renaming basenames that tests compose or assert, and 2 environment artefacts), none from a rule misapplied |

All of these rerun with one script, 20 checks in about two minutes, after any edit to a tool:
`skill-build/test/run_all_checks.sh` in the scratchpad of session 2fc8ee02 (it reads that
session's baseline closure, original tools and mock logs, so it is not shipped here).
