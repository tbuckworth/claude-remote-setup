---
description: Convert a web article to clean PDF and send to reMarkable
argument-hint: "<url> [--rm-folder /folder] [--no-images]"
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

5. Report success: title, page count, and where it was sent on the reMarkable.

## Notes

- The script uses Mozilla Readability to extract article content and headless Chrome to render the PDF.
- If rmapi fails, suggest the user check `rmapi` auth status.
- The user can also pass `--font-size` to override the default 14pt.
