#!/usr/bin/env python3
"""Archive the current agent session transcript into the deception-transcripts repo.

Copies the live session JSONL into <archive>/<session-id>/, writes a log.md with the
reason and the source repo's commit/remote, then commits on a branch, pushes, opens a
PR and merges it.

Works for both Claude Code (~/.claude/projects/<slug>/<id>.jsonl) and Codex
(~/.codex/sessions/YYYY/MM/DD/rollout-*-<id>.jsonl).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scrub  # noqa: E402

DEFAULT_ARCHIVE = Path(
    os.environ.get("STORE_TRANSCRIPT_ARCHIVE")
    or Path.home() / "pyg" / "deception-transcripts"
)
DEFAULT_REPO_SLUG = os.environ.get("STORE_TRANSCRIPT_REPO") or "deception-transcripts"
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
DEFAULT_LOCK = Path.home() / ".config" / "store-transcript" / "archive.lock"
DEFAULT_LOCK_TIMEOUT = 600.0


def lock_timeout() -> float:
    """Read the timeout lazily, and never let a bad value break unrelated runs.

    Parsing this at import time meant a malformed STORE_TRANSCRIPT_LOCK_TIMEOUT
    ("10m", "600s") raised at module load — before argparse — so even `--help`
    and `--no-pr`, which never take the lock, died with a traceback.
    """
    raw = os.environ.get("STORE_TRANSCRIPT_LOCK_TIMEOUT")
    if not raw:
        return DEFAULT_LOCK_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        value = None
    # float() happily returns nan and inf. A nan deadline makes every
    # `now >= deadline` comparison False, so a contended run would spin in the
    # retry loop forever rather than falling back -- the precise failure this
    # function exists to prevent. Zero and negatives exit instantly and report
    # "held for over -1s".
    if value is None or not math.isfinite(value) or value <= 0:
        sys.stderr.write(
            f"ignoring unusable STORE_TRANSCRIPT_LOCK_TIMEOUT={raw!r}; "
            f"using {DEFAULT_LOCK_TIMEOUT:.0f}s\n"
        )
        return DEFAULT_LOCK_TIMEOUT
    return value


@contextlib.contextmanager
def archive_lock(timeout: float | None = None):
    """Serialise every run that mutates the shared archive working tree.

    The archive is one git checkout with one HEAD. Two overlapping runs interleave
    on it: one run's `checkout -B` moves HEAD out from under the other, so the
    other's `git add`/`commit` lands on the wrong branch, and `git add -A <dest>`
    can sweep a half-written sibling directory into the wrong commit. Since the
    command now archives in the background, the session stays usable and a second
    run is genuinely reachable, so this is a real race rather than a theoretical one.

    The lock lives outside the archive repo so it is never committed, and is held
    for the whole git section rather than per-command.
    """
    timeout = lock_timeout() if timeout is None else timeout
    path = Path(os.environ.get("STORE_TRANSCRIPT_LOCK_FILE") or DEFAULT_LOCK)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    waited = False
    # "a+" never truncates. Opening "w" would wipe the current holder's PID line
    # before this process had the lock, leaving the file empty for the whole time
    # it is held and the holder unidentifiable.
    with open(path, "a+") as handle:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                # Genuine contention: someone else holds it. Everything else --
                # ENOLCK, EOPNOTSUPP on an NFS home without lock support, EBADF --
                # is not contention, and spinning on it would burn the whole
                # timeout and then blame a run that does not exist.
                if time.monotonic() >= deadline:
                    holder = ""
                    with contextlib.suppress(OSError):
                        handle.seek(0)
                        pid = handle.read().strip().splitlines()
                        if pid:
                            holder = f" (held by pid {pid[-1]})"
                    raise SystemExit(
                        f"another store-transcript run has held {path}{holder} for over "
                        f"{timeout:.0f}s; nothing was archived. Re-run once it finishes.\n"
                        "Do not delete the lock file: the lock is released automatically "
                        "when the holding process exits, so a lock still held means a real "
                        "run is still going."
                    )
                if not waited:
                    print("Waiting for another store-transcript run to finish...")
                    waited = True
                time.sleep(1)
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                handle.seek(0)
                handle.truncate()
            fcntl.flock(handle, fcntl.LOCK_UN)


def run(cmd, cwd=None, check=True, quiet=False):
    """Run a command, returning stripped stdout."""
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )
    if check and proc.returncode != 0:
        if not quiet:
            sys.stderr.write(f"$ {' '.join(cmd)}\n{proc.stdout}{proc.stderr}\n")
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return proc.stdout.strip(), proc.returncode


def first_json_line(path: Path) -> dict:
    """Return the first line of a JSONL file that parses as a JSON object."""
    with path.open("r", errors="replace") as fh:
        for _ in range(50):
            line = fh.readline()
            if not line:
                break
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    return {}


# --- transcript discovery -------------------------------------------------


def find_claude_transcript(session_id: str | None) -> Path | None:
    if session_id:
        matches = sorted(CLAUDE_PROJECTS.glob(f"*/{session_id}.jsonl"))
        return matches[0] if matches else None
    candidates = list(CLAUDE_PROJECTS.glob("*/*.jsonl"))
    return newest_for_cwd(candidates, cwd_of_claude)


def cwd_of_claude(path: Path) -> str | None:
    return first_json_line(path).get("cwd")


def cwd_of_codex(path: Path) -> str | None:
    payload = first_json_line(path).get("payload") or {}
    return payload.get("cwd")


def codex_session_id(path: Path) -> str | None:
    payload = first_json_line(path).get("payload") or {}
    sid = payload.get("session_id") or payload.get("id")
    if sid:
        return sid
    m = re.search(r"rollout-.*?-([0-9a-f-]{36})\.jsonl$", path.name)
    return m.group(1) if m else None


def find_codex_transcript(session_id: str | None) -> Path | None:
    candidates = list(CODEX_SESSIONS.glob("*/*/*/rollout-*.jsonl"))
    if session_id:
        exact = [p for p in candidates if session_id in p.name]
        if exact:
            return max(exact, key=lambda p: p.stat().st_mtime)
        return None
    return newest_for_cwd(candidates, cwd_of_codex)


def newest_for_cwd(candidates: list[Path], cwd_getter) -> Path | None:
    """Pick the most recently modified transcript whose recorded cwd is the current dir.

    The live session is the one still being appended to, so mtime order is the
    reliable signal. Falls back to newest overall if no cwd matches.
    """
    if not candidates:
        return None
    here = str(Path.cwd().resolve())
    by_recency = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    for path in by_recency[:60]:
        recorded = cwd_getter(path)
        if recorded and str(Path(recorded).resolve()) == here:
            return path
    return by_recency[0]


def detect_agent() -> str:
    if os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return "claude"
    if any(k.startswith("CODEX") for k in os.environ):
        return "codex"
    return "claude"


# --- source repo metadata -------------------------------------------------


def repo_info(session_cwd: str | None) -> dict:
    """Collect git metadata for the repo the session was working in."""
    start = Path(session_cwd) if session_cwd and Path(session_cwd).is_dir() else Path.cwd()
    root, rc = run(["git", "rev-parse", "--show-toplevel"], cwd=start, check=False, quiet=True)
    if rc != 0:
        return {"session_cwd": str(start), "is_repo": False}

    root_path = Path(root)
    commit, _ = run(["git", "rev-parse", "HEAD"], cwd=root_path)
    branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root_path)
    remote, rc_remote = run(["git", "remote", "get-url", "origin"], cwd=root_path, check=False, quiet=True)
    dirty, _ = run(["git", "status", "--porcelain"], cwd=root_path)

    info = {
        "session_cwd": str(start),
        "is_repo": True,
        "root": str(root_path),
        "name": root_path.name,
        "commit": commit,
        "branch": branch,
        "remote": remote if rc_remote == 0 else None,
        "dirty": bool(dirty),
    }
    info["commit_url"] = commit_url(info["remote"], commit)
    return info


def commit_url(remote: str | None, commit: str) -> str | None:
    if not remote:
        return None
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
    if not m:
        return None
    return f"https://github.com/{m.group(1)}/commit/{commit}"


# --- archive repo ---------------------------------------------------------


def qualify_slug(repo_slug: str) -> str:
    """Expand a bare repo name to owner/name using the logged-in GitHub account."""
    if "/" in repo_slug:
        return repo_slug
    owner, rc = run(["gh", "api", "user", "-q", ".login"], check=False, quiet=True)
    if rc != 0 or not owner:
        raise SystemExit(
            "not logged in to GitHub (run `gh auth login`), or set "
            "STORE_TRANSCRIPT_REPO=<owner>/<repo>"
        )
    return f"{owner}/{repo_slug}"


def ensure_archive(archive: Path, repo_slug: str) -> None:
    """Make sure the archive exists locally, is a git repo, and has a GitHub remote."""
    archive.mkdir(parents=True, exist_ok=True)
    if not (archive / ".git").is_dir():
        run(["git", "init", "-q", "-b", "main"], cwd=archive)
    _, rc = run(["git", "remote", "get-url", "origin"], cwd=archive, check=False, quiet=True)
    if rc != 0:
        _, exists = run(["gh", "repo", "view", repo_slug], check=False, quiet=True)
        if exists != 0:
            run(["gh", "repo", "create", repo_slug, "--private"], cwd=archive)
        run(["git", "remote", "add", "origin",
             f"https://github.com/{repo_slug}.git"], cwd=archive)


def default_branch(archive: Path) -> str:
    head, rc = run(["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
                   cwd=archive, check=False, quiet=True)
    if rc == 0 and head:
        return head.rsplit("/", 1)[-1]
    branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=archive)
    return branch if branch != "HEAD" else "main"


def sync_base(archive: Path, base: str) -> None:
    _, rc = run(["git", "rev-parse", "--verify", base], cwd=archive, check=False, quiet=True)
    if rc == 0:
        run(["git", "checkout", "-q", base], cwd=archive)
    _, rc = run(["git", "ls-remote", "--exit-code", "origin", base],
                cwd=archive, check=False, quiet=True)
    if rc == 0:
        run(["git", "pull", "-q", "--ff-only", "origin", base], cwd=archive, check=False)


# --- log ------------------------------------------------------------------


def write_log(dest: Path, *, reason: str, agent: str, session_id: str,
              transcript: Path, size: int, repo: dict, audit: dict | None) -> None:
    lines = [
        f"# Session transcript archive — {session_id}",
        "",
        "## Why this was stored",
        "",
        reason.strip(),
        "",
        "## Session",
        "",
        f"- **Agent:** {agent}",
        f"- **Session ID:** `{session_id}`",
        f"- **Transcript file:** `{transcript.name}` ({size:,} bytes)",
        f"- **Source path:** `{transcript}`",
        f"- **Session working directory:** `{repo.get('session_cwd')}`",
        f"- **Archived:** {date.today().isoformat()}",
        "",
        "## Repository state at time of archiving",
        "",
    ]
    if repo.get("is_repo"):
        lines += [
            f"- **Repo:** `{repo['name']}`",
            f"- **Local path:** `{repo['root']}`",
            f"- **Remote (origin):** {repo['remote'] or '_none_'}",
            f"- **Branch:** `{repo['branch']}`",
            f"- **Commit hash:** `{repo['commit']}`",
            f"- **Working tree:** {'dirty (uncommitted changes present)' if repo['dirty'] else 'clean'}",
        ]
        if repo.get("commit_url"):
            lines.append(f"- **Permalink to commit:** {repo['commit_url']}")
    else:
        lines.append("- Session working directory is not a git repository; no commit recorded.")

    lines += ["", "## Scrubbing", ""]
    if audit is None:
        lines.append("- **Not scrubbed** (`--no-scrub`). This transcript may contain "
                     "live credentials.")
    else:
        lines += [
            f"- Secrets scrambled: **{audit['total']}** "
            f"({audit['distinct']} distinct values) across {audit['lines']:,} lines",
            "- Substitution is deterministic and format-preserving; see "
            "`scrub-audit.md` for the per-rule breakdown.",
            "- Verified: no original secret value survives in the stored file.",
        ]
    lines.append("")
    dest.write_text("\n".join(lines))


# --- PR -------------------------------------------------------------------


def open_and_merge_pr(archive: Path, branch: str, base: str, title: str, body: str) -> str | None:
    run(["git", "push", "-q", "-u", "origin", branch], cwd=archive)
    url, rc = run(["gh", "pr", "create", "--base", base, "--head", branch,
                   "--title", title, "--body", body], cwd=archive, check=False, quiet=True)
    if rc != 0:
        existing, rc2 = run(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"],
                            cwd=archive, check=False, quiet=True)
        if rc2 != 0:
            raise SystemExit("could not create or find a PR for this branch")
        url = existing

    # GitHub needs a moment to compute mergeability on a fresh PR.
    for attempt in range(6):
        _, rc = run(["gh", "pr", "merge", branch, "--squash", "--delete-branch"],
                    cwd=archive, check=False, quiet=True)
        if rc == 0:
            break
        time.sleep(2 * (attempt + 1))
    else:
        sys.stderr.write(f"PR created but auto-merge failed; merge manually: {url}\n")
        return url

    run(["git", "checkout", "-q", base], cwd=archive)
    run(["git", "pull", "-q", "--ff-only", "origin", base], cwd=archive, check=False)
    run(["git", "fetch", "-q", "--prune", "origin"], cwd=archive, check=False)
    return url


# --- main -----------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("reason", help="why this transcript is being stored")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--agent", choices=["claude", "codex", "auto"], default="auto")
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    ap.add_argument("--repo-slug", default=DEFAULT_REPO_SLUG)
    ap.add_argument("--no-pr", action="store_true",
                    help="commit locally only; do not push, PR, or merge")
    ap.add_argument("--no-scrub", action="store_true",
                    help="store the transcript verbatim, WITHOUT scrambling secrets")
    args = ap.parse_args()

    agent = detect_agent() if args.agent == "auto" else args.agent
    if agent == "codex":
        transcript = find_codex_transcript(args.session_id)
        session_id = codex_session_id(transcript) if transcript else None
        session_cwd = cwd_of_codex(transcript) if transcript else None
    else:
        # Claude Code exports the live session id; an explicit --session-id wins.
        sid = args.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID")
        transcript = find_claude_transcript(sid)
        session_id = sid or (transcript.stem if transcript else None)
        session_cwd = cwd_of_claude(transcript) if transcript else None

    if not transcript or not transcript.is_file():
        raise SystemExit(f"could not locate a {agent} session transcript")
    session_id = session_id or transcript.stem

    repo = repo_info(session_cwd)

    # Everything past this point mutates the shared archive checkout, so it runs
    # under the lock. Locating and reading the session transcript above touches
    # nothing shared and stays outside it.
    with archive_lock():
        archive_into_repo(args, agent=agent, transcript=transcript,
                          session_id=session_id, repo=repo)


def archive_into_repo(args, *, agent: str, transcript: Path, session_id: str,
                      repo: dict) -> None:
    ensure_archive(args.archive, qualify_slug(args.repo_slug))
    base = default_branch(args.archive)
    sync_base(args.archive, base)

    dest_dir = args.archive / session_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / transcript.name

    # Scrub before anything is written into the repo: a secret that reaches the
    # first commit is in git history for good, and no later fix-up removes it.
    audit = None
    if args.no_scrub:
        shutil.copy2(transcript, dest_file)
    else:
        audit = scrub.scrub_file(transcript, dest_file, scrub.load_salt())
        leaked = scrub.verify(dest_file, audit["originals"])
        if leaked:
            dest_file.unlink(missing_ok=True)
            raise SystemExit(
                f"ABORTED: {len(leaked)} secret value(s) survived scrubbing; "
                "nothing was written. This is a scrubber bug — please report it."
            )
        (dest_dir / "scrub-audit.md").write_text(scrub.audit_markdown(audit))

    write_log(dest_dir / "log.md", reason=args.reason, agent=agent,
              session_id=session_id, transcript=transcript,
              size=dest_file.stat().st_size, repo=repo, audit=audit)

    _, rc = run(["git", "diff", "--quiet", "HEAD", "--"], cwd=args.archive,
                check=False, quiet=True)
    status, _ = run(["git", "status", "--porcelain"], cwd=args.archive)
    if not status:
        print(f"No changes to commit; {dest_dir} is already up to date.")
        return

    branch = f"store/{session_id}"
    run(["git", "checkout", "-q", "-B", branch], cwd=args.archive)
    run(["git", "add", "-A", str(dest_dir)], cwd=args.archive)
    summary = " ".join(args.reason.split())
    if len(summary) > 60:
        summary = summary[:57] + "..."
    title = f"Store transcript {session_id[:8]}: {summary}"
    body = (f"Archiving {agent} session `{session_id}`.\n\n"
            f"**Reason:** {args.reason.strip()}\n\n"
            f"**Source repo commit:** `{repo.get('commit', 'n/a')}`"
            f" ({repo.get('remote') or 'no remote'})\n")
    run(["git", "commit", "-q", "-m", title, "-m", body], cwd=args.archive)

    print(f"Archived {agent} session {session_id}")
    print(f"  transcript: {dest_file} ({dest_file.stat().st_size:,} bytes)")
    if repo.get("is_repo"):
        print(f"  source repo: {repo['remote'] or repo['root']} @ {repo['commit']}")

    if args.no_pr:
        print(f"  committed on branch {branch} (no PR requested)")
        return

    url = open_and_merge_pr(args.archive, branch, base, title, body)
    if url:
        print(f"  PR: {url}")


if __name__ == "__main__":
    main()
