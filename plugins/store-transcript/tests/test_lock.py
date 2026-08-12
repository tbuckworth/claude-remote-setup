#!/usr/bin/env python3
"""Check that archive_lock actually serialises concurrent runs.

The archive is a single git checkout with a single HEAD. Since the command
archives in the background, the session stays usable and a second run is
genuinely reachable, so two runs can interleave on that tree: one run's
`checkout -B` moves HEAD out from under the other. The lock is what prevents it.

Run after touching the lock:

    python3 plugins/store-transcript/tests/test_lock.py

Stdlib only.
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

# Each child takes the lock, records enter/exit timestamps, and holds it briefly.
CHILD = """
import json, os, sys, time
sys.path.insert(0, {scripts!r})
from store_transcript import archive_lock
with archive_lock(timeout=30):
    enter = time.monotonic()
    time.sleep(0.6)
    exit_ = time.monotonic()
print(json.dumps([enter, exit_]))
"""

failures = []


def check(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        failures.append(msg)


def spans(lockfile, n):
    env = {**dict(__import__("os").environ), "STORE_TRANSCRIPT_LOCK_FILE": str(lockfile)}
    procs = [
        subprocess.Popen([sys.executable, "-c", CHILD.format(scripts=str(SCRIPTS))],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for _ in range(n)
    ]
    out = []
    for p in procs:
        so, se = p.communicate(timeout=90)
        if p.returncode != 0:
            print(f"    child failed: {se.strip()}")
            return None
        # the child may also print the "waiting" notice; take the JSON line
        line = [ln for ln in so.strip().splitlines() if ln.startswith("[")][-1]
        out.append(__import__("json").loads(line))
    return out


def main():
    print("archive_lock serialisation")
    with tempfile.TemporaryDirectory() as tmp:
        lockfile = Path(tmp) / "archive.lock"

        got = spans(lockfile, 3)
        check(got is not None, "three concurrent holders all completed")
        if got is None:
            return 1

        got.sort()
        overlaps = [
            (a, b) for a, b in zip(got, got[1:]) if b[0] < a[1]
        ]
        check(not overlaps,
              f"no two holders were inside the lock at once ({len(overlaps)} overlap(s))")

        total_held = sum(e - s for s, e in got)
        wall = max(e for _, e in got) - min(s for s, _ in got)
        check(wall >= total_held * 0.9,
              f"wall time {wall:.2f}s reflects serial execution, not parallel "
              f"(sum of held time {total_held:.2f}s)")

        check(lockfile.exists(), "lock file was created outside the archive repo")

    print("\nlock timeout")
    with tempfile.TemporaryDirectory() as tmp:
        lockfile = Path(tmp) / "archive.lock"
        holder_src = CHILD.format(scripts=str(SCRIPTS)).replace("time.sleep(0.6)", "time.sleep(8)")
        import os as _os
        env = {**dict(_os.environ), "STORE_TRANSCRIPT_LOCK_FILE": str(lockfile)}
        holder = subprocess.Popen([sys.executable, "-c", holder_src],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        time.sleep(1.5)
        waiter_src = CHILD.format(scripts=str(SCRIPTS)).replace("timeout=30", "timeout=2")
        waiter = subprocess.run([sys.executable, "-c", waiter_src],
                                capture_output=True, text=True, env=env, timeout=60)
        check(waiter.returncode != 0, "a run that cannot get the lock in time exits non-zero")
        check("nothing was archived" in waiter.stderr,
              "the timeout message says plainly that nothing was archived")
        holder.communicate(timeout=60)

    print("\nholder stays identifiable while a waiter is blocked")
    with tempfile.TemporaryDirectory() as tmp:
        import os as _os
        lockfile = Path(tmp) / "archive.lock"
        env = {**dict(_os.environ), "STORE_TRANSCRIPT_LOCK_FILE": str(lockfile)}
        holder_src = CHILD.format(scripts=str(SCRIPTS)).replace("time.sleep(0.6)", "time.sleep(6)")
        holder = subprocess.Popen([sys.executable, "-c", holder_src],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        time.sleep(1.5)
        waiter_src = CHILD.format(scripts=str(SCRIPTS)).replace("timeout=30", "timeout=1")
        waiter = subprocess.run([sys.executable, "-c", waiter_src],
                                capture_output=True, text=True, env=env, timeout=60)
        # The waiter opens the same file. If it truncated on open, the PID would be gone.
        contents = lockfile.read_text().strip()
        check(contents == str(holder.pid),
              f"lock file still names the holder ({contents!r} == pid {holder.pid}) "
              "after a waiter opened it")
        check(str(holder.pid) in waiter.stderr,
              "the timeout message names the holding PID")
        check("Do not delete the lock file" in waiter.stderr,
              "the timeout message warns against deleting the lock file")
        holder.communicate(timeout=60)

    print("\nmalformed timeout env does not break unrelated runs")
    import os as _os
    bad = {**dict(_os.environ), "STORE_TRANSCRIPT_LOCK_TIMEOUT": "10m"}
    helped = subprocess.run([sys.executable, str(SCRIPTS / "store_transcript.py"), "--help"],
                            capture_output=True, text=True, env=bad, timeout=60)
    check(helped.returncode == 0,
          "`--help` still works with a malformed STORE_TRANSCRIPT_LOCK_TIMEOUT")
    check("Traceback" not in helped.stderr,
          "no traceback from parsing the timeout at import")

    print("\nnon-contention flock errors are not reported as contention")
    probe = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(SCRIPTS)!r});\n"
         "import store_transcript as st, inspect;\n"
         "src = inspect.getsource(st.archive_lock);\n"
         "print('BlockingIOError' in src and 'except OSError:' not in src)"],
        capture_output=True, text=True, timeout=60)
    check(probe.stdout.strip() == "True",
          "retry path catches BlockingIOError only, so ENOLCK/EOPNOTSUPP propagate")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
