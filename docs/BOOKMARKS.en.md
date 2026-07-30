# Private bookmark export and categorization

The `get_bookmarks` MCP tool returns authenticated bookmark pages without
writing anything to disk. If you build a durable archive around it, treat the
archive as private account data: bookmarked tweet text and the raw response can
reveal interests, research, contacts, and URLs that are not intended for a
public repository.

## Private output location

Use this repository-local path:

```text
.private/twitter-bookmarks/
```

The repository `.gitignore` excludes that exact directory. The narrower path is
intentional: it protects bookmark exports without silently ignoring unrelated
files elsewhere in `.private`.

Create directories with mode 700 and files with mode 600. Keep authentication
outside the archive:

- Browser cookies remain in the owner-only `TWITTER_COOKIES` file.
- An XChat PIN remains in a gitignored owner-only env file.
- OAuth access and refresh tokens remain in the owner-only token store.
- None of those secrets belongs in a bookmark JSON or Markdown file.

## Complete pagination

1. Call `get_bookmarks` with `count=100` and no cursor.
2. Save the returned tweets and `next_cursor` in a checkpoint.
3. Call the same tool again with that cursor.
4. Deduplicate every result by tweet ID. Adjacent X pages can overlap.
5. Atomically replace the checkpoint after every successful page, including the
   next cursor, so a timeout can resume without replaying the full collection.
6. Continue until one of these terminal conditions occurs:
   - `next_cursor` is absent; or
   - X repeats a previously seen cursor and the repeated page adds zero new IDs.
7. Treat a repeated cursor that still adds new IDs as incomplete and investigate
   it instead of silently truncating the archive.

Use bounded retries for rate limits and transient transport errors. Do not place
an arbitrary page limit on an "all bookmarks" export; completeness comes from
the terminal cursor condition and unique-ID audit.

## Preserved fields

The raw archive should preserve the complete returned tweet payload once. A
smaller categorized archive can retain only the fields useful for browsing:

- bookmark order;
- tweet ID and canonical X URL;
- author ID, screen name, and display name;
- created timestamp and language;
- full text and hashtags;
- expanded links and media references;
- engagement metrics;
- primary category and up to three category tags.

Keep media URLs and metadata by default. Downloading the actual image/video
binaries is a separate, potentially much larger operation and should not happen
implicitly.

## Sorting procedure

Normalize the tweet text, author name, screen name, hashtags, and expanded URL
domains to lowercase. Score explicit keyword phrases and domain hints against
the taxonomy below. Use word boundaries for short terms such as `AI`, `AR`,
`VR`, and `F1` so unrelated words do not match accidentally.

Choose the highest-scoring category as the primary category and retain up to
the next two positive-scoring categories as tags. Domain-specific evidence such
as GitHub, arXiv, Apple Developer, UploadVR, OpenSea, or YouTube should receive
more weight than a single generic keyword.

Keep primary topics broad and stable:

- Technology
- Business & Finance
- Design & Creativity
- Learning & Research
- News & Society
- Media & Entertainment
- Sports & Recreation
- Lifestyle & Personal Development
- Reference & Resources

Use narrower interests as tags rather than primary topics. For example, AI,
software engineering, developer tools, cloud, security, Apple, mobile, XR,
gaming, startups, marketing, investing, crypto, podcasts, and motorsport can all
be tags beneath one of the broader topics. This keeps the main index easy to
scan while preserving useful detail for filtering.

When no explicit category scores, use deterministic fallbacks instead of one
oversized miscellaneous bucket:

1. Media attached -> Visual Media
2. Expanded external URL -> Reference & Resources
3. Text at most 160 characters -> Notes & Quotes
4. Otherwise -> General Commentary

After changing the taxonomy, reclassify the saved raw archive rather than
calling X again. Remove obsolete category files so an old category cannot linger
beside the new index.

## Suggested private file layout

```text
.private/twitter-bookmarks/
├── raw-bookmarks.json
├── categorized-bookmarks.json
├── manifest.json
├── index.md
└── categories/
    ├── ai-machine-learning.md
    ├── software-engineering.md
    └── ...
```

The manifest should record the export time, logical page count, number of unique
IDs, duplicates removed, terminal reason, pagination-complete flag, and category
counts. Do not infer completeness merely because a request returned fewer than
100 tweets.

## Verification before reporting completion

Run all of these checks:

```bash
git check-ignore -v .private/twitter-bookmarks/raw-bookmarks.json
git status --short
find .private/twitter-bookmarks -type f -perm -004 -print
find .private/twitter-bookmarks -type d ! -perm 700 -print
```

Then verify programmatically that:

- raw count equals categorized count;
- total category count equals the raw count;
- every tweet ID is unique;
- the manifest says pagination is complete and records the terminal reason;
- every file is mode 600 and every directory is mode 700;
- the Git worktree contains no bookmark export files.

Only report aggregate counts and category names unless the user explicitly asks
to inspect private bookmark content.
