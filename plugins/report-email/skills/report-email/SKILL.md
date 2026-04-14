---
name: report-email
description: Use this skill when the user asks to "send a report email", "email me results", "send results with charts", "email a summary", or any request to send an HTML-formatted email with embedded charts or images. Also trigger when sending experiment results, analysis summaries, or any rich report via email.
version: 1.0.0
---

# Report Email — HTML emails with inline charts

Send HTML emails with charts/images rendered inline (not as attachments) via Gmail API.

## How it works

1. **Generate charts** with matplotlib, save as PNG to `/tmp/`
2. **Write HTML** to `/tmp/report.html`, referencing charts with `<img src="cid:CHART_NAME" />`
3. **Send** with the helper script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/send_report_email.py \
  --to RECIPIENT \
  --subject "Subject Line" \
  --html /tmp/report.html \
  --image chart_name:/tmp/chart_name.png \
  --image another_chart:/tmp/another.png
```

## Key rules

- **CID references**: In the HTML, use `<img src="cid:NAME" />`. The `NAME` must match the CID in `--image NAME:/path/to/file.png`.
- **No base64 data URIs**: Gmail strips `data:image/png;base64,...` from emails. Always use CID references.
- **No SVG**: Email clients strip SVG. Use matplotlib PNG.
- **Multiple images**: Repeat `--image CID:PATH` for each image.
- **Recipient**: Use `titusbuckworth@gmail.com` unless the user specifies otherwise.
- **Chart style**: Use `fig.patch.set_facecolor('#ffffff')` for white background. Save at `dpi=150` for clarity.

## Workflow

### Step 1: Generate charts

```python
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(10, 5))
# ... plot data ...
plt.savefig('/tmp/my_chart.png', dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
```

### Step 2: Write HTML

Write the full HTML email body to a file. Reference charts with CID:

```html
<img src="cid:my_chart" style="width:100%;max-width:800px;" />
```

### Step 3: Send

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/send_report_email.py \
  --to titusbuckworth@gmail.com \
  --subject "Report Title" \
  --html /tmp/report.html \
  --image my_chart:/tmp/my_chart.png \
  --label Experiments
```

The `--label` flag applies a Gmail label after sending (requires `gmail.modify` scope). Use `Experiments` for experiment reports. Omit for general emails.

## Prerequisites

- OAuth token at `~/.config/google-docs-mcp/token.json` with `gmail.send` scope
- Gmail API enabled in Google Cloud project `house-splitting`
- Python packages: `google-api-python-client`, `google-auth`
- If token missing or expired, run: `python3 ~/pyg/admin/google_reauth.py`

## HTML email tips

- Use inline CSS (email clients strip `<style>` blocks sometimes — inline is safest for critical styles)
- Tables render more reliably than flexbox/grid across email clients
- Keep total email size under 10MB (Gmail limit)
- Test with Gmail web client — it's the most restrictive
