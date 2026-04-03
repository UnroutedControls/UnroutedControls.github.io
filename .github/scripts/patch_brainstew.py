#!/usr/bin/env python3
"""
patch_brainstew.py
==================
Called by the GitHub Actions workflow whenever a .md file is pushed to posts/.

Usage:
    python3 patch_brainstew.py "posts/my-post.md posts/another.md"

What it does:
  1. Reads each markdown file
  2. Parses the frontmatter (title, date, from)
  3. Generates an inbox-row <div> and a <script type="text/markdown"> block
  4. Inserts them into brainstew.html at the two marker comments
  5. Updates the status bar message count
  6. Writes the file back in place

Markdown file format
--------------------
Every post needs a tiny YAML frontmatter block at the top:

    ---
    title: My Cool Post Title
    date: 04/02/26
    from: uc
    ---

    # My Cool Post Title

    Your markdown content here...

`from` is optional (defaults to "uc").
`date` is optional (defaults to today MM/DD/YY).
The first # heading is used as the display title if `title` is missing.
"""

import sys
import os
import re
from datetime import datetime
from html import escape

# ── Paths ──────────────────────────────────────────────────────────────
BRAINSTEW = "brainstew.html"

# Markers that must already exist in brainstew.html
ROW_MARKER   = "<!-- ADD POSTS HERE:"      # inbox rows injected after this line
BLOCK_MARKER = "<!-- add more markdown posts here"  # script blocks injected before this line

# ── Helpers ────────────────────────────────────────────────────────────

def today_str():
    d = datetime.now()
    return f"{d.month:02d}/{d.day:02d}/{str(d.year)[2:]}"


def parse_frontmatter(text):
    """
    Returns (meta_dict, body_text).
    meta_dict keys: title, date, from
    """
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

    # Fallback: pull title from first # heading
    if 'title' not in meta:
        h1 = re.search(r'^#\s+(.+)', body, re.MULTILINE)
        if h1:
            meta['title'] = re.sub(r'[*_`]', '', h1.group(1)).strip()

    meta.setdefault('title', 'Untitled Post')
    meta.setdefault('date',  today_str())
    meta.setdefault('from',  'uc')

    return meta, body.strip()


def slug_from_file(path):
    """Turn posts/my-cool-post.md → my-cool-post"""
    base = os.path.basename(path)
    return re.sub(r'[^a-z0-9-]', '', base.replace('.md', '').replace(' ', '-').lower())


def make_post_id(slug, existing_html):
    """Ensure the post ID is unique — append -2, -3 etc. if needed."""
    candidate = f"post-{slug}"
    if candidate not in existing_html:
        return candidate
    i = 2
    while f"{candidate}-{i}" in existing_html:
        i += 1
    return f"{candidate}-{i}"


def build_inbox_row(post_id, meta):
    title_esc = escape(meta['title'])
    from_esc  = escape(meta['from'])
    date_esc  = escape(meta['date'])
    return (
        f'          <div class="inbox-item unread" data-post-id="{post_id}">\n'
        f'            <div>&#x1F4E7;</div>\n'
        f'            <div class="dot-cell">&#x25CF;</div>\n'
        f'            <div>{title_esc}</div>\n'
        f'            <div>{from_esc}</div>\n'
        f'            <div>{date_esc}</div>\n'
        f'          </div>'
    )


def build_script_block(post_id, meta, body):
    title_esc = escape(meta['title'], quote=True)
    date_esc  = escape(meta['date'],  quote=True)
    from_esc  = escape(meta['from'],  quote=True)
    # body goes raw inside the script block — no escaping needed
    # closing </script> must be broken up to avoid early termination
    safe_body = body.replace('</script>', '<\\/script>')
    return (
        f'<script type="text/markdown" id="{post_id}"'
        f' data-title="{title_esc}"'
        f' data-date="{date_esc}"'
        f' data-from="{from_esc}">\n'
        f'{safe_body}\n'
        f'</script>'
    )


def count_messages(html):
    """Count inbox-item rows to update the status bar."""
    return len(re.findall(r'class="inbox-item', html))


def patch_html(html, inbox_row, script_block):
    """
    Insert inbox_row right after ROW_MARKER line.
    Insert script_block right before BLOCK_MARKER line.
    Newest post goes to the TOP of the inbox.
    """
    lines = html.splitlines(keepends=True)
    row_idx   = None
    block_idx = None

    for i, line in enumerate(lines):
        if ROW_MARKER in line and row_idx is None:
            row_idx = i
        if BLOCK_MARKER in line and block_idx is None:
            block_idx = i

    if row_idx is None:
        raise ValueError(
            f"Could not find ROW_MARKER '{ROW_MARKER}' in brainstew.html.\n"
            "Make sure the comment '<!-- ADD POSTS HERE:' exists in your inbox-rows div."
        )
    if block_idx is None:
        raise ValueError(
            f"Could not find BLOCK_MARKER '{BLOCK_MARKER}' in brainstew.html.\n"
            "Make sure the comment '<!-- add more markdown posts here' exists near the bottom."
        )

    # Insert inbox row AFTER the marker line
    lines.insert(row_idx + 1, inbox_row + '\n\n')

    # block_idx shifted by 1 because we just inserted a line above it
    if block_idx > row_idx:
        block_idx += 1

    # Insert script block BEFORE the marker line (i.e. at block_idx position)
    lines.insert(block_idx, script_block + '\n\n')

    return ''.join(lines)


def update_status_bar(html):
    """Update the '1 message(s), 1 unread' status panel text."""
    count = count_messages(html)
    new_text = f"{count} message(s)"
    # Replace whatever is in status-count span
    html = re.sub(
        r'(<div class="status-panel" id="status-count">)[^<]*(</div>)',
        rf'\g<1>{new_text}\g<2>',
        html
    )
    return html


# ── Main ───────────────────────────────────────────────────────────────

def process_file(md_path, html):
    """Process a single markdown file. Returns updated html."""
    print(f"  Processing: {md_path}")

    if not os.path.exists(md_path):
        print(f"  WARNING: {md_path} not found — skipping")
        return html

    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    meta, body = parse_frontmatter(text)
    slug       = slug_from_file(md_path)
    post_id    = make_post_id(slug, html)

    print(f"    Title:   {meta['title']}")
    print(f"    Date:    {meta['date']}")
    print(f"    Post ID: {post_id}")

    # Check for duplicate — if this post already exists, skip
    if f'id="{post_id}"' in html and f'data-post-id="{post_id}"' in html:
        print(f"    SKIP: post '{post_id}' already exists in brainstew.html")
        return html

    inbox_row    = build_inbox_row(post_id, meta)
    script_block = build_script_block(post_id, meta, body)

    html = patch_html(html, inbox_row, script_block)
    html = update_status_bar(html)

    print(f"    Injected successfully.")
    return html


def main():
    # Files passed as a single space/newline-separated string from the workflow
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("No markdown files provided — nothing to do.")
        sys.exit(0)

    md_files = [f.strip() for f in re.split(r'[\s\n]+', sys.argv[1].strip()) if f.strip()]
    md_files = [f for f in md_files if f.endswith('.md')]

    if not md_files:
        print("No .md files found in args — nothing to do.")
        sys.exit(0)

    if not os.path.exists(BRAINSTEW):
        print(f"ERROR: {BRAINSTEW} not found. Make sure the script runs from repo root.")
        sys.exit(1)

    with open(BRAINSTEW, 'r', encoding='utf-8') as f:
        html = f.read()

    print(f"Loaded {BRAINSTEW} ({len(html)} bytes)")
    print(f"Processing {len(md_files)} file(s):")

    for md_path in md_files:
        html = process_file(md_path, html)

    with open(BRAINSTEW, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nDone. {BRAINSTEW} updated.")


if __name__ == '__main__':
    main()
