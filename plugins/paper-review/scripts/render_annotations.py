#!/usr/bin/env python3
"""Render reMarkable annotations (handwriting + highlights) onto a PDF.

Usage:
    python render_annotations.py <paper_dir> [--open] [--output PATH]

Requires: rmscene, PyMuPDF (fitz)

The paper directory should contain:
  - A .pdf file (the original document)
  - A .content file (reMarkable page metadata)
  - A UUID-named directory containing .rm files (stroke data)

The transform from rm coordinates to PDF coordinates is derived by matching
SceneGlyphItemBlock text highlight rectangles against actual PDF text positions.
This avoids relying on undocumented binary viewport fields in the .rm format.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import fitz
from rmscene import read_blocks, SceneLineItemBlock


COLOR_MAP = {
    0: (0, 0, 0),        # black
    1: (0.5, 0.5, 0.5),  # gray
    2: (1, 1, 1),        # white
    3: (1, 1, 0),        # yellow
    4: (0, 0.8, 0),      # green
    5: (1, 0.5, 0.7),    # pink
    6: (0, 0, 1),        # blue
    7: (1, 0, 0),        # red
    8: (0.5, 0.5, 0.5),  # gray-overlap
    9: (1, 0.9, 0),      # highlight yellow
}


def find_files(paper_dir: Path):
    pdfs = list(paper_dir.glob("*.pdf"))
    pdfs = [p for p in pdfs if p.name != "annotated.pdf"]
    if not pdfs:
        sys.exit(f"No PDF found in {paper_dir}")
    pdf_path = pdfs[0]

    content_files = list(paper_dir.glob("*.content"))
    if not content_files:
        sys.exit(f"No .content file found in {paper_dir}")

    rm_dirs = [d for d in paper_dir.iterdir() if d.is_dir() and len(d.name) == 36]
    if not rm_dirs:
        sys.exit(f"No UUID directory with .rm files found in {paper_dir}")

    return pdf_path, content_files[0], rm_dirs[0]


def parse_content(content_path: Path):
    content = json.loads(content_path.read_text())
    if "cPages" in content:
        pages = content["cPages"].get("pages", [])
    elif "pages" in content:
        pages = [{"id": pid} for pid in content["pages"]]
    else:
        sys.exit("Cannot parse page list from .content file")
    return pages


def get_pdf_page_idx(page_info: dict) -> int | None:
    redir = page_info.get("redir", {})
    if isinstance(redir, dict):
        val = redir.get("value", None)
    else:
        val = redir
    if val is None or val == "N/A":
        return None
    return int(val)


def read_rm_blocks(rm_file: Path):
    with open(rm_file, "rb") as f:
        return list(read_blocks(f))


def _solve_affine(pairs):
    n = len(pairs)
    sum_rm = sum(p[0] for p in pairs)
    sum_pdf = sum(p[1] for p in pairs)
    sum_rm2 = sum(p[0] ** 2 for p in pairs)
    sum_rm_pdf = sum(p[0] * p[1] for p in pairs)
    denom = n * sum_rm2 - sum_rm ** 2
    if abs(denom) < 1e-10:
        return None
    scale = (n * sum_rm_pdf - sum_rm * sum_pdf) / denom
    offset = (sum_pdf - scale * sum_rm) / n
    return scale, offset


def _collect_glyph_pairs(blocks, pdf_page):
    """Collect (rm_coord, pdf_coord) pairs from glyph highlights on one page.

    Uses the glyph 'start' field to locate the exact character offset in the
    page text, then gets coordinates via PyMuPDF search_for with the glyph text.
    Falls back to search_for if start-based lookup fails.
    """
    pairs_x, pairs_y = [], []

    for block in blocks:
        if type(block).__name__ != "SceneGlyphItemBlock":
            continue
        item = block.item
        if not hasattr(item, "value") or item.value is None:
            continue
        glyph = item.value
        text = getattr(glyph, "text", "")
        rects = getattr(glyph, "rectangles", [])
        if not text or not rects or len(text) < 5:
            continue

        search_text = text.rstrip(".,:;)")
        pdf_matches = pdf_page.search_for(search_text)
        if not pdf_matches:
            continue

        if len(pdf_matches) == 1:
            pdf_rect = pdf_matches[0]
        else:
            # Multiple matches — pick the one whose width ratio best matches
            rm_w = rects[0].w
            best = None
            best_ratio_err = float("inf")
            for m in pdf_matches:
                if rm_w > 0:
                    ratio_err = abs(m.width / rm_w - pdf_matches[0].width / rm_w)
                else:
                    ratio_err = 0
                if best is None or ratio_err < best_ratio_err:
                    best = m
                    best_ratio_err = ratio_err
            pdf_rect = best

        rm_rect = rects[0]
        pairs_x.append((rm_rect.x, pdf_rect.x0))
        pairs_y.append((rm_rect.y, pdf_rect.y0))

    return pairs_x, pairs_y


def derive_global_transform(all_page_data, doc):
    """Derive a single global transform from glyph matches across all pages.

    Collects pairs from all pages, fits RANSAC-style by checking consistency.
    All PDF-backed pages share the same coordinate transform on reMarkable.
    """
    all_pairs_x, all_pairs_y = [], []

    for pdf_idx, blocks in all_page_data:
        if pdf_idx >= len(doc):
            continue
        page = doc[pdf_idx]
        px, py = _collect_glyph_pairs(blocks, page)
        all_pairs_x.extend(px)
        all_pairs_y.extend(py)

    if len(all_pairs_x) < 2:
        return None

    result_x = _solve_affine(all_pairs_x)
    result_y = _solve_affine(all_pairs_y)
    if result_x is None or result_y is None:
        return None

    sx, ox = result_x
    sy, oy = result_y

    # Filter outliers: remove pairs with residual > 10 pts and refit
    def filter_and_refit(pairs, scale, offset):
        filtered = [(rm, pdf) for rm, pdf in pairs if abs(scale * rm + offset - pdf) < 10]
        if len(filtered) < 2:
            return scale, offset
        result = _solve_affine(filtered)
        return result if result else (scale, offset)

    sx, ox = filter_and_refit(all_pairs_x, sx, ox)
    sy, oy = filter_and_refit(all_pairs_y, sy, oy)

    # Sanity check: sx and sy should be similar (uniform scaling)
    if abs(sx - sy) / max(abs(sx), abs(sy)) > 0.1:
        # Scales diverge too much — use only the axis with more data spread
        rm_x_range = max(p[0] for p in all_pairs_x) - min(p[0] for p in all_pairs_x) if all_pairs_x else 0
        rm_y_range = max(p[0] for p in all_pairs_y) - min(p[0] for p in all_pairs_y) if all_pairs_y else 0
        if rm_y_range > rm_x_range:
            sx = sy
            ox = sum(pdf - sx * rm for rm, pdf in all_pairs_x) / len(all_pairs_x) if all_pairs_x else ox
        else:
            sy = sx
            oy = sum(pdf - sy * rm for rm, pdf in all_pairs_y) / len(all_pairs_y) if all_pairs_y else oy

    return {"sx": sx, "ox": ox, "sy": sy, "oy": oy}


def get_color(obj, attr="color"):
    color_val = getattr(obj, attr, None)
    if hasattr(color_val, "value"):
        return COLOR_MAP.get(color_val.value, (1, 0, 0))
    elif isinstance(color_val, int):
        return COLOR_MAP.get(color_val, (1, 0, 0))
    return (1, 0, 0)


def render_strokes(blocks, page, transform):
    sx, ox = transform["sx"], transform["ox"]
    sy, oy = transform["sy"], transform["oy"]
    pw, ph = page.rect.width, page.rect.height

    for block in blocks:
        if not isinstance(block, SceneLineItemBlock):
            continue
        item = block.item
        if not hasattr(item, "value") or item.value is None:
            continue
        line = item.value
        if not hasattr(line, "points") or not line.points:
            continue

        c = get_color(line)
        tool = getattr(line, "tool", None)
        tool_val = tool.value if hasattr(tool, "value") else (tool if isinstance(tool, int) else 0)
        is_highlighter = tool_val in [5, 18]
        opacity = 0.35 if is_highlighter else 1.0

        thickness = getattr(line, "thickness_scale", 1.0)
        if hasattr(thickness, "value"):
            thickness = thickness.value
        if is_highlighter:
            width = max(2.0, float(thickness) * sx * 3.0)
        else:
            width = max(0.3, float(thickness) * sx * 1.2)

        points = line.points
        for i in range(len(points) - 1):
            p1, p2 = points[i], points[i + 1]
            x1 = sx * float(p1.x) + ox
            y1 = sy * float(p1.y) + oy
            x2 = sx * float(p2.x) + ox
            y2 = sy * float(p2.y) + oy

            if max(x1, x2) < -50 or min(x1, x2) > pw + 50:
                continue
            if max(y1, y2) < -50 or min(y1, y2) > ph + 50:
                continue

            shape = page.new_shape()
            shape.draw_line(fitz.Point(x1, y1), fitz.Point(x2, y2))
            shape.finish(color=c, width=width, stroke_opacity=opacity)
            shape.commit()


def render_highlights(blocks, page, transform):
    sx, ox = transform["sx"], transform["ox"]
    sy, oy = transform["sy"], transform["oy"]

    for block in blocks:
        if type(block).__name__ != "SceneGlyphItemBlock":
            continue
        item = block.item
        if not hasattr(item, "value") or item.value is None:
            continue
        glyph = item.value
        rects = getattr(glyph, "rectangles", [])
        if not rects:
            continue

        rgba = getattr(glyph, "color_rgba", None)
        if rgba:
            r, g, b = rgba[0] / 255, rgba[1] / 255, rgba[2] / 255
        else:
            r, g, b = 1.0, 0.93, 0.46

        for rect in rects:
            rx = sx * rect.x + ox
            ry = sy * rect.y + oy
            rw = sx * rect.w
            rh = sy * rect.h
            pdf_rect = fitz.Rect(rx, ry, rx + rw, ry + rh)
            annot = page.add_highlight_annot(pdf_rect)
            annot.set_colors(stroke=(r, g, b))
            annot.set_opacity(0.4)
            annot.update()


def render_annotated_pdf(paper_dir: Path, output_path: Path | None = None) -> Path:
    pdf_path, content_path, rm_dir = find_files(paper_dir)
    pages = parse_content(content_path)
    doc = fitz.open(pdf_path)

    if output_path is None:
        output_path = paper_dir / "annotated.pdf"

    # First pass: load all blocks and collect page data for global transform
    page_data = []  # (pdf_idx, blocks, page_info)
    all_glyph_page_data = []  # (pdf_idx, blocks) for transform derivation

    for page_info in pages:
        uuid = page_info["id"]
        rm_file = rm_dir / f"{uuid}.rm"
        if not rm_file.exists():
            continue

        pdf_idx = get_pdf_page_idx(page_info)
        if pdf_idx is None or pdf_idx >= len(doc):
            continue

        blocks = read_rm_blocks(rm_file)
        has_content = any(
            (isinstance(b, SceneLineItemBlock) and hasattr(b.item, "value") and b.item.value is not None)
            or type(b).__name__ == "SceneGlyphItemBlock"
            for b in blocks
        )
        if not has_content:
            continue

        page_data.append((pdf_idx, blocks))
        all_glyph_page_data.append((pdf_idx, blocks))

    # Derive a single global transform from all glyph matches
    transform = derive_global_transform(all_glyph_page_data, doc)
    if transform is None:
        pw, ph = doc[0].rect.width, doc[0].rect.height
        scale = ph / 1872.0
        transform = {"sx": scale, "ox": pw / 2.0, "sy": scale, "oy": 0.0}

    # Second pass: render with the global transform
    for pdf_idx, blocks in page_data:
        page = doc[pdf_idx]
        render_strokes(blocks, page, transform)
        render_highlights(blocks, page, transform)

    doc.save(str(output_path))
    doc.close()
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Render reMarkable annotations onto PDF")
    parser.add_argument("paper_dir", type=Path, help="Paper directory with PDF + rm files")
    parser.add_argument("--output", "-o", type=Path, help="Output PDF path")
    parser.add_argument("--open", action="store_true", help="Open in Preview after rendering")
    args = parser.parse_args()

    out = render_annotated_pdf(args.paper_dir, args.output)
    print(out)

    if args.open:
        subprocess.run(["open", str(out)])


if __name__ == "__main__":
    main()
