#!/usr/bin/env python3
"""Ship eval results: parse, upload to Drive, email comparison report.

Usage:
    python3 ship_eval.py <path>              # dir of .eval files or single .eval
    python3 ship_eval.py <path> --dry-run    # parse + report only, no upload/email
    python3 ship_eval.py <path> --skip-drive # email only, no Drive upload
    python3 ship_eval.py <dir> --glob '*.eval'        # custom glob pattern
    python3 ship_eval.py <dir> --since 2026-04-15T00:00:00  # filter by ctime

    # Poll Modal volume every 30m, ship when N evals land:
    python3 ship_eval.py --modal <remote_path> --expect 11 --poll 30

    # Poll until stable (no new evals for 2 consecutive checks):
    python3 ship_eval.py --modal <remote_path> --poll 30

Config: ~/.config/claude-eval-ship/config.json
    {"recipient_email": "...", "drive_parent_folder_id": "...", "gmail_label": "Evals"}
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

REQUIRED_PACKAGES = ["matplotlib", "google.auth", "googleapiclient"]


def _check_deps():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        pip_names = {
            "google.auth": "google-auth",
            "googleapiclient": "google-api-python-client",
        }
        to_install = [pip_names.get(m, m) for m in missing]
        print(f"Installing missing packages: {', '.join(to_install)}", file=sys.stderr)
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--break-system-packages", "--quiet", *to_install,
        ])


_check_deps()


SCRIPTS_DIR = Path(__file__).resolve().parent
GDRIVE_SCRIPT = Path.home() / "claude-remote-setup/plugins/yulia-gdrive-upload/scripts/upload_to_gdrive.py"
EMAIL_SCRIPT = SCRIPTS_DIR / "send_report_email.py"
REPORT_SCRIPT = SCRIPTS_DIR / "build_report.py"
CONFIG_PATH = Path.home() / ".config/claude-eval-ship/config.json"

# Copied from control_arena/.../ptb_eval_cli.py::_derive_eval_name (source of truth).
_SCAFFOLD_FROM_POLICY_TYPE = {
    "claude_code_policy": "claude_code",
    "codex_cli_policy": "codex_cli",
    "gemini_cli_policy": "gemini_cli",
}


def load_config():
    if not CONFIG_PATH.exists():
        print(f"ERROR: Config not found at {CONFIG_PATH}", file=sys.stderr)
        print('Create it with: {"recipient_email": "...", "drive_parent_folder_id": "...", "gmail_label": "Evals"}', file=sys.stderr)
        sys.exit(1)
    cfg = json.loads(CONFIG_PATH.read_text())
    for key in ("recipient_email", "drive_parent_folder_id", "gmail_label"):
        if not cfg.get(key) or cfg[key].startswith("FILL_IN"):
            print(f"ERROR: config key '{key}' is missing or placeholder in {CONFIG_PATH}", file=sys.stderr)
            sys.exit(1)
    return cfg


MODAL_VOLUME = "control-arena-eval-results"


def discover_evals(path, glob_pattern="*.eval", since=None):
    p = Path(path)
    if p.is_file() and p.suffix == ".eval":
        return [p]
    if p.is_dir():
        evals = sorted(p.glob(glob_pattern))
        if since:
            cutoff = datetime.fromisoformat(since).timestamp()
            evals = [e for e in evals if e.stat().st_ctime >= cutoff]
        return evals
    print(f"ERROR: {path} is not an .eval file or directory", file=sys.stderr)
    sys.exit(1)


def modal_ls(remote_path):
    """Count .eval files on the Modal volume under remote_path.

    Modal layout: each run gets its own subfolder (e.g. honest_20260417_1047_run000/)
    with one .eval file inside. So we list the parent to find matching subfolders,
    then count them (each subfolder = one eval).

    remote_path can be:
      - A specific run folder: /post_train_bench/honest_20260417_1047_run000/
      - A prefix to match multiple run folders: /post_train_bench/honest_20260417_1047

    Returns list of (subfolder, eval_filename) tuples.
    """
    # Normalise: if path ends without /, it's a prefix match on the parent dir
    remote_path = remote_path.rstrip("/")
    parent = remote_path.rsplit("/", 1)[0] + "/" if "/" in remote_path else "/"
    prefix = remote_path.rsplit("/", 1)[-1] if "/" in remote_path else remote_path

    result = subprocess.run(
        ["modal", "volume", "ls", MODAL_VOLUME, parent],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: modal volume ls failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Find matching subfolders
    matching_dirs = []
    for line in result.stdout.strip().splitlines():
        entry = line.strip().rstrip("/")
        basename = entry.rsplit("/", 1)[-1] if "/" in entry else entry
        if basename.startswith(prefix):
            matching_dirs.append(entry)

    # Check each subfolder for .eval files
    evals = []
    for subdir in matching_dirs:
        sub_result = subprocess.run(
            ["modal", "volume", "ls", MODAL_VOLUME, subdir + "/"],
            capture_output=True, text=True,
        )
        if sub_result.returncode != 0:
            continue
        for line in sub_result.stdout.strip().splitlines():
            name = line.strip()
            if name.endswith(".eval"):
                evals.append((subdir, name))

    return evals


def modal_download(remote_path, local_dir):
    """Download .eval files from matching run folders into a flat local dir.

    Each run folder contains one .eval; we download them all into local_dir.
    """
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    evals = modal_ls(remote_path)
    if not evals:
        print(f"ERROR: No .eval files found under {remote_path}", file=sys.stderr)
        sys.exit(1)

    for subdir, eval_name in evals:
        # Download the specific .eval file
        remote_file = eval_name if "/" in eval_name else f"{subdir}/{eval_name.rsplit('/', 1)[-1]}"
        result = subprocess.run(
            ["modal", "volume", "get", MODAL_VOLUME, remote_file, str(local_dir) + "/"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"WARNING: Failed to download {remote_file}: {result.stderr}", file=sys.stderr)
        else:
            basename = eval_name.rsplit("/", 1)[-1]
            print(f"  Downloaded: {basename}")

    return local_dir


def poll_modal(remote_path, poll_minutes, expect_n, local_dir):
    """Poll Modal volume until evals are ready, then download.

    "Ready" means either:
      - expect_n is set and we see >= expect_n .eval files, OR
      - expect_n is not set and count is stable across 2 consecutive checks
        (and count > 0).

    Returns the local directory containing downloaded evals.
    """
    prev_count = 0
    stable_checks = 0
    check_num = 0

    while True:
        check_num += 1
        evals = modal_ls(remote_path)
        count = len(evals)
        now = datetime.now().strftime("%H:%M")

        if expect_n:
            print(f"[{now}] Poll #{check_num}: {count}/{expect_n} evals on volume")
            if count >= expect_n:
                print(f"All {expect_n} evals found. Downloading...")
                return modal_download(remote_path, local_dir)
        else:
            print(f"[{now}] Poll #{check_num}: {count} evals on volume")
            if count > 0 and count == prev_count:
                stable_checks += 1
                if stable_checks >= 2:
                    print(f"Count stable at {count} for {stable_checks} checks. Downloading...")
                    return modal_download(remote_path, local_dir)
            else:
                stable_checks = 0

        prev_count = count
        print(f"  Waiting {poll_minutes}m until next check...")
        time.sleep(poll_minutes * 60)


def parse_eval(eval_path):
    """Parse a single .eval ZIP into a run dict for the report generator."""
    eval_path = Path(eval_path)
    try:
        zf = zipfile.ZipFile(eval_path)
    except zipfile.BadZipFile:
        print(f"ERROR: Bad ZIP: {eval_path}", file=sys.stderr)
        sys.exit(1)

    # --- header metadata ---
    try:
        header = json.loads(zf.read("header.json"))
    except KeyError:
        print(f"ERROR: No header.json in {eval_path}", file=sys.stderr)
        sys.exit(1)

    metadata = header.get("eval", {}).get("metadata", {}) or {}
    setting = metadata.get("setting") or {}

    mode = metadata.get("mode")
    if not mode:
        print(f"ERROR: Missing eval.metadata.mode in {eval_path}", file=sys.stderr)
        sys.exit(1)

    main_task = (setting.get("main_task") or "").strip("^$")
    side_task = setting.get("side_task") or ""
    backend = setting.get("training_backend") or "gpu"

    # --- scaffold from _journal/start.json ---
    scaffold = "react"
    config = "tuned"
    try:
        start = json.loads(zf.read("_journal/start.json"))
        skip_ckpt = None
        for step in start.get("plan", {}).get("steps", []):
            params = step.get("params", {})
            if "skip_starting_checkpoint" in params and skip_ckpt is None:
                skip_ckpt = params["skip_starting_checkpoint"]
            for value in params.values():
                if isinstance(value, dict):
                    ptype = value.get("type")
                    if ptype in _SCAFFOLD_FROM_POLICY_TYPE:
                        scaffold = _SCAFFOLD_FROM_POLICY_TYPE[ptype]
        config = "base" if skip_ckpt else "tuned"
    except KeyError:
        pass

    # --- sample scores ---
    sample_files = [n for n in zf.namelist() if n.startswith("samples/")]
    if not sample_files:
        print(f"ERROR: No samples in {eval_path}", file=sys.stderr)
        sys.exit(1)

    sample = json.loads(zf.read(sample_files[0]))
    if isinstance(sample, list):
        sample = sample[0] if sample else {}
    scores = sample.get("scores", {})

    # Fallback for main_task from sample id
    if not main_task:
        raw_id = sample.get("id", "")
        raw_id = raw_id.split("_ST:", 1)[0]
        main_task = raw_id.replace("MT:", "") or "unknown"

    main_score = scores.get("posttrain_main_scorer", {}).get("value")
    if main_score == "I":
        main_score = None

    # Side score: prefer multi_side_scorer, fall back to side_scorer
    side_scorer = scores.get("posttrain_multi_side_scorer") or scores.get("posttrain_side_scorer") or {}
    side_score = side_scorer.get("value")
    if side_score == "I":
        side_score = None

    # Per-side-task breakdown (honest runs report all 7)
    side_task_scores = {}
    raw_side = (side_scorer.get("metadata") or {}).get("side_task_scores", {})
    if isinstance(raw_side, dict):
        for sname, sentry in raw_side.items():
            if isinstance(sentry, dict):
                sscore = sentry.get("score")
                if isinstance(sscore, (int, float)):
                    side_task_scores[sname] = float(sscore)

    # Checkpoint data
    ckpt_scorer = scores.get("posttrain_checkpoint_scorer", {})
    best_checkpoint = ckpt_scorer.get("value")
    ckpt_meta = ckpt_scorer.get("metadata") or {}
    best_side_score = ckpt_meta.get("best_side_score")
    best_side_checkpoint = ckpt_meta.get("best_side_checkpoint")

    checkpoint_list = []
    raw_ckpts = ckpt_meta.get("checkpoint_scores", [])
    for c in raw_ckpts:
        if isinstance(c, str):
            try:
                c = ast.literal_eval(c)
            except (ValueError, SyntaxError):
                continue
        if isinstance(c, dict):
            checkpoint_list.append({
                "name": c.get("name", ""),
                "timestamp": c.get("timestamp", ""),
                "epoch_seconds": c.get("epoch_seconds", 0),
                "accuracy": c.get("accuracy", 0),
                "side_score": c.get("side_score"),
            })
    checkpoint_list.sort(key=lambda x: x.get("timestamp", ""))

    # --- canonical filename (logic from ptb_eval_cli._derive_eval_name) ---
    ts_match = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})", eval_path.name)
    if ts_match:
        y, mo, d, h, mi = ts_match.groups()
        timestamp = f"{y}{mo}{d}_{h}{mi}"
    else:
        timestamp = "unknown"

    side_part = f"_{side_task}" if side_task else ""
    canonical_name = f"{main_task}_{config}_{mode}{side_part}_{backend}_{scaffold}_{timestamp}.eval"

    return {
        "file": eval_path.name,
        "canonical_name": canonical_name,
        "path": str(eval_path),
        "task": main_task,
        "config": config,
        "mode": mode,
        "side_task": side_task,
        "main_score": main_score,
        "side_score": side_score,
        "side_task_scores": side_task_scores,
        "best_checkpoint": best_checkpoint,
        "best_side_score": best_side_score,
        "best_side_checkpoint": best_side_checkpoint,
        "checkpoints": checkpoint_list,
    }


def run_cmd(cmd, stdin_data=None):
    """Run a subprocess, fail loudly on error."""
    result = subprocess.run(cmd, capture_output=True, text=True, input=stdin_data)
    if result.returncode != 0:
        print(f"ERROR running: {' '.join(str(c) for c in cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return result.stdout


def build_subject(sweep_name, runs):
    """Build the email subject line."""
    n = len(runs)
    tasks = sorted({r["task"] for r in runs})
    modes = sorted({r["mode"] for r in runs})

    if n == 1:
        r = runs[0]
        main_pct = f"{r['main_score']*100:.0f}%" if r['main_score'] is not None else "CRASH"
        return f"[EVAL] {r['mode'].upper()} | {r['task']} | main={main_pct}"

    return f"[SWEEP] {sweep_name} | {n} runs | tasks={','.join(tasks)} | modes={','.join(modes)}"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ship eval results: parse, upload, email.")
    parser.add_argument("path", nargs="?", default=None,
                        help="Path to .eval file or directory of .eval files (not needed with --modal)")
    parser.add_argument("--sweep-name", default=None, help="Override sweep name")
    parser.add_argument("--skip-drive", action="store_true", help="Skip Drive upload")
    parser.add_argument("--dry-run", action="store_true", help="Parse + report only, no upload/email")
    parser.add_argument("--glob", default="*.eval", help="Glob pattern for eval discovery (default: *.eval)")
    parser.add_argument("--since", default=None, help="Only include evals created after this ISO timestamp")
    parser.add_argument("--modal", default=None, metavar="REMOTE_PATH",
                        help="Download evals from Modal volume before shipping (e.g. /my-sweep/)")
    parser.add_argument("--poll", type=int, default=None, metavar="MINUTES",
                        help="Poll Modal volume every N minutes until evals are ready (requires --modal)")
    parser.add_argument("--expect", type=int, default=None, metavar="N",
                        help="Expected number of .eval files (used with --poll to know when done)")
    args = parser.parse_args()

    if args.poll and not args.modal:
        print("ERROR: --poll requires --modal", file=sys.stderr)
        sys.exit(1)
    if args.expect and not args.poll:
        print("ERROR: --expect requires --poll", file=sys.stderr)
        sys.exit(1)
    if not args.path and not args.modal:
        print("ERROR: provide a path or --modal <remote_path>", file=sys.stderr)
        sys.exit(1)

    # 1. Config
    if not args.dry_run:
        cfg = load_config()
    else:
        cfg = {"recipient_email": "dry-run", "drive_parent_folder_id": "dry-run", "gmail_label": "Evals"}

    # 1b. Modal download (with optional polling)
    if args.modal:
        local_dir = Path(tempfile.mkdtemp(prefix="ship_modal_"))
        if args.poll:
            print(f"Polling Modal volume every {args.poll}m for {args.modal}")
            if args.expect:
                print(f"  Expecting {args.expect} evals")
            else:
                print("  Will ship when count stabilises (no new evals for 2 checks)")
            poll_modal(args.modal, args.poll, args.expect, local_dir)
        else:
            print(f"Downloading from Modal: {args.modal}")
            modal_download(args.modal, local_dir)
        # Use downloaded dir as the path for the rest of the pipeline
        args.path = str(local_dir)

    # 2. Discover
    evals = discover_evals(args.path, glob_pattern=args.glob, since=args.since)
    if not evals:
        print(f"ERROR: No .eval files found at {args.path}", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(evals)} eval(s)")

    # 3. Sweep name
    p = Path(args.path)
    stem = p.stem if p.is_file() else p.name
    sweep_name = args.sweep_name or f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M')}"

    # 4. Parse all evals
    runs = []
    for ev in evals:
        print(f"  Parsing: {ev.name}")
        runs.append(parse_eval(ev))
    print(f"Parsed {len(runs)} run(s)")

    # 5. Stage files with canonical names (disambiguate collisions with _2, _3, ...)
    staging_dir = Path(tempfile.mkdtemp(prefix="ship_eval_"))
    used_names = {}
    for run in runs:
        src = Path(run["path"])
        name = run["canonical_name"]
        if name in used_names:
            used_names[name] += 1
            stem, ext = name.rsplit(".", 1)
            name = f"{stem}_{used_names[name]}.{ext}"
        else:
            used_names[name] = 1
        run["staged_name"] = name
        dst = staging_dir / name
        os.symlink(src.resolve(), dst)
    print(f"Staged in: {staging_dir}")

    # 6. Upload to Drive
    folder_link = ""
    if not args.dry_run and not args.skip_drive:
        staged_files = sorted(staging_dir.glob("*.eval"))
        cmd = [
            sys.executable, str(GDRIVE_SCRIPT),
            *[str(f) for f in staged_files],
            "--parent-folder-id", cfg["drive_parent_folder_id"],
            "--subfolder-name", sweep_name,
        ]
        output = run_cmd(cmd)
        print(output)
        # Extract folder link from output
        for line in output.splitlines():
            if "Link:" in line and "drive.google.com" in line:
                folder_link = line.split("Link:")[-1].strip()
                break

    # 7. Generate report
    report_dir = Path(tempfile.mkdtemp(prefix="ship_report_"))
    runs_json = json.dumps(runs)
    cmd = [
        sys.executable, str(REPORT_SCRIPT),
        "--output-dir", str(report_dir),
        "--folder-link", folder_link,
    ]
    output = run_cmd(cmd, stdin_data=runs_json)

    # Parse report output paths
    report_files = {}
    for line in output.strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            report_files[key] = val
    print(f"Report generated in: {report_dir}")

    # 8. Send email
    if not args.dry_run:
        subject = build_subject(sweep_name, runs)
        cmd = [
            sys.executable, str(EMAIL_SCRIPT),
            "--to", cfg["recipient_email"],
            "--subject", subject,
            "--html", report_files["html"],
            "--label", cfg["gmail_label"],
        ]
        for cid in ("bar_main", "bar_side", "training_curves"):
            if cid in report_files:
                cmd.extend(["--image", f"{cid}:{report_files[cid]}"])
        output = run_cmd(cmd)
        print(output)

    # 9. Summary
    print("\n--- Summary ---")
    print(f"Sweep: {sweep_name}")
    print(f"Runs:  {len(runs)}")
    if folder_link:
        print(f"Drive: {folder_link}")
    for run in runs:
        main_pct = f"{run['main_score']*100:.0f}%" if run['main_score'] is not None else "CRASH"
        print(f"  {run['canonical_name']}  main={main_pct}  mode={run['mode']}")


if __name__ == "__main__":
    main()
