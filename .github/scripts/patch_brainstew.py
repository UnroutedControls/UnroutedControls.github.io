#!/usr/bin/env python3
"""
patch_brainstew.py — improved

Fixes and features:
- Uses make_post_id when inserting; for updates will prefer existing matching IDs.
- Robust post_exists: matches either id or data-post-id.
- Safer update_post using permissive regexes and fallback behavior.
- Consistent escaping for attributes vs text nodes.
- Normalizes frontmatter keys and coerces update to boolean.
- Better status-count replacement anchored to id.
- Dry-run prints unified diff (first 200 lines) and top added/removed lines.
- Logs collisions and chosen post_id.
- More defensive marker handling.
"""

import sys
import os
import re
import argparse
import difflib
from datetime import datetime
from html import escape

BRAINSTEW    = "brainstew.html"
ROW_MARKER   = "<!-- ADD POSTS HERE:"
BLOCK_MARKER = "<!-- add more markdown posts here"

def log(msg=""):
    print(msg, flush=True)

def today_str():
    d = datetime.now()
    return f"{d.month:02d}/{d.day:02d}/{str(d.year)[2:]}"

def parse_frontmatter(text):
    """
    Returns (meta_dict, body_text).
    Keys normalized to lowercase. 'update' coerced to boolean.
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

    # Normalize and coerce types
    meta['title'] = meta['title'].strip()
    meta['date']  = meta['date'].strip()
    meta['from']  = meta['from'].strip()
    meta['update'] = str(meta['update']).strip().lower() in ('true', 'yes', '1', 'y')

    return meta, body.strip()

def slug_from_file(path):
    base = os.path.basename(path)
    slug = base.replace('.md', '').replace(' ', '-').lower()
    return re.sub(r'[^a-z0-9-]', '', slug)

def find_existing_post_ids_for_slug(slug, html):
    """Return list of existing post-id strings that start with post-{slug}"""
    pattern = re.compile(r'\b(post-' + re.escape(slug) + r'(?:-\d+)?)\b')
    return sorted(set(pattern.findall(html)), key=lambda s: (len(s), s))

def make_post_id(slug, existing_html):
    """Return a candidate post id that does not collide; prefer next numeric."""
    base = f"post-{slug}"
    if base not in existing_html:
        return base
    i = 2
    while f"{base}-{i}" in existing_html:
        i += 1
    return f"{base}-{i}"

def post_exists(post_id, html):
    """Existence if either id attribute or data-post-id attribute present."""
    return (re.search(r'\bid="' + re.escape(post_id) + r'"', html) is not None or
            re.search(r'\bdata-post-id="' + re.escape(post_id) + r'"', html) is not None)

def build_inbox_row(post_id, meta):
    # For text nodes we escape without quote handling (no additional quoting)
    t = escape(meta['title'], quote=False)
    f = escape(meta['from'],  quote=False)
    d = escape(meta['date'],  quote=False)
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
    # Attributes must be quoted-escaped
    t = escape(meta['title'], quote=True)
    d = escape(meta['date'],  quote=True)
    f = escape(meta['from'],  quote=True)
    # Protect against closing script tag
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
    Insert after ROW_MARKER and before BLOCK_MARKER.
    Newest at top.
    """
    # Find markers on their own lines tolerant to whitespace
    lines = html.splitlines(keepends=True)
    row_idx = None
    block_idx = None
    for i, line in enumerate(lines):
        if ROW_MARKER in line and row_idx is None:
            row_idx = i
        if BLOCK_MARKER in line and block_idx is None:
            block_idx = i

    if row_idx is None:
        raise ValueError(f"ROW_MARKER not found: '{ROW_MARKER}'")
    if block_idx is None:
        raise ValueError(f"BLOCK_MARKER not found: '{BLOCK_MARKER}'")

    lines.insert(row_idx + 1, inbox_row + '\n\n')
    if block_idx > row_idx:
        block_idx += 1
    lines.insert(block_idx, script_block + '\n\n')
    return ''.join(lines)

def safe_replace_script_tag_content(html, post_id, new_body):
    """
    Replace the inner content of the <script ... id="post_id"...>...</script>
    without assuming attribute order. Uses regex to find the opening tag and
    then replace up to the closing </script>.
    """
    open_tag_re = re.compile(r'(<script\b[^>]*\bid="' + re.escape(post_id) + r'"[^>]*>)(.*?)(</script>)',
                             flags=re.DOTALL | re.IGNORECASE)
    safe_body = new_body.replace('</script>', '<\\/script>')
    def repl(m):
        return m.group(1) + "\n" + safe_body + "\n" + m.group(3)
    new_html, count = open_tag_re.subn(repl, html)
    if count == 0:
        raise ValueError(f"Script block with id='{post_id}' not found for replacement")
    return new_html

def safe_update_data_title_attribute(html, post_id, new_title):
    """
    Replace or add data-title="..." on the script tag with id=post_id.
    """
    # Find the script tag opening portion
    script_open_re = re.compile(r'(<script\b[^>]*\bid="' + re.escape(post_id) + r'"[^>]*>)',
                                flags=re.IGNORECASE)
    m = script_open_re.search(html)
    if not m:
        raise ValueError(f"Script tag with id='{post_id}' not found for data-title update")
    open_tag = m.group(1)
    # Replace data-title if present
    if 'data-title=' in open_tag:
        new_open_tag = re.sub(r'(data-title\s*=\s*")[^"]*(")', r'\1' + escape(new_title, quote=True) + r'\2', open_tag)
    else:
        # insert before closing '>'
        new_open_tag = open_tag[:-1] + f' data-title="{escape(new_title, quote=True)}">'
    # Substitute the single open tag occurrence
    return html[:m.start(1)] + new_open_tag + html[m.end(1):]

def safe_update_inbox_row_title(html, post_id, new_title):
    """
    Find the inbox row with data-post-id="post_id" and replace the third <div> text node (the visible title).
    Approach: find the row start, then a simple regex for the third <div>...</div> after it.
    """
    row_re = re.compile(r'(<div[^>]*data-post-id="' + re.escape(post_id) + r'"[^>]*>)(.*?)(</div>)',
                        flags=re.DOTALL | re.IGNORECASE)
    # Locate the row's start position
    m = re.search(r'<div[^>]*data-post-id="' + re.escape(post_id) + r'"[^>]*>', html)
    if not m:
        raise ValueError(f"Inbox row with data-post-id='{post_id}' not found")
    start_idx = m.start()
    # From that start, search forward for the sequence of three immediate child divs and replace the 3rd one's content.
    sub_html = html[start_idx:]
    # pattern to find the first three sibling divs inside the row
    three_divs_re = re.compile(r'(<div\b[^>]*>.*?</div>\s*<div\b[^>]*>.*?</div>\s*<div\b[^>]*>)(.*?)(</div>)',
                               flags=re.DOTALL | re.IGNORECASE)
    m2 = three_divs_re.search(sub_html)
    if not m2:
        raise ValueError("Inbox row structure unexpected; cannot update title reliably")
    new_sub = sub_html[:m2.start(2)] + escape(new_title, quote=False) + sub_html[m2.end(2):]
    return html[:start_idx] + new_sub

def update_post(html, post_id, meta, body):
    """
    Robust update flow:
    - update data-title on script tag
    - update visible title in inbox row
    - replace script block body content
    """
    # Update data-title attribute on script opening tag
    html = safe_update_data_title_attribute(html, post_id, meta['title'])
    # Update visible title in inbox row
    html = safe_update_inbox_row_title(html, post_id, meta['title'])
    # Replace script block content
    html = safe_replace_script_tag_content(html, post_id, body)
    return html

def update_status_bar(html):
    # Count inbox-item occurrences
    count = len(re.findall(r'\bclass="inbox-item\b', html))
    # Replace inner text of the element with id="status-count"
    return re.sub(
        r'(<div[^>]*class="status-panel"[^>]*id="status-count"[^>]*>)(.*?)(</div>)',
        lambda m: m.group(1) + f"{count} message(s)" + m.group(3),
        html,
        flags=re.DOTALL | re.IGNORECASE
    )

def diff_summary(original, modified, show_unified=True, max_lines=200):
    """Log a brief summary and optionally some unified diff lines."""
    orig_lines = original.splitlines()
    new_lines  = modified.splitlines()
    added   = [l for l in new_lines  if l not in orig_lines and l.strip()]
    removed = [l for l in orig_lines if l not in new_lines  and l.strip()]
    log(f"  + {len(added)} lines added")
    log(f"  - {len(removed)} lines removed")
    if show_unified:
        ud = difflib.unified_diff(orig_lines, new_lines, lineterm='')
        snippet = []
        for i, line in enumerate(ud):
            if i >= max_lines:
                break
            snippet.append(line)
        if snippet:
            log("\n--- Unified diff (first lines) ---")
            for ln in snippet:
                log(ln)
            log("--- end diff snippet ---\n")

def process_file(md_path, html, dry_run=False):
    log(f"\n{'─'*50}")
    log(f"  File:    {md_path}")

    if not os.path.exists(md_path):
        log(f"  WARNING: file not found — skipping")
        return html

    with open(md_path, 'r', encoding='utf-8') as fh:
        text = fh.read()

    meta, body = parse_frontmatter(text)
    slug = slug_from_file(md_path)

    # Detect existing ids for this slug
    existing_ids = find_existing_post_ids_for_slug(slug, html)
    chosen_post_id = None
    is_update = bool(meta.get('update', False))

    if existing_ids:
        # If any existing IDs for slug, prefer the first (likely base or lowest suffix)
        chosen_post_id = existing_ids[0]
        log(f"  Existing IDs for slug '{slug}': {existing_ids} — choosing {chosen_post_id}")
    else:
        chosen_post_id = f"post-{slug}"

    log(f"  Title:   {meta['title']}")
    log(f"  Date:    {meta['date']}")
    log(f"  From:    {meta['from']}")
    log(f"  Slug:    {slug}")
    log(f"  Post ID: {chosen_post_id}")
    log(f"  Update:  {is_update}")

    if post_exists(chosen_post_id, html):
        if is_update:
            log(f"  Mode: UPDATE existing post")
            if dry_run:
                log(f"  [DRY RUN] would update post '{chosen_post_id}'")
                return html
            try:
                html = update_post(html, chosen_post_id, meta, body)
                log(f"  Updated successfully")
            except Exception as e:
                log(f"  ERROR updating post '{chosen_post_id}': {e}")
        else:
            log(f"  SKIP: post '{chosen_post_id}' already exists.")
            log(f"  To update it, add 'update: true' to the frontmatter.")
    else:
        # No exact existing match — generate a non-colliding id for insertion
        insert_post_id = make_post_id(slug, html)
        if insert_post_id != f"post-{slug}":
            log(f"  Collision detected — using insert id '{insert_post_id}'")
        log(f"  Mode: INSERT new post as {insert_post_id}")
        if dry_run:
            log(f"  [DRY RUN] would insert post '{insert_post_id}'")
            return html
        inbox_row    = build_inbox_row(insert_post_id, meta)
        script_block = build_script_block(insert_post_id, meta, body)
        html         = inject_post(html, inbox_row, script_block)
        html         = update_status_bar(html)
        log(f"  Inserted successfully")

    return html

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
        try:
            html = process_file(md_path, html, dry_run=args.dry_run)
        except Exception as e:
            log(f"ERROR processing {md_path}: {e}")

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
