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
- After changing local agent configuration, run `bash ~/.claude/sync-config.sh` to synchronize supported configuration to the desktop.

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
