#!/usr/bin/env python3
"""Mechanical pre-processing: download, extract, render papers from reMarkable.

This script handles the non-AI parts of pre-processing. It downloads new papers
from reMarkable, extracts annotations, renders annotated PDFs, and extracts PDF
text. It outputs a list of new paper slugs for Claude to analyze.

Usage:
    uv run --python 3.12 --with rmscene,PyMuPDF,Pillow \
        preprocess_papers.py [--data-dir DIR] [--plugin-dir DIR] [--dry-run]

Called by preprocess_cron.sh, which then invokes `claude -p` for analysis.
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path.home() / "pyg" / "paper-review"
DEFAULT_PLUGIN_DIR = Path.home() / "pyg" / "claude-remote-setup" / "plugins" / "paper-review"
REMARKABLE_FOLDERS = ["To Quiz", "Apollo Interview Prep/Done"]


def rmapi_cmd(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["rmapi"] + args,
        capture_output=True, text=True, timeout=60
    )


def verify_rmapi_auth() -> bool:
    result = rmapi_cmd(["ls", "/"])
    if result.returncode != 0 or not result.stdout.strip():
        log.error("rmapi auth failed: %s", result.stderr.strip())
        return False
    return True


def list_remarkable_papers() -> list[dict]:
    papers = []
    for folder in REMARKABLE_FOLDERS:
        result = rmapi_cmd(["ls", folder])
        if result.returncode != 0:
            log.warning("Failed to list %s: %s", folder, result.stderr.strip())
            continue
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("[d]") or line.startswith("[f]"):
                name = line[3:].strip()
                papers.append({"name": name, "folder": folder})
    return papers


def generate_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:50]


def is_already_done(db: dict, slug: str) -> bool:
    for paper in db.get("papers", []):
        if paper.get("id") == slug:
            if paper.get("preprocessed") or paper.get("status") == "reviewed":
                return True
    return False


def download_paper(name: str, folder: str, paper_dir: Path) -> bool:
    paper_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["rmapi", "get", f"{folder}/{name}"],
        capture_output=True, text=True, timeout=120,
        cwd=str(paper_dir),
    )
    if result.returncode != 0:
        log.error("Download failed for %s: %s", name, result.stderr.strip())
        return False

    archives = list(paper_dir.glob("*.zip")) + list(paper_dir.glob("*.rmdoc"))
    for archive in archives:
        subprocess.run(
            ["unzip", "-o", str(archive), "-d", str(paper_dir)],
            capture_output=True, timeout=60,
        )
    return True


def run_extract_annotations(paper_dir: Path, plugin_dir: Path) -> bool:
    script = plugin_dir / "scripts" / "extract_annotations.py"
    result = subprocess.run(
        ["uv", "run", "--python", "3.12",
         "--with", "rmscene,PyMuPDF,Pillow",
         str(script), str(paper_dir)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning("Annotation extraction failed: %s", result.stderr[:200])
        return False
    (paper_dir / "annotations.json").write_text(result.stdout)
    return True


def run_render_annotations(paper_dir: Path, plugin_dir: Path):
    script = plugin_dir / "scripts" / "render_annotations.py"
    subprocess.run(
        ["uv", "run", "--python", "3.12",
         "--with", "rmscene,PyMuPDF",
         str(script), str(paper_dir)],
        capture_output=True, timeout=120,
    )


def extract_pdf_text(paper_dir: Path) -> bool:
    import fitz
    pdfs = [p for p in paper_dir.glob("*.pdf") if p.name != "annotated.pdf"]
    if not pdfs:
        return False
    doc = fitz.open(str(pdfs[0]))
    pages = {"pages": [doc[i].get_text() for i in range(len(doc))], "total": len(doc)}
    doc.close()
    (paper_dir / "pdf_text.json").write_text(json.dumps(pages, indent=2))
    return True


def main():
    parser = argparse.ArgumentParser(description="Pre-process papers from reMarkable (mechanical steps)")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--plugin-dir", type=Path, default=DEFAULT_PLUGIN_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = args.data_dir
    plugin_dir = args.plugin_dir
    db_path = data_dir / "database.json"

    if not db_path.exists():
        log.error("database.json not found at %s", db_path)
        sys.exit(1)

    if not verify_rmapi_auth():
        sys.exit(2)

    db = json.loads(db_path.read_text())
    papers = list_remarkable_papers()
    log.info("Found %d papers in reMarkable folders", len(papers))

    new_papers = []
    for paper in papers:
        slug = generate_slug(paper["name"])
        if is_already_done(db, slug):
            continue
        new_papers.append({**paper, "slug": slug})

    log.info("%d new papers to process", len(new_papers))

    if args.dry_run:
        for p in new_papers:
            print(json.dumps(p))
        return

    if not new_papers:
        print("[]")
        return

    results = []
    for paper in new_papers:
        slug = paper["slug"]
        name = paper["name"]
        folder = paper["folder"]
        paper_dir = data_dir / "papers" / slug

        log.info("Processing: %s -> %s", name, slug)

        if not download_paper(name, folder, paper_dir):
            continue

        run_extract_annotations(paper_dir, plugin_dir)
        run_render_annotations(paper_dir, plugin_dir)
        extract_pdf_text(paper_dir)

        results.append({
            "slug": slug,
            "name": name,
            "folder": folder,
            "paper_dir": str(paper_dir),
        })
        log.info("Ready for analysis: %s", slug)

    print(json.dumps(results))


if __name__ == "__main__":
    main()
