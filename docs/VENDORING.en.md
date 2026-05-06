# Vendoring twikit

> ⚠️ This patch log is currently authored in 中文 only. Switch the **language toggle in the top bar to 中文** to read the full version, or browse the source on [GitHub](https://github.com/tangivis/twitter-mcp/blob/main/docs/VENDORING.zh.md).

## Why this exists (English summary)

PyPI doesn't accept `git+` URLs as dependencies, but `twikit` 2.3.3 on PyPI has two known bugs that PR#412 fixes upstream (still unmerged at the time of writing). Plus, X's response shapes drift in ways that benefit from defensive parsing.

To keep `pip install twikit-mcp` working out of the box, we vendor the entire `twikit` package into `twitter_mcp/_vendor/twikit/` and apply both PR#412's fixes and our own additional patches.

## Patch log (English summary)

Each entry below is a patch applied on top of upstream `twikit`. The Chinese page has full reasoning, regression tests, and reproduction commands.

| Version | File | Fix |
|---|---|---|
| 0.1.3 | `_vendor/twikit/user.py` | `User.__init__` tolerates missing `legacy.entities.description.urls` and `legacy.withheld_in_countries`. |
| 0.1.4 | `_vendor/twikit/user.py` | `User.__init__` fully defensive — every `legacy.*` field uses `.get()` with type-appropriate defaults. |
| 0.1.5 | `_vendor/twikit/tweet.py` | `Tweet` properties + `entities.*` subtree fully defensive. |
| 0.1.9 | `_vendor/twikit/client/gql.py` | `tweet_result_by_rest_id` flips `fieldToggles.withArticlePlainText` from `False` to `True` (issue #10 — without this, article body never populates). |
| 0.1.21 | `_vendor/twikit/client/client.py` | `get_lists` uses `.get()` chain instead of bracket access (issue #37 — burner accounts with 0 lists got `KeyError: 'list'`). |

## Exit strategy

When `twikit` releases > 2.3.3 with PR#412 merged + our patches upstreamed:

1. Delete `twitter_mcp/_vendor/twikit/`
2. In `pyproject.toml`, add `"twikit>=X.Y.Z"` to `dependencies`
3. Update `server.py` imports back to `from twikit import Client`

Until then, every patch carries a `# twitter-mcp patch (issue #N)` marker and is logged in the 中文 patch table (toggle the language switch above) for traceability.

## Translation contributions welcome

Open a PR adding `docs/VENDORING.en.md` content. The 中文 page is mostly factual (commit hashes, file paths, problem/solution pairs) — direct translation works fine.
