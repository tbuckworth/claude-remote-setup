---
name: yulia-gdrive-upload
description: Use this skill when the user asks to "upload to Drive", "save to Google Drive", "upload eval to Drive", "put this on Drive", "share via Drive", or any request to upload files (especially .eval files) to Google Drive.
version: 2.0.0
---

# Google Drive Upload

For eval sweeps, use `/ship-eval <path>` which handles upload + email in one command.

## Direct upload (one-off)

```bash
# Upload into an existing folder
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/upload_to_gdrive.py FILE [FILE ...] --folder FOLDER_ID

# Auto-create a subfolder and upload into it
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/upload_to_gdrive.py FILE [FILE ...] \
  --parent-folder-id PARENT_ID --subfolder-name "sweep_20260415"

# Single file with renamed name in Drive
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/upload_to_gdrive.py FILE --folder FOLDER_ID --name "new_name.eval"
```

## Key rules
- `.eval` files are ZIP archives -- upload as-is, don't extract.
- The script prints Drive links after upload -- always show these to the user.

## Prerequisites
- OAuth token at `~/.config/google-docs-mcp/token.json` with `drive.file` scope
- Google Drive API enabled in the Google Cloud project
- Python packages: `google-api-python-client`, `google-auth`
