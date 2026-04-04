---
title: HowTo Setup EZ Blog Posts w Github Actions & .md Files
date: 04/03/26
---


# AUTO-PUBLISHING A STATIC SITE BLOG WITH GITHUB ACTIONS

```
 ________________________________________________
|                                                |
|   PUSH .MD FILE  >>  GITHUB ACTIONS  >>  LIVE  |
|________________________________________________|
```

> no CMS. no backend. no subscription. just git.

---

## WHAT THIS IS

A zero-cost, zero-dependency pipeline that lets you write a markdown file,
push it to GitHub, and have it automatically injected into your static HTML
blog page — formatted, titled, and live in about 60 seconds.

Works from any device with a browser. No local tooling required after setup.

**What you need:**

- A static site hosted on GitHub Pages
- A single HTML file that acts as your blog/inbox page
- Two marker comments inside that HTML file (explained below)
- 5 minutes of setup

---

## HOW IT WORKS

```
YOU PUSH posts/my-post.md
          |
          v
GitHub Actions triggers automatically
          |
          v
Python script reads your markdown + frontmatter
          |
          v
Injects an inbox row + content block into your HTML
          |
          v
Commits updated HTML back to your repo
          |
          v
GitHub Pages deploys
          |
          v
POST IS LIVE (~60 seconds total)
```

No rebuild step. No static site generator. No Jekyll, Hugo, or anything else.
Your HTML file IS the site. The script just adds to it.

---

## PART 1 :: PREPARE YOUR HTML FILE

Your blog HTML file needs two comment markers that tell the script
exactly where to inject new content. Add them if they aren't there.

### Marker 1 — Inbox row insertion point

Inside the container where your post list lives, add this comment:

```html
<div id="your-posts-container">

  <!-- ADD POSTS HERE: copy one row per post -->

  <!-- existing posts below this line -->
  <div data-post-id="post-1"> ... </div>

</div>
```

The script inserts new posts **directly after** this comment,
so the newest post always appears at the top.

### Marker 2 — Content block insertion point

Near the bottom of your HTML, before `</body>`, add this comment:

```html
<!-- add more markdown posts here -->

</body>
</html>
```

The script inserts the markdown content blocks **before** this comment.

### Marker strings (exact text matters)

The Python script looks for these exact strings:

```
ROW_MARKER   = "<!-- ADD POSTS HERE:"
BLOCK_MARKER = "<!-- add more markdown posts here"
```

If you want to use different comment text, edit the two constants
at the top of `.github/scripts/patch_brainstew.py` to match.

---

## PART 2 :: ADD THE FILES TO YOUR REPO

Your repo needs this structure:

```
your-repo/
├── your-blog.html              <- your existing HTML file
├── posts/                      <- CREATE THIS (your writing goes here)
│   └── example-post.md
└── .github/
    ├── workflows/
    │   └── publish-post.yml    <- the Action
    └── scripts/
        └── patch_brainstew.py  <- the patcher (rename if you want)
```

Create the folders:

```bash
mkdir -p .github/workflows .github/scripts posts
```

---

## PART 3 :: THE WORKFLOW FILE

Create `.github/workflows/publish-post.yml`:

```yaml
name: Publish Blog Post

on:
  push:
    paths:
      - 'posts/**.md'

permissions:
  contents: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Find changed posts
        id: find_posts
        run: |
          CHANGED=$(git diff --name-only --diff-filter=AM \
            ${{ github.event.before }} ${{ github.sha }} \
            -- 'posts/*.md' 2>/dev/null || \
            git show --name-only --format="" \
            ${{ github.sha }} -- 'posts/*.md')
          echo "changed_files<<EOF" >> $GITHUB_OUTPUT
          echo "$CHANGED" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT

      - name: Patch HTML
        run: |
          python3 .github/scripts/patch_brainstew.py \
            "${{ steps.find_posts.outputs.changed_files }}"

      - name: Commit and push
        run: |
          git config user.name  "Blog Bot"
          git config user.email "blogbot@noreply.github.com"
          git add your-blog.html
          git diff --staged --quiet || \
            git commit -m "new post published [skip ci]"
          git push
```

**Important:** change `your-blog.html` on the second-to-last line
to the actual filename of your blog HTML file.

---

## PART 4 :: THE PATCHER SCRIPT

Create `.github/scripts/patch_brainstew.py`.

At the top of the file, set these three constants to match your setup:

```python
BRAINSTEW    = "your-blog.html"        # your HTML filename
ROW_MARKER   = "<!-- ADD POSTS HERE:"  # must match what's in your HTML
BLOCK_MARKER = "<!-- add more markdown posts here"
```

The script reads your markdown file, parses the frontmatter,
builds an HTML row for the post list and a content block,
then injects both into the right places in your HTML file.

It also updates any status bar element with `id="status-count"`
if you have one — optional, delete that function if you don't.

Full script available at: `github.com` — search "patch_brainstew github actions static blog"
or copy it from the repo you set this up in.

---

## PART 5 :: ENABLE WRITE PERMISSIONS

The Action needs to commit back to your repo.
This is off by default — turn it on once:

```
GitHub repo → Settings → Actions → General
→ Workflow permissions
→ ● Read and write permissions
→ Save
```

---

## PART 6 :: WRITING A POST

Every post is a `.md` file in the `posts/` folder.

### Frontmatter

Add this block at the very top of the file:

```
---
title: Your Post Title
date: 04/03/26
from: yourname
---
```

All three fields are optional:

- `title` — falls back to your first `# heading` if missing
- `date` — falls back to today's date (MM/DD/YY) if missing
- `from` — falls back to "uc" if missing, rename the default in the script

### Post body

Write normal markdown below the frontmatter:

```markdown
---
title: My First Post
date: 04/03/26
---

# My First Post

Normal **markdown** works here. Headers, lists, code blocks,
blockquotes, links — all of it.

## A Section

- bullet lists
- work fine

> blockquotes too

    code blocks
    like this

---

horizontal rules become decorative dividers if your renderer handles them
```

### File naming

Name the file something URL-friendly:

```
posts/my-first-post.md
posts/homelab-update-april.md
posts/thoughts-on-rust.md
```

The filename becomes the post ID in the HTML (`post-my-first-post`).
Spaces and uppercase are fine — the script slugifies it.

---

## PUBLISHING WORKFLOW

### From a computer

```bash
# new post
nano posts/my-post.md

# write it, save, then:
git add posts/my-post.md
git commit -m "new post: my post"
git push
```

### From a phone (zero install)

```
1. Open your repo on github.com in mobile browser
2. Navigate to the posts/ folder
3. Tap Add file → Create new file
4. Name it: my-post.md
5. Write frontmatter + content
6. Tap Commit changes → Commit directly to main
7. Done
```

Watch the Actions tab — green checkmark means it's live.

### From Obsidian (best mobile experience)

```
1. Install Obsidian (free) + community plugin: Obsidian Git
2. Clone your repo as an Obsidian vault
3. Write posts in the posts/ folder
4. Use Obsidian Git to commit + push
```

---

## WHAT HAPPENS AFTER YOU PUSH

```
git push
  |
  +-- GitHub sees new file in posts/
  |
  +-- publish-post.yml triggers
  |
  +-- Python script runs:
  |     reads posts/your-post.md
  |     parses frontmatter
  |     builds HTML row
  |     builds content block
  |     injects both into your-blog.html
  |     writes file back
  |
  +-- Bot commits: "new post published [skip ci]"
  |
  +-- GitHub Pages redeploys
  |
  +-- live in ~60 seconds
```

The `[skip ci]` tag on the bot commit prevents an infinite loop
where the bot's commit triggers the Action again.

---

## UPDATING OR DELETING A POST

### Update

Re-pushing the same `.md` file won't create a duplicate — the script
detects the post ID already exists and skips it.

To update post content, edit the HTML directly: find the
`<script type="text/markdown" id="post-your-slug">` block
and edit the markdown inside it.

### Delete

Find and remove two things in your HTML file:

```
1. The <div class="inbox-item" data-post-id="post-your-slug"> row
2. The <script type="text/markdown" id="post-your-slug"> block
```

The `data-post-id` on the row matches the `id` on the script block.

---

## TROUBLESHOOTING

```
ACTION FAILS: "Could not find ROW_MARKER"
  → Check your HTML has exactly: <!-- ADD POSTS HERE:
  → Or update ROW_MARKER in the Python script to match

ACTION FAILS: permission denied on git push
  → Settings → Actions → General → Read and write permissions

ACTION DOESN'T TRIGGER
  → Make sure the file is in posts/ (not repo root)
  → Make sure filename ends in .md
  → Check the on.push.paths in the yml matches your folder name

POST APPEARS BUT TITLE IS WRONG
  → Add a proper frontmatter block with title: at the top

ACTION RUNS BUT HTML LOOKS BROKEN
  → Check for </script> anywhere in your post body
  → The patcher escapes these but if you edited manually it may not be
```

---

## COST

```
GitHub Actions free tier:  2,000 minutes/month
This workflow per run:     ~30 seconds
Posts you can publish:     ~4,000/month before hitting limits

Cost:                      $0.00
```

---

## REQUIREMENTS SUMMARY

```
[ ] GitHub account (free)
[ ] Repo with GitHub Pages enabled
[ ] Static HTML blog file with two marker comments
[ ] .github/workflows/publish-post.yml added to repo
[ ] .github/scripts/patch_brainstew.py added to repo
[ ] posts/ folder created in repo root
[ ] Workflow permissions set to read+write in repo settings
[ ] 5 minutes
```

---

```
>> SETUP COMPLETE
>> WRITE .MD FILE
>> GIT PUSH
>> DONE
```

> no logins. no dashboards. no subscriptions.
> just a text file and a push.


