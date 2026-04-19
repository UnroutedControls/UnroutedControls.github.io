---
title: Pipeline Test Post
date: 04/17/26
from: uc
newsletter: false
---

# Pipeline Test Post

if you're reading this in the BS Mail inbox then the auto-publish pipeline is working correctly!! 

delete this post once confirmed. to delete: remove the inbox row div and the script block from brainstew.html with the id `post-pipeline-test-post`.

---

## what just happened

you pushed this `.md` file to `posts/` and github actions:

- read the frontmatter
- injected an inbox row into brainstew.html
- injected the markdown content block into brainstew.html  
- committed the updated brainstew.html back to the repo
- github pages redeployed

total time: about 60 seconds.

---

## how to write a real post

just write normal markdown. frontmatter at the top:

```
---
title: My Post Title
date: MM/DD/YY
from: uc
---

# My Post Title

content here...
```

that's it. push it and it goes live.

> newsletter: false means this post won't be emailed to subscribers.
> remove that line on real posts if you want them sent out.

