"""Extract highlights and ink annotations from a reMarkable document directory.

Usage: uv run --python 3.12 --with rmscene,PyMuPDF,Pillow,pyobjc-framework-Vision extract_annotations.py <doc-dir>

The doc-dir should contain:
  - A .pdf file (the original document)
  - A .content JSON file (page mapping)
  - A subdirectory with .rm files (annotation layers)

Outputs JSON to stdout (pages are 1-indexed). Saves ink cluster PNGs to doc-dir.
"""

import json
import sys
from pathlib import Path

from rmscene import read_blocks, SceneGlyphItemBlock, SceneLineItemBlock
from rmscene.scene_items import PenColor, Pen

# --- Color and tool mappings ---

PEN_COLOR_MAP = {
    PenColor.BLACK.value: "black",
    PenColor.GRAY.value: "gray",
    PenColor.WHITE.value: "white",
    PenColor.YELLOW.value: "yellow",
    PenColor.GREEN.value: "green",
    PenColor.PINK.value: "pink",
    PenColor.BLUE.value: "blue",
    PenColor.RED.value: "red",
    PenColor.GRAY_OVERLAP.value: "gray",
    PenColor.HIGHLIGHT.value: "yellow",
    PenColor.GREEN_2.value: "green",
    PenColor.CYAN.value: "cyan",
    PenColor.MAGENTA.value: "magenta",
    PenColor.YELLOW_2.value: "yellow",
}

PEN_COLOR_RGB = {
    PenColor.BLACK.value: (0, 0, 0),
    PenColor.GRAY.value: (125, 125, 125),
    PenColor.WHITE.value: (200, 200, 200),
    PenColor.YELLOW.value: (251, 205, 50),
    PenColor.GREEN.value: (0, 160, 60),
    PenColor.PINK.value: (220, 50, 120),
    PenColor.BLUE.value: (0, 100, 220),
    PenColor.RED.value: (220, 40, 40),
    PenColor.GRAY_OVERLAP.value: (125, 125, 125),
    PenColor.HIGHLIGHT.value: (251, 205, 50),
    PenColor.GREEN_2.value: (0, 160, 60),
    PenColor.CYAN.value: (0, 180, 210),
    PenColor.MAGENTA.value: (180, 40, 180),
    PenColor.YELLOW_2.value: (251, 205, 50),
}

PEN_TOOL_MAP = {
    Pen.BALLPOINT_1.value: "Ballpoint",
    Pen.BALLPOINT_2.value: "Ballpoint",
    Pen.CALIGRAPHY.value: "Calligraphy",
    Pen.ERASER.value: "Eraser",
    Pen.ERASER_AREA.value: "Eraser",
    Pen.FINELINER_1.value: "Fineliner",
    Pen.FINELINER_2.value: "Fineliner",
    Pen.HIGHLIGHTER_1.value: "Highlighter",
    Pen.HIGHLIGHTER_2.value: "Highlighter",
    Pen.MARKER_1.value: "Marker",
    Pen.MARKER_2.value: "Marker",
    Pen.MECHANICAL_PENCIL_1.value: "Mechanical Pencil",
    Pen.MECHANICAL_PENCIL_2.value: "Mechanical Pencil",
    Pen.PAINTBRUSH_1.value: "Paintbrush",
    Pen.PAINTBRUSH_2.value: "Paintbrush",
    Pen.PENCIL_1.value: "Pencil",
    Pen.PENCIL_2.value: "Pencil",
    Pen.SHADER.value: "Shader",
}

ERASER_TOOLS = {Pen.ERASER.value, Pen.ERASER_AREA.value}


# --- File discovery and content parsing ---

def find_files(doc_dir: Path):
    pdf_file = None
    content_file = None
    rm_dir = None

    for f in doc_dir.iterdir():
        if f.suffix == ".pdf" and f.name != "annotated.pdf":
            pdf_file = f
        elif f.suffix == ".content":
            content_file = f
        elif f.is_dir() and len(f.name) == 36:
            rm_dir = f

    if rm_dir is None:
        rm_files = list(doc_dir.rglob("*.rm"))
        if rm_files:
            rm_dir = rm_files[0].parent

    return pdf_file, content_file, rm_dir


def parse_content(content_path: Path):
    content = json.loads(content_path.read_text())
    if "cPages" in content:
        return content["cPages"].get("pages", [])
    if "pages" in content:
        return [{"id": pid} for pid in content["pages"]]
    return []


def get_pdf_page_idx(page_info: dict) -> int | None:
    redir = page_info.get("redir", {})
    if isinstance(redir, dict):
        val = redir.get("value", None)
    else:
        val = redir
    if val is None or val == "N/A":
        return None
    return int(val)


# --- Coordinate transform (inlined from render_annotations.py) ---

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
    pairs_x, pairs_y = [], []

    for block in blocks:
        if not isinstance(block, SceneGlyphItemBlock):
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

    def filter_and_refit(pairs, scale, offset):
        filtered = [(rm, pdf) for rm, pdf in pairs if abs(scale * rm + offset - pdf) < 10]
        if len(filtered) < 2:
            return scale, offset
        result = _solve_affine(filtered)
        return result if result else (scale, offset)

    sx, ox = filter_and_refit(all_pairs_x, sx, ox)
    sy, oy = filter_and_refit(all_pairs_y, sy, oy)

    if abs(sx - sy) / max(abs(sx), abs(sy)) > 0.1:
        rm_x_range = max(p[0] for p in all_pairs_x) - min(p[0] for p in all_pairs_x) if all_pairs_x else 0
        rm_y_range = max(p[0] for p in all_pairs_y) - min(p[0] for p in all_pairs_y) if all_pairs_y else 0
        if rm_y_range > rm_x_range:
            sx = sy
            ox = sum(pdf - sx * rm for rm, pdf in all_pairs_x) / len(all_pairs_x) if all_pairs_x else ox
        else:
            sy = sx
            oy = sum(pdf - sy * rm for rm, pdf in all_pairs_y) / len(all_pairs_y) if all_pairs_y else oy

    return {"sx": sx, "ox": ox, "sy": sy, "oy": oy}


def rm_bbox_to_pdf(bbox, transform):
    sx, ox = transform["sx"], transform["ox"]
    sy, oy = transform["sy"], transform["oy"]
    x0, y0, x1, y1 = bbox
    return [sx * x0 + ox, sy * y0 + oy, sx * x1 + ox, sy * y1 + oy]


# --- Annotation extraction ---

def extract_annotations_from_blocks(blocks, page_num):
    highlights = []
    strokes = []

    for block in blocks:
        if isinstance(block, SceneGlyphItemBlock):
            value = block.item.value
            if value is None or block.item.deleted_length > 0:
                continue
            color_val = value.color.value if hasattr(value.color, "value") else int(value.color)
            rects = getattr(value, "rectangles", [])
            rm_rects = [{"x": r.x, "y": r.y, "w": r.w, "h": r.h} for r in rects]
            highlights.append({
                "page": page_num,
                "text": value.text,
                "color": color_val,
                "color_name": PEN_COLOR_MAP.get(color_val, "unknown"),
                "start": value.start,
                "length": value.length,
                "rm_rects": rm_rects,
            })
        elif isinstance(block, SceneLineItemBlock):
            value = block.item.value
            if value is None or block.item.deleted_length > 0:
                continue
            points = value.points
            if not points:
                continue
            xs = [p.x for p in points]
            ys = [p.y for p in points]
            tool_val = value.tool.value if hasattr(value.tool, "value") else int(value.tool)
            color_val = value.color.value if hasattr(value.color, "value") else int(value.color)
            strokes.append({
                "page": page_num,
                "bbox": [min(xs), min(ys), max(xs), max(ys)],
                "tool": tool_val,
                "tool_name": PEN_TOOL_MAP.get(tool_val, "Unknown"),
                "color": color_val,
                "color_name": PEN_COLOR_MAP.get(color_val, "unknown"),
                "thickness_scale": value.thickness_scale,
                "points": [(p.x, p.y, p.width, p.pressure) for p in points],
            })

    return highlights, strokes


# --- Union-Find for clustering ---

class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def bbox_gap(a, b):
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def cluster_strokes(strokes, gap_threshold=60.0):
    draw_strokes = [s for s in strokes if s["tool"] not in ERASER_TOOLS]
    if not draw_strokes:
        return []

    by_page = {}
    for s in draw_strokes:
        by_page.setdefault(s["page"], []).append(s)

    clusters = []
    for page_num, page_strokes in sorted(by_page.items()):
        n = len(page_strokes)
        uf = UnionFind(n)

        for i in range(n):
            for j in range(i + 1, n):
                if bbox_gap(page_strokes[i]["bbox"], page_strokes[j]["bbox"]) < gap_threshold:
                    uf.union(i, j)

        groups = {}
        for i in range(n):
            root = uf.find(i)
            groups.setdefault(root, []).append(page_strokes[i])

        for cluster_id, group in enumerate(groups.values()):
            total_points = sum(len(s["points"]) for s in group)
            if total_points < 5:
                continue

            x0 = min(s["bbox"][0] for s in group)
            y0 = min(s["bbox"][1] for s in group)
            x1 = max(s["bbox"][2] for s in group)
            y1 = max(s["bbox"][3] for s in group)

            is_full_page = (x1 - x0) > 1200 and (y1 - y0) > 1600

            colors = sorted(set(s["color_name"] for s in group))
            tools = sorted(set(s["tool_name"] for s in group))

            clusters.append({
                "page": page_num,
                "cluster_id": cluster_id,
                "bbox": [x0, y0, x1, y1],
                "num_strokes": len(group),
                "total_points": total_points,
                "type": "full-page" if is_full_page else "note",
                "stroke_colors": colors,
                "tools_used": tools,
                "strokes": group,
            })

    return clusters


# --- Rendering ---

def render_cluster_white(cluster, doc_dir: Path, padding=30, scale=2.0):
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = cluster["bbox"]
    w = max(10, int((x1 - x0) * scale + 2 * padding))
    h = max(10, int((y1 - y0) * scale + 2 * padding))

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    for stroke in cluster["strokes"]:
        pts = stroke["points"]
        if len(pts) < 2:
            continue
        color = PEN_COLOR_RGB.get(stroke["color"], (0, 0, 0))
        line_width = max(1, int(stroke["thickness_scale"] * scale))

        coords = [
            (int((p[0] - x0) * scale + padding), int((p[1] - y0) * scale + padding))
            for p in pts
        ]
        draw.line(coords, fill=color, width=line_width)

    page = cluster["page"]
    cid = cluster["cluster_id"]
    name = f"ink_cluster_p{page}_{cid}_white.png"
    path = doc_dir / name
    img.save(str(path))
    return str(path)


def render_cluster_context(cluster, pdf_file: Path, doc_dir: Path, transform):
    import fitz
    from PIL import Image, ImageDraw

    page_num = cluster["page"]
    x0, y0, x1, y1 = cluster["bbox"]
    sx, ox = transform["sx"], transform["ox"]
    sy, oy = transform["sy"], transform["oy"]

    doc = fitz.open(str(pdf_file))
    if page_num >= len(doc):
        doc.close()
        return None

    page = doc[page_num]
    page_rect = page.rect

    pdf_x0 = sx * x0 + ox
    pdf_y0 = sy * y0 + oy
    pdf_x1 = sx * x1 + ox
    pdf_y1 = sy * y1 + oy

    margin_pts = 20
    clip_x0 = max(0, pdf_x0 - margin_pts)
    clip_y0 = max(0, pdf_y0 - margin_pts)
    clip_x1 = min(page_rect.width, pdf_x1 + margin_pts)
    clip_y1 = min(page_rect.height, pdf_y1 + margin_pts)

    clip = fitz.Rect(clip_x0, clip_y0, clip_x1, clip_y1)
    if clip.is_empty:
        doc.close()
        return None

    zoom = 2
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    bg = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    left_extend = 0
    if pdf_x0 - margin_pts < 0:
        left_extend_pts = abs(pdf_x0 - margin_pts)
        left_extend = int(left_extend_pts * zoom)
        extended = Image.new("RGB", (bg.width + left_extend, bg.height), (230, 230, 230))
        extended.paste(bg, (left_extend, 0))
        bg = extended

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for stroke in cluster["strokes"]:
        pts = stroke["points"]
        if len(pts) < 2:
            continue
        rgb = PEN_COLOR_RGB.get(stroke["color"], (0, 0, 0))
        alpha = 140 if stroke["tool_name"] == "Highlighter" else 220
        color = (*rgb, alpha)
        line_width = max(1, int(stroke["thickness_scale"] * sx * zoom))

        coords = []
        for p in pts:
            pdf_px = sx * p[0] + ox
            pdf_py = sy * p[1] + oy
            px = (pdf_px - clip_x0) * zoom + left_extend
            py = (pdf_py - clip_y0) * zoom
            coords.append((int(px), int(py)))

        draw.line(coords, fill=color, width=line_width)

    bg_rgba = bg.convert("RGBA")
    composite = Image.alpha_composite(bg_rgba, overlay)
    result = composite.convert("RGB")

    cid = cluster["cluster_id"]
    name = f"ink_cluster_p{page_num}_{cid}_context.png"
    path = doc_dir / name
    result.save(str(path))
    doc.close()
    return str(path)


def extract_surrounding_text(pdf_page, bbox, transform, expansion_pts=30):
    sx, ox = transform["sx"], transform["ox"]
    sy, oy = transform["sy"], transform["oy"]
    x0, y0, x1, y1 = bbox
    page_rect = pdf_page.rect

    import fitz
    clip = fitz.Rect(
        max(0, sx * x0 + ox - expansion_pts),
        max(0, sy * y0 + oy - expansion_pts),
        min(page_rect.width, sx * x1 + ox + expansion_pts),
        min(page_rect.height, sy * y1 + oy + expansion_pts),
    )

    text = pdf_page.get_text(clip=clip).strip()

    if len(text) > 500:
        text = text[:500] + "..."
    return text


def transcribe_image(image_path: str) -> str:
    try:
        import Vision
        from Quartz import (
            CGImageSourceCreateWithURL,
            CGImageSourceCreateImageAtIndex,
        )
        from Foundation import NSURL
    except ImportError:
        return ""

    try:
        url = NSURL.fileURLWithPath_(image_path)
        source = CGImageSourceCreateWithURL(url, None)
        if source is None:
            return ""
        cg_image = CGImageSourceCreateImageAtIndex(source, 0, None)
        if cg_image is None:
            return ""

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(0)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            cg_image, None
        )
        success = handler.performRequests_error_([request], None)
        if not success[0]:
            return ""

        results = request.results()
        if not results:
            return ""

        lines = []
        for obs in results:
            candidate = obs.topCandidates_(1)
            if candidate:
                lines.append(candidate[0].string())
        return "\n".join(lines)
    except Exception:
        return ""


def extract_pdf_metadata(pdf_file: Path):
    import fitz

    doc = fitz.open(str(pdf_file))
    metadata = doc.metadata or {}

    title = metadata.get("title", "")
    author = metadata.get("author", "")
    total_pages = len(doc)

    links = []
    for page_num in range(total_pages):
        page = doc[page_num]
        for link in page.get_links():
            if link.get("uri"):
                links.append({
                    "page": page_num + 1,
                    "uri": link["uri"],
                })

    doc.close()
    return title, author, total_pages, links


# --- Spatial grouping ---

def find_nearby_highlights(note_pdf_bbox, page_highlights, threshold=100.0):
    scored = []
    for h in page_highlights:
        pdf_bbox = h.get("pdf_bbox")
        if pdf_bbox is None:
            continue
        gap = bbox_gap(note_pdf_bbox, pdf_bbox)
        scored.append((gap, h))

    scored.sort(key=lambda x: x[0])

    nearby = []
    for gap, h in scored:
        if gap <= threshold:
            nearby.append({
                "text": h["text"],
                "color_name": h["color_name"],
                "distance_pts": round(gap, 1),
            })

    # Always include the closest highlight even if beyond threshold
    if not nearby and scored:
        gap, h = scored[0]
        nearby.append({
            "text": h["text"],
            "color_name": h["color_name"],
            "distance_pts": round(gap, 1),
            "beyond_threshold": True,
        })

    return nearby


# --- Main ---

def main():
    if len(sys.argv) < 2:
        print("Usage: extract_annotations.py <doc-dir>", file=sys.stderr)
        sys.exit(1)

    doc_dir = Path(sys.argv[1])
    if not doc_dir.is_dir():
        print(f"Error: {doc_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    pdf_file, content_file, rm_dir = find_files(doc_dir)

    # Phase 1: Parse content and load blocks per page
    page_blocks = []  # (pdf_idx, blocks)

    if content_file and rm_dir:
        pages = parse_content(content_file)
        for page_info in pages:
            uuid = page_info.get("id", "")
            if not uuid:
                continue
            rm_file = rm_dir / f"{uuid}.rm"
            if not rm_file.exists():
                continue
            pdf_idx = get_pdf_page_idx(page_info)
            if pdf_idx is None:
                continue
            with open(rm_file, "rb") as f:
                blocks = list(read_blocks(f))
            page_blocks.append((pdf_idx, blocks))
    elif rm_dir:
        for i, rm_file in enumerate(sorted(rm_dir.glob("*.rm"))):
            with open(rm_file, "rb") as f:
                blocks = list(read_blocks(f))
            page_blocks.append((i, blocks))

    # Phase 2: Derive global transform
    transform = None
    if pdf_file:
        import fitz
        doc = fitz.open(str(pdf_file))
        transform = derive_global_transform(page_blocks, doc)
        if transform is None:
            pw, ph = doc[0].rect.width, doc[0].rect.height
            scale = ph / 1872.0
            transform = {"sx": scale, "ox": pw / 2.0, "sy": scale, "oy": 0.0}
        doc.close()
    else:
        transform = {"sx": 1.0, "ox": 0.0, "sy": 1.0, "oy": 0.0}

    # Phase 3: Extract highlights and strokes
    all_highlights = []
    all_strokes = []
    for pdf_idx, blocks in page_blocks:
        highlights, strokes = extract_annotations_from_blocks(blocks, pdf_idx)
        all_highlights.extend(highlights)
        all_strokes.extend(strokes)

    # Phase 4: Convert highlight rm_rects to PDF coords and compute pdf_bbox
    for h in all_highlights:
        sx, ox = transform["sx"], transform["ox"]
        sy, oy = transform["sy"], transform["oy"]
        pdf_rects = []
        for r in h.get("rm_rects", []):
            pdf_rects.append({
                "x": round(sx * r["x"] + ox, 1),
                "y": round(sy * r["y"] + oy, 1),
                "w": round(sx * r["w"], 1),
                "h": round(sy * r["h"], 1),
            })
        h["pdf_rects"] = pdf_rects
        if pdf_rects:
            h["pdf_bbox"] = [
                min(r["x"] for r in pdf_rects),
                min(r["y"] for r in pdf_rects),
                max(r["x"] + r["w"] for r in pdf_rects),
                max(r["y"] + r["h"] for r in pdf_rects),
            ]

    # Phase 5: Cluster strokes and build handwritten notes
    clusters = cluster_strokes(all_strokes)

    highlights_by_page = {}
    for h in all_highlights:
        highlights_by_page.setdefault(h["page"], []).append(h)

    handwritten_notes = []
    if pdf_file:
        import fitz
        doc = fitz.open(str(pdf_file))

    for cluster in clusters:
        if cluster["type"] == "full-page":
            continue

        white_path = render_cluster_white(cluster, doc_dir)
        context_path = None
        surrounding_text = ""
        transcription = transcribe_image(white_path) if white_path else ""

        if pdf_file:
            context_path = render_cluster_context(cluster, pdf_file, doc_dir, transform)
            page_num = cluster["page"]
            if page_num < len(doc):
                surrounding_text = extract_surrounding_text(
                    doc[page_num], cluster["bbox"], transform
                )

        pdf_bbox = rm_bbox_to_pdf(cluster["bbox"], transform)

        page_hl = highlights_by_page.get(cluster["page"], [])
        nearby = find_nearby_highlights(pdf_bbox, page_hl)

        note = {
            "page": cluster["page"] + 1,
            "cluster_id": cluster["cluster_id"],
            "bbox": cluster["bbox"],
            "pdf_bbox": [round(v, 1) for v in pdf_bbox],
            "num_strokes": cluster["num_strokes"],
            "ink_on_white_path": white_path,
            "ink_on_pdf_path": context_path,
            "surrounding_text": surrounding_text,
            "transcription": transcription,
            "stroke_colors": cluster["stroke_colors"],
            "tools_used": cluster["tools_used"],
            "nearby_highlights": nearby,
        }
        handwritten_notes.append(note)

    if pdf_file:
        doc.close()

    # Phase 6: Extract PDF metadata
    title, author, total_pages, links = "", "", 0, []
    if pdf_file:
        title, author, total_pages, links = extract_pdf_metadata(pdf_file)

    # Phase 7: Clean up and 1-index pages in highlights
    for h in all_highlights:
        h["page"] += 1
        h.pop("rm_rects", None)

    all_highlights.sort(key=lambda h: (h["page"], h.get("start", 0) or 0))

    result = {
        "title": title,
        "author": author,
        "total_pages": total_pages,
        "highlights": all_highlights,
        "handwritten_notes": handwritten_notes,
        "links": links,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
