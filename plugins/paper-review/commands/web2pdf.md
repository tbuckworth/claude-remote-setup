---
description: Convert a web article to clean PDF and send to reMarkable
argument-hint: "<url> [--rm-folder /folder] [--no-images | --layout]"
allowed-tools: [Bash, AskUserQuestion]
model: claude-sonnet-4-6
---

# Web to PDF for reMarkable

Convert a web article to a clean, readable PDF (no headers, footers, or ads) and send it to the reMarkable via rmapi.

## Constants

- **Script**: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/web2pdf.py`
- **Default font size**: 14pt
- **Default reMarkable folder**: `/`

## Workflow

1. Parse `{{argument}}` for the URL and any flags.

2. If no URL provided, ask the user for one.

3. If the user specified a reMarkable folder, use `--rm-folder`. Otherwise ask if they want to send to a specific folder or root.

4. Run the script:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/web2pdf.py "<url>" --rm --rm-folder "<folder>" -o "/tmp/<name>.pdf"
```

Choose a sensible output filename based on the article title. If the user specified `--no-images`, pass that flag too. If the user specified a custom font size, pass `--font-size`.

5. Check the figures. The default mode extracts the article text with Readability, which keeps `<img>` images but drops figures built from HTML or SVG (interactive charts, diagrams, transcript widgets, as on the Anthropic Alignment Science blog). If the page has such figures and the PDF lost them, or the user passed `--layout`, print the live page instead:
```bash
uv run --with requests,beautifulsoup4,readability-lxml,lxml_html_clean,playwright \
  python ${CLAUDE_PLUGIN_ROOT}/scripts/web2pdf.py "<url>" --layout --rm --rm-folder "<folder>" -o "/tmp/<name>.pdf"
```
`--layout` keeps the page's own look (and its site header and footer). It sizes the browser window to the printed A4 column, so figures that the page fits to the window with JavaScript are neither clipped nor split across pages. `--scale` (default 1.35) sets the text size. Don't write a one-off print script for such pages: printing from a wider window clips the figures.

6. Report success: title, page count, and where it was sent on the reMarkable.

## Notes

- The script uses Mozilla Readability to extract article content and headless Chrome to render the PDF. `--layout` skips extraction and prints the live page through Playwright and the installed Chrome.
- If rmapi fails, suggest the user check `rmapi` auth status.
- The user can also pass `--font-size` to override the default 14pt.
