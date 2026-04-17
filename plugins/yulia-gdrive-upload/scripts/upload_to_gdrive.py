#!/usr/bin/env python3
"""Upload files to Google Drive via the Drive API.

Usage:
    python3 upload_to_gdrive.py FILE [FILE ...] [--folder FOLDER_ID] [--name NAME]
    python3 upload_to_gdrive.py FILE [FILE ...] --parent-folder-id ID --subfolder-name NAME

Example:
    python3 upload_to_gdrive.py logs/eval_result.eval --folder 1abc123 --name "bfcl_attack_2026-04-15.eval"
    python3 upload_to_gdrive.py *.eval --parent-folder-id 1abc123 --subfolder-name "sweep_20260415"

Requires:
    - google-api-python-client, google-auth (pip install)
    - OAuth token at ~/.config/google-docs-mcp/token.json with drive.file scope
    - Google Drive API enabled in the Google Cloud project
"""

import argparse
import json
import mimetypes
import sys
from pathlib import Path


def get_drive_service():
    """Build Drive API service from the shared OAuth token."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = Path.home() / ".config/google-docs-mcp/token.json"
    if not token_path.exists():
        print(f"ERROR: OAuth token not found at {token_path}", file=sys.stderr)
        sys.exit(1)

    token_data = json.loads(token_path.read_text())
    creds = Credentials(
        token=None,
        refresh_token=token_data["refresh_token"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def create_subfolder(service, parent_folder_id, subfolder_name):
    """Create a subfolder under the given parent. Returns folder metadata."""
    folder_metadata = {
        "name": subfolder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id],
    }
    result = service.files().create(
        body=folder_metadata,
        fields="id, name, webViewLink",
    ).execute()
    return result


def upload_file(service, file_path, name=None, folder_id=None):
    """Upload a single file to Google Drive. Returns file metadata."""
    from googleapiclient.http import MediaFileUpload

    file_path = Path(file_path)
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    upload_name = name or file_path.name
    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    file_metadata = {"name": upload_name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
    result = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, webViewLink",
    ).execute()

    return result


def main():
    parser = argparse.ArgumentParser(description="Upload files to Google Drive")
    parser.add_argument("files", nargs="+", help="File(s) to upload")
    parser.add_argument(
        "--folder",
        default=None,
        help="Google Drive folder ID to upload into. "
        "Find it in the folder's URL: drive.google.com/drive/folders/FOLDER_ID",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Override the filename in Drive (only applies when uploading a single file).",
    )
    parser.add_argument(
        "--parent-folder-id",
        default=None,
        help="Parent folder ID. Used with --subfolder-name to auto-create a subfolder.",
    )
    parser.add_argument(
        "--subfolder-name",
        default=None,
        help="Name for the auto-created subfolder (requires --parent-folder-id).",
    )
    args = parser.parse_args()

    if args.name and len(args.files) > 1:
        print("ERROR: --name can only be used with a single file", file=sys.stderr)
        sys.exit(1)

    if bool(args.parent_folder_id) != bool(args.subfolder_name):
        print("ERROR: --parent-folder-id and --subfolder-name must be used together", file=sys.stderr)
        sys.exit(1)

    if args.parent_folder_id and args.folder:
        print("ERROR: Use --folder OR --parent-folder-id/--subfolder-name, not both", file=sys.stderr)
        sys.exit(1)

    service = get_drive_service()

    folder_id = args.folder
    if args.parent_folder_id:
        subfolder = create_subfolder(service, args.parent_folder_id, args.subfolder_name)
        folder_id = subfolder["id"]
        print(f"Created subfolder: {args.subfolder_name}")
        print(f"  ID: {subfolder['id']}")
        print(f"  Link: {subfolder.get('webViewLink', 'N/A')}")

    for file_path in args.files:
        name = args.name if args.name else None
        result = upload_file(service, file_path, name=name, folder_id=folder_id)
        print(f"Uploaded: {result['name']}")
        print(f"  ID: {result['id']}")
        print(f"  Link: {result.get('webViewLink', 'N/A')}")


if __name__ == "__main__":
    main()
