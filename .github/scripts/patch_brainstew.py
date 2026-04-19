#!/usr/bin/env python3
"""
patch_brainstew.py
==================
Injects markdown posts into brainstew.html.

Usage:
    # Normal mode — inject new posts
    python3 patch_brainstew.py "posts/my-post.md posts/another.md"

    # Dry run — print what would change, exit without modifying anything
    python3 patch_brainstew.py "posts/my-post.md" --dry-run

    # Update mode — re-push a post with update: true in its frontmatter
    # to replace its title/content in brainstew.html
    python3 patch_brainstew.py "posts/my-post.md"
    (set "update: true" in the post's frontmatter)

Frontmatter format
------------------
    ---
    title: My Post Title
    date: 04/05/26
    from: uc
    update: false        # set to true to replace an existing post
    ---

Post ID
-------
Derived from the filename, not the title.
    posts/my-cool-post.md  ->  post-my-cool-post

Renames create duplicates. Don't rename after first publish.
To rename safely: delete the old entry from brainstew.html first.

Marker comments required in brainstew.html
------------------------------------------
    <!-- ADD POSTS HERE: -->          (inside #inbox-rows div)
    <!-- add more markdown posts here -->   (near bottom before </body>)
"""

import sys
import os
import re
import argparse
from datetime import datetime
from html import escape

# ── Configuration ───────────────────────────────────────────────────────────

BRAINSTEW    = "brainstew.html"
ROW_MARKER   = "<!-- ADD POSTS HERE:"
BLOCK_MARKER = "<!-- add more markdown posts here"

# ── Helpers ─────────────────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)


def today_str():
    d = datetime.now()
    return f"{d.month:02d}/{d.day:02d}/{str(d.year)[2:]}"


def parse_frontmatter(text):
    """
    Returns (meta_dict, body_text).
    Recognized keys: title, date, from, update
    All keys are optional with safe defaults.
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

    # Fallback title from first # heading
    if 'title' not in meta:
        h1 = re.search(r'^#\s+(.+)', body, re.MULTILINE)
        if h1:
            meta['title'] = re.sub(r'[*_`]', '', h1.group(1)).strip()

    meta.setdefault('title',  'Untitled Post')
    meta.setdefault('date',   today_str())
    meta.setdefault('from',   'uc')
    meta.setdefault('update', 'false')

    # Sanitize all string values — no unescaped HTML in attributes
    for k in ('title', 'date', 'from'):
        meta[k] = meta[k].strip()

    return meta, body.strip()


def slug_from_file(path):
    """posts/My Cool Post.md  ->  my-cool-post"""
    base = os.path.basename(path)
    slug = base.replace('.md', '').replace(' ', '-').lower()
    return re.sub(r'[^a-z0-9-]', '', slug)


def make_post_id(slug, existing_html):
    """Return a unique post ID, appending -2, -3 etc. if needed."""
    candidate = f"post-{slug}"
    if candidate not in existing_html:
        return candidate
    i = 2
    while f"{candidate}-{i}" in existing_html:
        i += 1
    return f"{candidate}-{i}"


def post_exists(post_id, html):
    return (f'id="{post_id}"' in html and
            f'data-post-id="{post_id}"' in html)


def build_inbox_row(post_id, meta):
    t = escape(meta['title'])
    f = escape(meta['from'])
    d = escape(meta['date'])
    return (
        f'          <div class="inbox-item unread" data-post-id="{post_id}">\n'
        f'            <div>&#x1F4E7;</div>\n'
        f'            <div class="dot-cell">&#x25CF;</div>\n'
        f'            <div>{t}</div>\n'
        f'            <div>{f}</div>\n'
        f'            <div>{d}</div>\n'
        f'          </div>'
    )


def build_script_block(post_id, meta, body):
    t = escape(meta['title'], quote=True)
    d = escape(meta['date'],  quote=True)
    f = escape(meta['from'],  quote=True)
    # Escape any </script> in the body to prevent early tag termination
    safe_body = body.replace('</script>', '<\\/script>')
    return (
        f'<script type="text/markdown" id="{post_id}"'
        f' data-title="{t}"'
        f' data-date="{d}"'
        f' data-from="{f}">\n'
        f'{safe_body}\n'
        f'</script>'
    )


def inject_post(html, inbox_row, script_block):
    """
    Insert inbox_row directly after ROW_MARKER.
    Insert script_block directly before BLOCK_MARKER.
    Newest post ends up at the top of the inbox.
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
            f"ROW_MARKER not found: '{ROW_MARKER}'\n"
            f"Add this comment inside your #inbox-rows div in brainstew.html"
        )
    if block_idx is None:
        raise ValueError(
            f"BLOCK_MARKER not found: '{BLOCK_MARKER}'\n"
            f"Add this comment before </body> in brainstew.html"
        )

    lines.insert(row_idx + 1, inbox_row + '\n\n')
    if block_idx > row_idx:
        block_idx += 1
    lines.insert(block_idx, script_block + '\n\n')

    return ''.join(lines)


def update_post(html, post_id, meta, body):
    """
    Replace the title in the existing inbox row and replace
    the entire script block content for an existing post.
    Used when frontmatter contains update: true.
    """
    t = escape(meta['title'], quote=True)
    d = escape(meta['date'],  quote=True)
    f_val = escape(meta['from'], quote=True)

    # Update data-title attribute on the script block
    html = re.sub(
        rf'(<script[^>]*id="{re.escape(post_id)}"[^>]*data-title=")[^"]*(")',
        rf'\g<1>{t}\g<2>',
        html
    )

    # Update the visible title text in the inbox row
    # Row structure: <div>📧</div><div class="dot-cell">...</div><div>TITLE</div>
    html = re.sub(
        rf'(data-post-id="{re.escape(post_id)}"[^>]*>.*?<div class="dot-cell">.*?</div>\s*<div>)[^<]*(</div>)',
        rf'\g<1>{escape(meta["title"])}\g<2>',
        html,
        flags=re.DOTALL
    )

    # Replace the script block content
    safe_body = body.replace('</script>', '<\\/script>')
    html = re.sub(
        rf'(<script[^>]*id="{re.escape(post_id)}"[^>]*>).*?(</script>)',
        rf'\g<1>\n{safe_body}\n\g<2>',
        html,
        flags=re.DOTALL
    )

    return html


def update_status_bar(html):
    count = len(re.findall(r'class="inbox-item', html))
    return re.sub(
        r'(<div class="status-panel" id="status-count">)[^<]*(</div>)',
        rf'\g<1>{count} message(s)\g<2>',
        html
    )


def diff_summary(original, modified):
    """Print a brief summary of what changed."""
    orig_lines = set(original.splitlines())
    new_lines  = set(modified.splitlines())
    added   = [l for l in new_lines  - orig_lines if l.strip()]
    removed = [l for l in orig_lines - new_lines  if l.strip()]
    log(f"  + {len(added)} lines added")
    log(f"  - {len(removed)} lines removed")


# ── Per-file processor ──────────────────────────────────────────────────────

def process_file(md_path, html, dry_run=False):
    log(f"\n{'─'*50}")
    log(f"  File:    {md_path}")

    if not os.path.exists(md_path):
        log(f"  WARNING: file not found — skipping")
        return html

    with open(md_path, 'r', encoding='utf-8') as fh:
        text = fh.read()

    meta, body = parse_frontmatter(text)
    slug        = slug_from_file(md_path)
    post_id     = f"post-{slug}"
    is_update   = meta['update'].lower() in ('true', 'yes', '1')

    log(f"  Title:   {meta['title']}")
    log(f"  Date:    {meta['date']}")
    log(f"  From:    {meta['from']}")
    log(f"  Post ID: {post_id}")
    log(f"  Update:  {is_update}")

    if post_exists(post_id, html):
        if is_update:
            log(f"  Mode: UPDATE existing post")
            if dry_run:
                log(f"  [DRY RUN] would update post '{post_id}'")
                return html
            html = update_post(html, post_id, meta, body)
            log(f"  Updated successfully")
        else:
            log(f"  SKIP: post '{post_id}' already exists.")
            log(f"  To update it, add 'update: true' to the frontmatter.")
    else:
        log(f"  Mode: INSERT new post")
        if dry_run:
            log(f"  [DRY RUN] would insert post '{post_id}'")
            return html
        inbox_row    = build_inbox_row(post_id, meta)
        script_block = build_script_block(post_id, meta, body)
        html         = inject_post(html, inbox_row, script_block)
        html         = update_status_bar(html)
        log(f"  Inserted successfully")

    return html


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Patch brainstew.html with markdown posts')
    parser.add_argument('files', help='Space/newline-separated list of .md file paths')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would change without modifying brainstew.html')
    args = parser.parse_args()

    if not args.files.strip():
        log("No files provided — nothing to do")
        sys.exit(0)

    md_files = [f.strip() for f in re.split(r'[\s\n]+', args.files.strip()) if f.strip()]
    md_files = [f for f in md_files if f.endswith('.md')]

    if not md_files:
        log("No .md files in args — nothing to do")
        sys.exit(0)

    if not os.path.exists(BRAINSTEW):
        log(f"ERROR: {BRAINSTEW} not found. Run from repo root.")
        sys.exit(1)

    with open(BRAINSTEW, 'r', encoding='utf-8') as fh:
        original_html = fh.read()

    log(f"Loaded {BRAINSTEW} ({len(original_html)} bytes)")
    log(f"Processing {len(md_files)} file(s): {md_files}")

    if args.dry_run:
        log("\n[DRY RUN MODE — no files will be written]\n")

    html = original_html
    for md_path in md_files:
        html = process_file(md_path, html, dry_run=args.dry_run)

    log(f"\n{'─'*50}")

    if args.dry_run:
        diff_summary(original_html, html)
        log("\n[DRY RUN] brainstew.html was NOT modified")
        sys.exit(0)

    if html == original_html:
        log("No changes made to brainstew.html")
    else:
        with open(BRAINSTEW, 'w', encoding='utf-8') as fh:
            fh.write(html)
        diff_summary(original_html, html)
        log(f"\nDone. {BRAINSTEW} updated.")


if __name__ == '__main__':
    main()
