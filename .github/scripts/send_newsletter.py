#!/usr/bin/env python3
"""
send_newsletter.py
==================
Sends new BS Mail posts to Buttondown subscribers via the Buttondown API.
Called automatically by the GitHub Actions workflow after a post is published.

Usage:
    python3 send_newsletter.py "posts/my-post.md posts/another.md"

Environment variables (set as GitHub Secrets):
    BUTTONDOWN_API_KEY  — from buttondown.com/settings/api (required)
    SITE_URL            — your site URL, e.g. https://uc.unrouted.org
                          used to build the "read on site" link (optional)

Frontmatter flags:
    newsletter: false   — add this to skip sending a specific post
                          useful for corrections or test posts

The email is sent as markdown — Buttondown renders it natively.
Subject line = post title.
Body = post content + a "read on site" footer link.

Buttondown API docs: https://api.buttondown.email/v1/schema
"""

import sys
import os
import re
import json
import urllib.request
import urllib.error
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────

API_KEY  = os.environ.get('BUTTONDOWN_API_KEY', '')
SITE_URL = os.environ.get('SITE_URL', '').rstrip('/')
API_BASE = 'https://api.buttondown.email/v1'

# ── Helpers ─────────────────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)


def parse_frontmatter(text):
    """Same parser as patch_brainstew.py — kept local to avoid imports."""
    meta = {}
    body = text

    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if fm_match:
        fm_block = fm_match.group(1)
        body     = text[fm_match.end():]
        for line in fm_block.splitlines():
            if ':' in line:
                k, _, v = line.partition(':')
                meta[k.strip().lower()] = v.strip()

    if 'title' not in meta:
        h1 = re.search(r'^#\s+(.+)', body, re.MULTILINE)
        if h1:
            meta['title'] = re.sub(r'[*_`]', '', h1.group(1)).strip()

    today = datetime.now()
    meta.setdefault('title',      'New Post from BS Mail')
    meta.setdefault('date',       f"{today.month:02d}/{today.day:02d}/{str(today.year)[2:]}")
    meta.setdefault('from',       'uc')
    meta.setdefault('newsletter', 'true')

    return meta, body.strip()


def slug_from_file(path):
    base = os.path.basename(path)
    slug = base.replace('.md', '').replace(' ', '-').lower()
    return re.sub(r'[^a-z0-9-]', '', slug)


def build_email_body(meta, body, md_path):
    """
    Build the email body in markdown.
    Buttondown renders markdown natively in emails.
    """
    slug     = slug_from_file(md_path)
    site_url = SITE_URL or 'https://uc.unrouted.org'

    # Link to the live post on the site
    post_url = f"{site_url}/brainstew.html"

    header = f"*{meta['date']} — from {meta['from']} @ Unrouted Controls*\n\n---\n\n"

    footer = (
        f"\n\n---\n\n"
        f"*Read this in the BS Mail inbox → [{site_url}/brainstew.html]({post_url})*\n\n"
        f"*You're receiving this because you subscribed to BS Mail "
        f"at [uc.unrouted.org]({site_url}). "
        f"[Unsubscribe]({{{{ unsubscribe_url }}}})*"
    )

    return header + body + footer


def send_email(subject, body_md):
    """
    POST to Buttondown /emails endpoint.
    status=draft sends to you only for preview.
    status=about_to_send queues it for immediate send to all subscribers.
    """
    payload = json.dumps({
        'subject':  subject,
        'body':     body_md,
        'status':   'about_to_send',   # change to 'draft' to preview first
    }).encode('utf-8')

    req = urllib.request.Request(
        f'{API_BASE}/emails',
        data=payload,
        headers={
            'Authorization': f'Token {API_KEY}',
            'Content-Type':  'application/json',
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            log(f"  Email queued — Buttondown ID: {data.get('id', 'unknown')}")
            log(f"  Status: {data.get('status', 'unknown')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        log(f"  ERROR {e.code}: {error_body}")
        return False
    except Exception as e:
        log(f"  ERROR: {e}")
        return False


# ── Per-file processor ──────────────────────────────────────────────────────

def process_file(md_path):
    log(f"\n{'─'*50}")
    log(f"  File: {md_path}")

    if not os.path.exists(md_path):
        log(f"  WARNING: file not found — skipping")
        return

    with open(md_path, 'r', encoding='utf-8') as fh:
        text = fh.read()

    meta, body = parse_frontmatter(text)

    log(f"  Title:      {meta['title']}")
    log(f"  Newsletter: {meta['newsletter']}")

    # Respect newsletter: false flag in frontmatter
    if meta['newsletter'].lower() in ('false', 'no', '0'):
        log(f"  SKIP: newsletter: false in frontmatter")
        return

    subject  = meta['title']
    body_md  = build_email_body(meta, body, md_path)

    log(f"  Sending to Buttondown subscribers...")
    log(f"  Subject: {subject}")

    success = send_email(subject, body_md)
    if success:
        log(f"  Newsletter sent successfully")
    else:
        log(f"  Newsletter failed — check error above")
        # We exit 0 intentionally — a newsletter failure should not
        # fail the entire workflow or block the site publish.
        # The post is already live. The newsletter is best-effort.


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    if not API_KEY:
        log("BUTTONDOWN_API_KEY not set — skipping newsletter entirely")
        sys.exit(0)

    if len(sys.argv) < 2 or not sys.argv[1].strip():
        log("No files provided — nothing to send")
        sys.exit(0)

    md_files = [f.strip() for f in re.split(r'[\s\n]+', sys.argv[1].strip()) if f.strip()]
    md_files = [f for f in md_files if f.endswith('.md')]

    if not md_files:
        log("No .md files found — nothing to send")
        sys.exit(0)

    log(f"Buttondown newsletter sender")
    log(f"Processing {len(md_files)} file(s)")
    log(f"Site URL: {SITE_URL or '(not set, using default)'}")

    for md_path in md_files:
        process_file(md_path)

    log(f"\n{'─'*50}")
    log("Newsletter step complete")


if __name__ == '__main__':
    main()
