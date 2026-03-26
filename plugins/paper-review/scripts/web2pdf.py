#!/usr/bin/env python3
"""Convert a web article to a clean, tight-margin PDF for reMarkable."""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from readability import Document

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Clean CSS optimized for reMarkable (tight margins, full-width, readable)
CLEAN_CSS = """
@page {
    size: A4;
    margin: 0;  /* zero page margin = no room for Chrome header/footer */
}
body {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 14pt;
    line-height: 1.5;
    color: #000;
    max-width: 100%;
    margin: 0;
    padding: 1.5cm 1.2cm;  /* visual margins via padding instead */
}
h1 { font-size: 18pt; margin: 0 0 0.5em 0; line-height: 1.2; }
h2 { font-size: 14pt; margin: 1.2em 0 0.4em 0; }
h3 { font-size: 12pt; margin: 1em 0 0.3em 0; }
p { margin: 0.5em 0; text-align: justify; }
img { max-width: 100%; height: auto; margin: 0.5em 0; }
figure { margin: 0.5em 0; }
figcaption { font-size: 9pt; color: #444; font-style: italic; }
blockquote {
    border-left: 2pt solid #666;
    margin: 0.5em 0 0.5em 0;
    padding: 0.2em 0 0.2em 0.8em;
    font-style: italic;
}
pre, code {
    font-family: 'Courier New', monospace;
    font-size: 9pt;
    background: #f5f5f5;
    padding: 0.1em 0.3em;
}
pre { padding: 0.5em; overflow-x: auto; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; margin: 0.5em 0; }
th, td { border: 1px solid #ccc; padding: 0.3em 0.5em; font-size: 10pt; }
th { background: #f0f0f0; font-weight: bold; }
a { color: #000; text-decoration: underline; }
ul, ol { margin: 0.5em 0; padding-left: 1.5em; }
li { margin: 0.2em 0; }
.title-block { margin-bottom: 1em; border-bottom: 1px solid #ccc; padding-bottom: 0.5em; }
.title-block .meta { font-size: 9pt; color: #666; margin-top: 0.3em; }
"""


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_article(html: str, url: str) -> tuple[str, str]:
    """Extract article content and title using readability."""
    doc = Document(html, url=url)
    title = doc.title()
    # Strip common " - Site Name" or " | Site Name" suffixes
    title = re.split(r"\s*[|\-–—]\s*(?=[^|\-–—]*$)", title)[0].strip()
    content = doc.summary()
    return title, content


def clean_html(content: str, title: str, url: str, source_html: str, font_size: str = "11pt") -> str:
    """Clean extracted HTML: fix relative URLs, add title block."""
    soup = BeautifulSoup(content, "html.parser")

    # Fix relative image URLs
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and not src.startswith(("http://", "https://", "data:")):
            img["src"] = urljoin(url, src)
        # Remove srcset to avoid issues
        img.attrs.pop("srcset", None)

    # Fix relative link URLs
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href and not href.startswith(("http://", "https://", "mailto:", "#")):
            a["href"] = urljoin(url, href)

    # Try to extract date/author from source
    meta_parts = []
    source_soup = BeautifulSoup(source_html, "html.parser")

    for attr in ["article:published_time", "date", "publishedDate"]:
        tag = source_soup.find("meta", {"property": attr}) or source_soup.find("meta", {"name": attr})
        if tag and tag.get("content"):
            meta_parts.append(tag["content"][:10])
            break

    for attr in ["author", "article:author"]:
        tag = source_soup.find("meta", {"property": attr}) or source_soup.find("meta", {"name": attr})
        if tag and tag.get("content"):
            meta_parts.append(tag["content"])
            break

    domain = urlparse(url).netloc.replace("www.", "")
    meta_parts.append(domain)
    meta_str = " · ".join(meta_parts)

    css = CLEAN_CSS.replace("font-size: 14pt", f"font-size: {font_size}")
    final_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
<div class="title-block">
<h1>{title}</h1>
<div class="meta">{meta_str}</div>
</div>
{soup}
</body>
</html>"""
    return final_html


def to_pdf(html_str: str, output_path: str) -> None:
    """Render HTML to PDF using headless Chrome."""
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False, encoding="utf-8") as f:
        f.write(html_str)
        tmp_html = f.name
    try:
        output_abs = str(Path(output_path).resolve())
        result = subprocess.run(
            [
                CHROME,
                "--headless=new",
                f"--print-to-pdf={output_abs}",
                "--print-to-pdf-no-header",
                tmp_html,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if not Path(output_abs).exists():
            print(f"Chrome PDF failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)
    finally:
        Path(tmp_html).unlink(missing_ok=True)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")


def send_to_remarkable(pdf_path: str, folder: str = "/") -> bool:
    """Upload PDF to reMarkable via rmapi."""
    try:
        if folder != "/":
            subprocess.run(["rmapi", "mkdir", folder], capture_output=True)
        result = subprocess.run(
            ["rmapi", "put", pdf_path, folder],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            print(f"Sent to reMarkable: {folder}")
            return True
        else:
            print(f"rmapi error: {result.stderr.strip()}", file=sys.stderr)
            return False
    except FileNotFoundError:
        print("rmapi not found", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Convert web article to clean PDF")
    parser.add_argument("url", help="URL of the article")
    parser.add_argument("-o", "--output", help="Output PDF path (default: auto-named)")
    parser.add_argument("--rm", action="store_true", help="Send to reMarkable via rmapi")
    parser.add_argument("--rm-folder", default="/", help="reMarkable folder (default: /)")
    parser.add_argument("--no-images", action="store_true", help="Strip images")
    parser.add_argument("--font-size", default="14pt", help="Body font size (default: 14pt)")
    args = parser.parse_args()

    print(f"Fetching: {args.url}")
    raw_html = fetch_page(args.url)

    print("Extracting article content...")
    title, content = extract_article(raw_html, args.url)
    print(f"Title: {title}")

    final_html = clean_html(content, title, args.url, raw_html, font_size=args.font_size)

    if args.no_images:
        soup = BeautifulSoup(final_html, "html.parser")
        for img in soup.find_all("img"):
            img.decompose()
        final_html = str(soup)

    if args.output:
        output_path = args.output
    else:
        output_path = f"{slugify(title)}.pdf"

    print(f"Rendering PDF: {output_path}")
    to_pdf(final_html, output_path)
    print(f"Done: {output_path}")

    if args.rm:
        send_to_remarkable(output_path, args.rm_folder)


if __name__ == "__main__":
    main()
