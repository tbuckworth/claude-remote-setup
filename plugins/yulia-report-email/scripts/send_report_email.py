#!/usr/bin/env python3
"""Send an HTML email with inline embedded images via Gmail API.

Usage:
    python3 send_report_email.py --to EMAIL --subject SUBJECT --html FILE [--image CID:PATH ...] [--label NAME]

Example:
    python3 send_report_email.py \
        --to user@example.com \
        --subject "Experiment Results" \
        --html /tmp/report.html \
        --image chart1:/tmp/chart1.png \
        --image chart2:/tmp/chart2.png \
        --label Experiments

The HTML file should reference images with <img src="cid:chart1" />.
Images are embedded inline using MIME Content-ID headers, so they render
directly in the email body (not as attachments).

Requires:
    - google-api-python-client, google-auth (pip install)
    - OAuth token at ~/.config/google-docs-mcp/token.json with gmail.send + gmail.modify scopes
    - Gmail API enabled in the Google Cloud project
"""

import argparse
import base64
import json
import sys
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def get_gmail_service():
    """Build Gmail API service from the shared OAuth token."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = Path.home() / ".config/google-docs-mcp/token.json"
    if not token_path.exists():
        print(f"ERROR: OAuth token not found at {token_path}", file=sys.stderr)
        print("Run: python3 ~/pyg/admin/google_reauth.py", file=sys.stderr)
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
    return build("gmail", "v1", credentials=creds)


def build_message(to, subject, html_path, images):
    """Build a MIMEMultipart("related") message with inline images."""
    html_content = Path(html_path).read_text()

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["To"] = to
    msg["From"] = to  # gmail.send uses authenticated user as sender

    msg.attach(MIMEText(html_content, "html"))

    for cid, img_path in images:
        img_data = Path(img_path).read_bytes()

        # Detect subtype from extension
        ext = Path(img_path).suffix.lower()
        subtype = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "webp": "webp"}.get(
            ext.lstrip("."), "png"
        )

        img_part = MIMEImage(img_data, _subtype=subtype)
        img_part.add_header("Content-ID", f"<{cid}>")
        img_part.add_header("Content-Disposition", "inline", filename=f"{cid}.{ext.lstrip('.')}")
        msg.attach(img_part)

    return msg


def resolve_label_id(service, label_name):
    """Find a Gmail label ID by name. Returns None if not found."""
    labels = service.users().labels().list(userId="me").execute()
    for label in labels.get("labels", []):
        if label["name"] == label_name:
            return label["id"]
    return None


def send(service, message, label_name=None):
    """Send the MIME message via Gmail API, optionally applying a label."""
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    msg_id = result["id"]

    if label_name:
        label_id = resolve_label_id(service, label_name)
        if label_id:
            service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"addLabelIds": [label_id]},
            ).execute()
            print(f"Labeled: {label_name}", file=sys.stderr)
        else:
            print(f"WARNING: Label '{label_name}' not found in Gmail — skipping", file=sys.stderr)

    return result


def main():
    parser = argparse.ArgumentParser(description="Send HTML email with inline images via Gmail API")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--html", required=True, help="Path to HTML file for the email body")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        metavar="CID:PATH",
        help="Inline image as CID:PATH (e.g., chart:/tmp/chart.png). "
        "Reference in HTML as <img src=\"cid:chart\" />. Can be repeated.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Gmail label name to apply after sending (e.g., Experiments). "
        "Requires gmail.modify scope.",
    )
    args = parser.parse_args()

    # Parse image args
    images = []
    for img_spec in args.image:
        if ":" not in img_spec:
            print(f"ERROR: --image must be CID:PATH, got: {img_spec}", file=sys.stderr)
            sys.exit(1)
        cid, path = img_spec.split(":", 1)
        if not Path(path).exists():
            print(f"ERROR: Image file not found: {path}", file=sys.stderr)
            sys.exit(1)
        images.append((cid, path))

    # Validate HTML file
    if not Path(args.html).exists():
        print(f"ERROR: HTML file not found: {args.html}", file=sys.stderr)
        sys.exit(1)

    # Verify CID references in HTML
    html_content = Path(args.html).read_text()
    for cid, _ in images:
        if f'cid:{cid}' not in html_content:
            print(f"WARNING: CID '{cid}' not referenced in HTML (expected <img src=\"cid:{cid}\" />)", file=sys.stderr)

    # Send
    service = get_gmail_service()
    message = build_message(args.to, args.subject, args.html, images)
    result = send(service, message, label_name=args.label)
    print(f"Sent: {result['id']}")


if __name__ == "__main__":
    main()
