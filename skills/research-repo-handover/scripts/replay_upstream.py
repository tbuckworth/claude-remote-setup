"""Replay upstream PRs onto the handover repo's upstream-layout commit; merge through the renames.

usage: python3 replay_upstream.py JOB.toml     (reads [replay]; exit 3 at a conflict)

Works in a scratch clone of the handover repo that also holds the upstream commits. For each
[[replay.pr]], in order: take the PR's diff (merge^1..merge) restricted to files the branch
already has (plus upstream-added files matching `add`), minus `exclude`, apply it with
`git apply -3 --index`, and commit it alone. A PR whose commit message is already on the branch
is skipped, so after resolving a conflict by hand (and committing with the printed message) the
same command resumes. Order the PRs so changes that could alter results come last and can be
dropped. Then, if [replay.merge] is set, merge the branch into a new branch off the current
layout with `-X find-renames=<n>%`, so git carries each change through the renames.

[replay] keys:
  repo        the scratch clone (never the upstream repo or a shared checkout)
  fetch_from  optional: a repo to fetch upstream heads from (into refs/remotes/upstream/*)
              when a merge commit is missing
  base        the handover repo's last commit in upstream layout (e.g. the minimal-tree commit)
  branch      the branch to build (created at `base` if absent, resumed if present)
  exclude     regex of upstream paths never taken (docs, plans, archives, unkept configs)
  add         regex of upstream-added files to take
  message     commit message template: {label} and {merge} (default "upstream {label}, files
              the fork keeps"); `trailer` lines are appended
  [[replay.pr]]  merge (the upstream merge commit), label, optional only (regex of paths)
  [replay.merge] into (new branch name), from (the current-layout commit), find_renames (40)
Patches are written to the output directory, one per PR, with replay-report.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import job_from_argv, require, write_run_record  # noqa: E402


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done


def has_commit(repo: Path, rev: str) -> bool:
    return git(repo, "cat-file", "-e", f"{rev}^{{commit}}", check=False).returncode == 0


def pick(repo: Path, merge: str, only: str, exclude: str, add: str) -> list[str]:
    out = git(repo, "diff", "--name-status", "--no-renames", f"{merge}^1", merge).stdout
    files = []
    for line in out.splitlines():
        status, path = line.split("\t")[0], line.split("\t")[-1]
        if not re.search(only, path) or (exclude and re.search(exclude, path)):
            continue
        present = git(repo, "cat-file", "-e", f"HEAD:{path}", check=False).returncode == 0
        if present or (status == "A" and add and re.search(add, path)):
            files.append(path)
    return files


def main() -> int:
    job = job_from_argv(__doc__)
    cfg = job.section("replay")
    out_dir = job.out_dir(cfg)
    repo = job.resolve(require(cfg, "repo", "replay"))
    base, branch = require(cfg, "base", "replay"), require(cfg, "branch", "replay")
    exclude, add = cfg.get("exclude", ""), cfg.get("add", "")
    template = cfg.get("message", "upstream {label}, files the fork keeps")
    trailer = cfg.get("trailer", "")
    prs: list[dict[str, Any]] = require(cfg, "pr", "replay")
    if git(repo, "status", "--porcelain").stdout.strip():
        raise SystemExit(
            f"{repo} has uncommitted changes (a conflict to finish?); commit them first"
        )
    missing = [p["merge"] for p in prs if not has_commit(repo, p["merge"])]
    if missing and cfg.get("fetch_from"):
        git(
            repo,
            "fetch",
            "-q",
            str(job.resolve(cfg["fetch_from"])),
            "+refs/heads/*:refs/remotes/upstream/*",
        )
        missing = [m for m in missing if not has_commit(repo, m)]
    if missing:
        raise SystemExit(f"upstream commits not in {repo}: {missing}; set fetch_from or fetch them")
    if (
        git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False).returncode
        == 0
    ):
        git(repo, "switch", "-q", branch)
    else:
        git(repo, "switch", "-q", "-c", branch, base)
    done_messages = set(git(repo, "log", "--format=%s", f"{base}..HEAD").stdout.splitlines())
    report: list[dict[str, Any]] = []
    for pr in prs:
        merge, label = pr["merge"], pr.get("label", pr["merge"][:10])
        subject = template.format(label=label, merge=merge[:10])
        if subject in done_messages:
            print(f"== {label}: already on {branch}, skipped")
            report.append({"label": label, "status": "already replayed"})
            continue
        files = pick(repo, merge, pr.get("only", "."), exclude, add)
        print(f"== {label} ({merge[:10]}): {len(files)} file(s)")
        if not files:
            report.append({"label": label, "status": "nothing the branch keeps", "files": []})
            continue
        patch = out_dir / f"{re.sub(r'[^A-Za-z0-9_.-]+', '-', label).strip('-')}.patch"
        patch.write_text(
            git(repo, "diff", "--binary", f"{merge}^1", merge, "--", *files).stdout,
            encoding="utf-8",
        )
        applied = git(repo, "apply", "-3", "--index", str(patch), check=False)
        conflicted = git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()
        if conflicted or applied.returncode != 0:
            print(applied.stderr.strip())
            print("   CONFLICTS (resolve each to this PR's own change, then commit):")
            for f in conflicted:
                print(f"     {f}")
            print(f"   commit with: git -C {repo} commit -m {json.dumps(subject)}; then rerun")
            report.append(
                {"label": label, "status": "conflict", "files": files, "conflicted": conflicted}
            )
            (out_dir / "replay-report.json").write_text(json.dumps(report, indent=1) + "\n")
            return 3
        message = subject + (f"\n\n{trailer}" if trailer else "")
        git(repo, "commit", "-q", "-m", message)
        sha = git(repo, "rev-parse", "HEAD").stdout.strip()
        print(f"   committed {sha[:10]}")
        report.append({"label": label, "status": "committed", "commit": sha, "files": files})
    merge_cfg = cfg.get("merge")
    merged = None
    if merge_cfg:
        into, start = (
            require(merge_cfg, "into", "replay.merge"),
            require(merge_cfg, "from", "replay.merge"),
        )
        renames = int(merge_cfg.get("find_renames", 40))
        git(repo, "switch", "-q", "-c", into, start)
        result = git(repo, "merge", "--no-edit", f"-Xfind-renames={renames}%", branch, check=False)
        conflicted = git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()
        if result.returncode != 0:
            print(
                f"== merge {branch} into {into}: conflicts in {conflicted or result.stderr.strip()}"
            )
            print(
                "   A file shown as DU (deleted by us) fell below the rename threshold: apply the"
            )
            print(
                "   PR's change to its new path by hand. Then `git commit`, or `git merge --abort`."
            )
            (out_dir / "replay-report.json").write_text(json.dumps(report, indent=1) + "\n")
            return 3
        merged = git(repo, "rev-parse", "HEAD").stdout.strip()
        print(f"== merged {branch} into {into} with find-renames={renames}%: {merged[:10]}")
        print("   next: move upstream-added files to their new paths and rename their vocabulary")
    (out_dir / "replay-report.json").write_text(json.dumps(report, indent=1) + "\n")
    write_run_record(job, out_dir, "replay_upstream", {}, {"prs": len(prs), "merged": merged})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
