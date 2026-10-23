# Global Instructions

## Style

- Use concise, direct language. Do not waffle or repeat information.
- The user is an academic who values truth above blame. If you make a mistake, declare it immediately and matter-of-factly.
- Avoid sycophancy and defensive language.

## Desktop (SSH)

- SSH host alias: `desktop` (user `titus`, address `100.116.219.34`).
- Large 3 TB volume: `/media/titus/big` (device `/dev/sdb`, UUID `d88cd800-acde-46cc-b9e8-2be359f95347`).
  Its root is root-owned — write under an existing subdir (`tmp/`, `eval_archive/`, `bma_*`,
  `py-offload/`); a new top-level dir needs `sudo mkdir` + `sudo chown titus:titus`.
  Never use the bare `/media/titus/<UUID>` path: it is NOT a mountpoint, so writes there land
  on the 46 G root filesystem instead of the 3 TB disk.
- “Send/share to desktop” means `scp <file> desktop:/media/titus/big/tmp/`.
- “Run on desktop” means `ssh desktop '<command>'`.
- The desktop is Ubuntu with an NVIDIA RTX 3090; repositories live in `~/pyg`.
- Phone app installs over adb, only when Titus asks: `~/pyg/admin/wiki/systems/phone-adb.md`.
- Global agent instructions are `config/AGENTS.shared.md` and `config/AGENTS.email.md` in
  `~/pyg/claude-remote-setup`. Change them on a branch and merge to main on GitHub; never edit
  the checkout on either machine in place. Each machine pulls main every hour and rebuilds
  `~/.codex/AGENTS.md` (see `sync/README.md`). `~/.claude/sync-config.sh` is retired: do not run it.

## MATS cluster (Slurm GPUs)

- “Get a GPU on the MATS cluster”, “run this on MATS”, “submit to the cluster” all mean:
  submit a **Slurm job** from the dev node — never run the work in an SSH shell.
- SSH aliases (configured in `~/.ssh/config`): `mats` = dev/login node
  (`t.buckworth@185.141.218.207`), `mats-controller` (alias `mats-ctl`) = controller
  (`94.156.8.208`). Key-only auth with `~/.ssh/id_ed25519`.
- Use the `mats-cluster` skill (installed at `~/.claude/skills/mats-cluster`, and on the
  cluster itself) for partitions, prices, sbatch templates, and troubleshooting.
- Free partition `compute` (8× shared L40, 48 GB) — always start here. `elastic-*`
  partitions (A100/H100) are pay-as-you-go, **not yet enabled for this account**, and
  require explicit confirmation before any submission.
- Storage: `/mnt/nw/home/t.buckworth` (persistent, NFS, checkpoints/results),
  `/mnt/nw/teams/team_rhys_c9` (team share), `/ephemeral/t.buckworth` (fast scratch,
  wiped on reboot — HF cache and dataset shards go here). Nothing is backed up.
- **Nothing bulky goes in `/tmp` on the cluster.** `/tmp` is the node's root disk;
  filling it drains the worker and stalls everyone's queue (this happened
  2026-08-18, from agent scratch under `/tmp/opencode`). Export
  `TMPDIR=/ephemeral/$USER/tmp` (and `XDG_CACHE_HOME`) in every job script and
  before launching any agent on the cluster. Details: `mats-cluster` skill.
- `gpu-avail` / `gpu-cost` exist **only on the controller** (`ssh mats-controller`).
- Long-running terminal work (agents, downloads) belongs in `tmux` on the dev node.
- Autonomous research runs: use `RESEARCHER_COMPUTE_PROFILE=mats` (see
  `~/pyg/researcher/docs/COMPUTE-MATS.md`).

## Google Workspace

- Google Cloud project: `house-splitting` (project number `932775262283`).
- Credentials file: `~/pyg/house-splitting/credentials.json`.
- Re-authentication: `python ~/pyg/admin/google_reauth.py` (update its `SCOPES` first when adding scopes).
- Google Docs/Drive CLI: `python ~/.claude/tools/gdoc.py <command>`.
- OAuth token: `~/.config/google-docs-mcp/token.json`.
- `gdoc.py` commands: `read`, `copy`, `create`, `replace`, `batch-replace`, `share`, and `list`.
- MATS Ward 9 Shared Drive folder ID: `1dllRznKsAesxmA59RzBQxZCKEhePCOPE`.

### Google Drive deletion safety

- Never delete Drive files without explicit confirmation for the exact files.
- Before deletion, list and verify names, sizes, and count. Treat `name contains` queries as potentially over-broad.
- Shared Drive deletions are permanent. Never delete a parent folder when only selected children are intended.
- Prefer trash over permanent deletion when possible; confirm before emptying trash.

## Plugins and hooks

- Canonical custom-plugin source: `~/pyg/claude-remote-setup/plugins/`.
- Never edit installed plugin caches directly. Edit source, validate it, then reinstall or refresh it.
- Preserve shared payloads across Claude and Codex. Put platform manifests and small adapters beside shared skills, scripts, references, and hooks.
- For Claude-specific plugin work, read `~/pyg/claude-remote-setup/docs/plugin-development.md`.
- For Codex-specific plugin work, use the built-in `plugin-creator` guidance and validate `.codex-plugin/plugin.json` before installation.

## Web-to-PDF (reMarkable)

- Run `python ~/pyg/paper-review/tools/web2pdf.py <URL> [OPTIONS]` for HTML articles.
- Useful options: `-o PATH`, `--rm`, `--rm-folder FOLDER`, `--no-images`, and `--font-size SIZE` (default 14 pt).
- For arXiv papers, download the PDF directly from `https://arxiv.org/pdf/<id>`.

## Fine-tuning and LoRA

- Before fine-tuning a model, read the current guidance at `https://thinkingmachines.ai/blog/lora/` and use it to choose hyperparameters.

## To-do list (GitHub Issues)

- “Add to my to-do/task” means create a GitHub issue in `tbuckworth/tasks` with `gh issue create`.
- Always include `list:tasks` and a source label matching the active agent (`source:claude` or `source:codex`). Do not add `section:*` labels.
- Route clear cases to `list:research-ideas`, `list:look-into`, or `list:groceries` instead of `list:tasks`.
- Add one relevant action label when applicable: `action:buy`, `action:email`, `action:look-into`, `action:call`, or `action:manual`.
- Add `priority:high`, `priority:medium`, or `priority:low` only when relevant.
- Multiple tasks become separate issues. Put sub-items under a `## Checklist` section.
- Do not create new list labels without asking. Confirm each created issue with its title and labels.

## Secrets

**Never write a credential value into a file, a command, a commit, a log, or a chat message.**
This is enforced, not advisory: a `PreToolUse` hook (`~/.claude/hooks/secret-guard.py`) blocks
Bash/Write/Edit calls containing token-shaped strings, `permissions.deny` blocks reading `.env` and
credential files, and a global gitleaks pre-commit hook blocks commits on both machines.

All API keys live in **Bitwarden Secrets Manager**, project `agents`.

- **Run something that needs secrets** — this is the normal path:
  ```bash
  bws run --project-id "$(cat ~/.config/bws/project-id)" -- python train.py
  ```
  Every secret in the project arrives as an environment variable named by its key
  (`OPENAI_API_KEY`, `HF_TOKEN`, …). `bws run` has **no** `--env-file` option — it injects the whole
  project, so there is no such thing as a `bws://` reference inside a `.env` file. Do not invent one.
- **In code**, always `os.environ["HF_TOKEN"]` — never a literal, never a default value that is a key.
- **One specific secret**: `bws secret get <uuid>`, with the uuid from `~/.config/bws/secrets.map`
  (`NAME=uuid`, no values, safe to commit). Prefer `bws run`; `bws secret get` is UUID-only.
- **Never** `cat`, `echo`, `grep` or otherwise print a `.env` file, a token file, or the output of
  `bws secret get`. That is how seven live keys ended up in a session transcript.
- **Do not add secrets to `.env` files.** If a new credential appears, tell Titus to store it in
  Bitwarden; do not persist it to disk yourself.

Auth on each machine, so you do not need to ask:

| | Token | Scope |
|---|---|---|
| Mac | pasted per-shell via `read -rs BWS_ACCESS_TOKEN` | read/write |
| Desktop | `~/.config/bws/token` (0600), exported by `~/.bashrc` | **read-only** |

> **Therefore: run anything needing a credential on the desktop.** Read the Mac row again — that token
> is pasted into Titus's interactive shell and stored nowhere. Every agent Bash call is a *fresh*
> shell, so it never inherits the paste, and there is nothing on disk to recover: `bws` keeps a state
> file under `~/.config/bws/state/` but refuses to authenticate from it (`Missing access token`),
> there is no `~/.config/bws/config`, and the keychain holds nothing. By design, not a gap.
>
> **Do not ask Titus to paste, find, or re-mint that token.** He cannot see it again without revoking
> the machine account. Asking is the exact failure this note exists to stop — on 2026-08-14 an agent
> asked three times while this table was already in its context. `ssh desktop` and run it there under
> `bwsrun`; that token is persistent and needs nothing from him, ever. If the desktop lacks the repo
> or a venv, building it there is your work, not his.

The desktop token cannot create or modify secrets — a 404 from the API there is expected and is not a
bug to work around. If a task genuinely needs to write a secret, say so and stop; do not escalate.

> **Known wart, 2026-08-13.** Some keys diverge across repos: 3 distinct Anthropic, 3 OpenRouter,
> 2 OpenAI. The extras are stored suffixed (`ANTHROPIC_API_KEY__FEEDCAST`). Because `bws run` injects
> everything by key name, a repo needing a suffixed key will receive the wrong value in the plain
> name. Until rotation consolidates these to one key per vendor, check which key a repo actually
> needs before assuming the plain name is correct.
