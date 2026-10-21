#!/usr/bin/env python3
"""Pull-only sync of the global agent instructions (config/AGENTS.shared.md, config/AGENTS.email.md).

main on GitHub is the only source. Each machine runs this every hour (sync/install.sh sets up a
systemd user timer on the desktop and a launchd agent on the Mac); nothing is copied between machines.

Each run:
1. fetches origin/main and fast-forwards ~/pyg/claude-remote-setup, but only when the checkout is on
   main, has no uncommitted edits to tracked files and no commits GitHub lacks. Otherwise it changes
   nothing and reports the problem.
2. rebuilds ~/.codex/AGENTS.md as AGENTS.shared.md + AGENTS.email.md, keeping any block another
   installer appended between <!-- name --> and <!-- /name --> lines. Claude reads the checkout's files
   directly (~/.claude/CLAUDE.md imports them), so this keeps Codex on Claude's text even while step 1
   is stuck.

A problem goes to ~/.local/state/sync-instructions/status.json. The desktop emails it to Titus from the
agents account, once per new problem, and reads the Mac's status over ssh to do the same for the Mac.
The Mac also shows a notification.

    sync_instructions.py            one run
    sync_instructions.py --codex    only rebuild ~/.codex/AGENTS.md (setup-codex.sh)
    sync_instructions.py --status   print this machine's last status
"""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OWNER = "titusbuckworth@gmail.com"
MAC_HOST = "macbook"  # ssh alias of the Mac on the desktop
IS_MAC = platform.system() == "Darwin"
MACHINE = "the Mac" if IS_MAC else "the desktop"
FETCH_GRACE = 24 * 3600  # GitHub unreachable for this long is a problem; shorter is a blip
MAC_STALE = 26 * 3600  # the Mac answers ssh but has not run for this long: its job is not loaded
STATUS_REL = ".local/state/sync-instructions/status.json"
# A block another installer appended to ~/.codex/AGENTS.md, e.g. <!-- arrow-board:selected-projects -->.
MARKED = re.compile(r"^<!-- ([\w:.-]+) -->\n.*?^<!-- /\1 -->\n?", re.S | re.M)


class GitError(Exception):
    pass


def git(repo, *args, timeout=120):
    r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        lines = (r.stderr or r.stdout).strip().splitlines()
        raise GitError("git %s: %s" % (args[0], " ".join(lines[-3:]) or "exit %d" % r.returncode))
    return r.stdout.rstrip()  # not strip(): porcelain lines start with a space


def pull(repo):
    """Fast-forward repo to origin/main. Returns (pulled, problem, fetch_error); problem means it was left as is."""
    try:
        git(repo, "fetch", "-q", "origin", "main")
    except (GitError, subprocess.TimeoutExpired) as e:
        return False, None, str(e)
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        return False, "the checkout is on branch %s, not main" % branch, None
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        files = [line[3:] for line in dirty.splitlines()]
        return False, "uncommitted edits to %s" % ", ".join(files), None
    ahead = git(repo, "rev-list", "--count", "origin/main..HEAD")
    if ahead != "0":
        return False, "main has %s commit(s) that are not on GitHub" % ahead, None
    if git(repo, "rev-parse", "HEAD") == git(repo, "rev-parse", "origin/main"):
        return False, None, None
    try:
        git(repo, "merge", "-q", "--ff-only", "origin/main")
    except GitError as e:  # e.g. an untracked file in the way of a newly tracked one
        return False, str(e), None
    return True, None, None


def codex_text(repo, old):
    """AGENTS.shared.md + AGENTS.email.md, then the marked blocks of the old file that are not already in it."""
    shared = (repo / "config" / "AGENTS.shared.md").read_text()
    email = (repo / "config" / "AGENTS.email.md").read_text()
    text = shared + ("" if shared.endswith("\n") else "\n") + email
    for m in MARKED.finditer(old or ""):
        if m.group(0).strip() not in text:
            text = text.rstrip("\n") + "\n\n" + m.group(0).rstrip("\n") + "\n"
    return text


def write_codex(repo, path):
    """Rebuild path in place. Returns True if it changed. Never writes through a symlink: on 2026-09-11
    ~/.codex/AGENTS.md was a symlink to AGENTS.shared.md and `cat A B > link` truncated A."""
    old, mode = None, 0o644
    if path.exists():
        old = path.read_text()
        if not path.is_symlink():
            mode = path.stat().st_mode & 0o777
    text = codex_text(repo, old)
    if text == old and not path.is_symlink():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".AGENTS.md.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, str(path))  # replaces a symlink itself, not its target
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


def load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save(path, status):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=1) + "\n")
    os.replace(str(tmp), str(path))


def fix_hint(problem):
    if problem.startswith("uncommitted edits"):
        return ("Commit them on a branch and merge to main on GitHub (or discard them with git checkout -- FILE "
                "if main already has them).")
    if problem.startswith("the checkout is on branch"):
        return "Merge or save that branch's work, then git switch main."
    if "not on GitHub" in problem:
        return "Push them through a pull request, or reset main to origin/main if they are already merged."
    return "Look at ~/pyg/claude-remote-setup on that machine."


def email(machine, problem):
    """From the agents account; mail to Titus this short is not held for review."""
    body = ("The hourly sync of agent instructions on %s stopped: %s.\n\n%s\n\nUntil then %s keeps the "
            "instructions it has; Codex still matches Claude there. You get this once per new problem.\n"
            % (machine, problem, fix_hint(problem), machine))
    subject = "Agent instructions not updating on %s" % machine
    env = {k: v for k, v in os.environ.items() if not k.startswith("SSH_")}
    r = subprocess.run(["agent-mail", "send", "--unrouted", "--to", OWNER, "--subject", subject], input=body,
                       capture_output=True, text=True, timeout=180, env=env)
    return r.returncode == 0


def mac_banner(problem):
    msg = (problem[:180] + " (see ~/Library/Logs/sync-instructions.log)").replace('"', "'")
    subprocess.run(["osascript", "-e", 'display notification "%s" with title "Agent instructions sync"' % msg],
                   capture_output=True, timeout=30)


def notify(status, key, machine, problem, send):
    """Tell Titus about problem once: status[key] remembers the last one reported; cleared when fixed."""
    if not problem:
        status.pop(key, None)
        return
    if status.get(key) == problem:
        return
    if send(machine, problem):
        status[key] = problem


def mac_problem(now):
    """The Mac's own reported problem, read over ssh; None if it is fine or unreachable (asleep, away)."""
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", MAC_HOST, "cat " + STATUS_REL],
                           capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode == 255:  # ssh itself failed: the Mac is off the tailnet
        return None
    try:
        st = json.loads(r.stdout) if r.returncode == 0 else {}
    except ValueError:
        st = {}
    if not st.get("checked_at") or now - st["checked_at"] > MAC_STALE:
        when = time.strftime("%d %b %H:%M", time.localtime(st["checked_at"])) if st.get("checked_at") else "never"
        return "its hourly job has not run (last run: %s); run sync/install.sh there" % when
    return st.get("problem")


def run(repo, codex, state, check_mac):
    now = int(time.time())
    status = load(state)
    pulled, problem, fetch_error = pull(repo)
    if fetch_error:
        status.setdefault("fetch_failing_since", now)
        if now - status["fetch_failing_since"] > FETCH_GRACE:
            problem = "GitHub unreachable since %s (%s)" % (
                time.strftime("%d %b %H:%M", time.localtime(status["fetch_failing_since"])), fetch_error)
    else:
        status.pop("fetch_failing_since", None)
    rebuilt = write_codex(repo, codex)
    status.update(checked_at=now, head=git(repo, "rev-parse", "--short", "HEAD"), pulled=pulled,
                  codex_rebuilt=rebuilt, problem=problem, fetch_error=fetch_error)
    if IS_MAC:
        notify(status, "reported", MACHINE, problem, lambda m, p: mac_banner(p) or True)
    else:
        notify(status, "reported", MACHINE, problem, email)
        if check_mac:
            notify(status, "reported_mac", "the Mac", mac_problem(now), email)
    save(state, status)
    print("%s head %s%s%s%s" % (MACHINE, status["head"], ", pulled" if pulled else "",
                                ", rebuilt ~/.codex/AGENTS.md" if rebuilt else "",
                                "; PROBLEM: " + problem if problem else
                                ("; fetch failed: " + fetch_error if fetch_error else "")))


def main():
    home = Path.home()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--codex", action="store_true", help="only rebuild ~/.codex/AGENTS.md from the checkout")
    p.add_argument("--status", action="store_true", help="print this machine's last status")
    p.add_argument("--repo", type=Path, default=home / "pyg" / "claude-remote-setup")
    p.add_argument("--codex-file", type=Path, default=Path(os.environ.get("CODEX_HOME", home / ".codex")) / "AGENTS.md")
    p.add_argument("--state", type=Path, default=home / STATUS_REL)
    p.add_argument("--no-mac", action="store_true", help="on the desktop, do not check the Mac's status")
    a = p.parse_args()
    if a.status:
        print(json.dumps(load(a.state), indent=1))
    elif a.codex:
        print("rebuilt" if write_codex(a.repo, a.codex_file) else "unchanged", a.codex_file)
    else:
        run(a.repo, a.codex_file, a.state, check_mac=not a.no_mac)


if __name__ == "__main__":
    sys.exit(main())
