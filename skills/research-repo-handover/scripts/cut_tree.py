"""Cut the pin down to the keep set: the tree that becomes the handover repo's first commit.

usage: python3 cut_tree.py JOB.toml     (reads [source] and [cut])

[cut] keys:
  keep      the keep set (make_keep_set.py's keep.tsv)
  tree      a new directory to write the cut tree into (refused if it exists and is not empty)
  commit    true: `git init` the tree and commit it, so later stages and replays have a base
  message   the commit message; `{repo}` and `{pin}` are filled in. Add any trailer lines here.
  commit_env  extra environment for the commit, stated in the config with its reason (e.g. a
            secret-scan hook's skip variable for a scratch tree whose findings are known false
            positives; the real repo gets a narrow allowlist instead)
The source repo is only read (`git archive`). Files outside the keep set are deleted, then empty
directories. Prints the counts and records them in cut_tree.run.json.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import (  # noqa: E402
    job_from_argv,
    materialise,
    read_tsv,
    require,
    tracked_at,
    walk_files,
    write_run_record,
)


def main() -> int:
    job = job_from_argv(__doc__)
    source, cfg = job.section("source"), job.section("cut")
    out_dir = job.out_dir(cfg)
    repo, pin = job.resolve(require(source, "repo", "source")), require(source, "pin", "source")
    keep_path = job.resolve(require(cfg, "keep", "cut"))
    keep = {row[0] for row in read_tsv(keep_path)}
    tree = job.resolve(require(cfg, "tree", "cut"))
    tracked = set(tracked_at(repo, pin))
    unknown = sorted(keep - tracked)
    if unknown:
        raise SystemExit(f"keep set names paths the pin does not track: {unknown[:5]}")
    materialise(repo, pin, tree)
    removed = 0
    for rel in walk_files(tree, skip_dirs=()):
        if rel not in keep:
            (tree / rel).unlink()
            removed += 1
    for dirpath, _dirs, _files in sorted(os.walk(tree), key=lambda w: -len(w[0])):
        if Path(dirpath) != tree and not any(Path(dirpath).iterdir()):
            Path(dirpath).rmdir()
    left = walk_files(tree, skip_dirs=())
    if set(left) != keep:
        raise SystemExit(f"cut tree differs from the keep set: {sorted(set(left) ^ keep)[:5]}")
    commit = None
    if cfg.get("commit"):
        message = cfg.get("message", "Minimal tree of {repo}@{pin}").format(
            repo=source.get("name", repo.name), pin=pin
        )
        env = {**os.environ, **{k: str(v) for k, v in cfg.get("commit_env", {}).items()}}

        def run(*args: str) -> str:
            done = subprocess.run(args, cwd=tree, capture_output=True, text=True, env=env)
            if done.returncode != 0:
                raise SystemExit(f"{' '.join(args[:2])} failed in {tree}:\n{done.stderr[-2000:]}")
            return done.stdout

        run("git", "init", "-q", "-b", cfg.get("branch", "main"))
        # --force: the keep set is the authority, including files the pin's .gitignore
        # ignores but upstream force-added (a data/raw/.gitkeep, say).
        run("git", "add", "-A", "--force")
        run("git", "commit", "-q", "-m", message)
        commit = run("git", "rev-parse", "HEAD").strip()
        committed = {p for p in run("git", "ls-files", "-z").split("\0") if p}
        if committed != keep:
            raise SystemExit(
                f"committed files differ from the keep set: {sorted(committed ^ keep)[:5]}"
            )
    results = {"kept": len(left), "removed": removed, "tree": str(tree), "commit": commit}
    write_run_record(job, out_dir, "cut_tree", {"keep": str(keep_path)}, results)
    print(f"cut {pin[:12]}: kept {len(left)}, removed {removed}; tree {tree}")
    if commit:
        print(f"committed {commit[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
