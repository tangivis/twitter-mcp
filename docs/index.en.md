# twikit-mcp

**Twitter/X MCP server + CLI — no API key needed.**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

An [MCP](https://modelcontextprotocol.io/) server that lets Claude (or any MCP-compatible AI agent) interact with Twitter/X using browser cookies. The same `twikit-mcp` binary doubles as a CLI for shell scripts and debugging.

## What's new in 0.1.45

- **CI: an unreachable review API no longer fails the PR** — `pr-review.yml` had a warn-and-skip handler for a bad LLM response, but GitHub runs `run:` blocks under `bash -e`, so a non-zero `curl` exit (timeout, DNS, connection refused) killed the step *before* the handler ran. [Run #141](https://github.com/tangivis/twitter-mcp/actions/runs/32003925207) died that way and turned an already-approved PR red. All three call sites now capture curl's status and degrade as intended. A test extracts the real shell out of the workflow and runs it against a stub `curl`, so it can't drift from what CI executes — and it immediately found the same latent bug in `issue-triage.yml`. (closes #124)
- **No more duplicate review on a draft→ready flip** — reviews now record which commit they covered, and a second run on the same SHA skips instead of spending another LLM call. `ready_for_review` stays a trigger, since a contributor marking a draft ready genuinely wants a review then.

CI only — no change to the package. Upgrade is optional.

## What's new in 0.1.44

- **Listed in the official MCP registry** — a `server.json` manifest now declares this server to [`registry.modelcontextprotocol.io`](https://registry.modelcontextprotocol.io) as `io.github.tangivis/twitter-mcp`: PyPI package, stdio transport, and every environment variable with a description you can act on. A sentinel test keeps it in sync with `pyproject.toml` and cross-checks the declared variables against the ones the code actually reads — in both directions, so the manifest can't advertise a knob that does nothing or omit one that matters. (closes #122)
- **DeepSeek Harness card completed** — documents the `reconnect` keys and the fact that a duplicate `serverName` across live instances fails the later plugin at load.

## What's new in 0.1.43

- **README's client list is no longer stale** — Pi (documented in 0.1.34) and DeepSeek Harness (0.1.40) were missing from the one-line "Works with" summary in all three languages, because nothing connected that line to the Install page. Both are now listed, and a sentinel test asserts every client card on the Install page appears in every README summary, so the next one can't quietly go missing. Docs + test only.

## What's new in 0.1.42

- **`get_retweeters` no longer dies on a suspended account** — when one of a tweet's retweeters has been suspended or deleted, X returns `__typename: UserUnavailable` for that entry, which carries no `rest_id`. twikit's `User.__init__` reads that key unconditionally, so a single dead account killed the entire call with `KeyError: 'rest_id'`. Unparseable entries are now skipped and the rest are returned. `get_favoriters` shares the same code path and the same fix. Caught by live-smoke against real X on 2026-08-17. (issue #37)
- Also hardened one line away in the same function: cursor extraction assumed the last two timeline entries are always cursors, which `KeyError`'d on gated responses that omit them. Missing cursors now yield `None`.

Upgrade with `uv tool upgrade twikit-mcp` (or `pip install --upgrade twikit-mcp`).

## What's new in 0.1.41

- **Read XChat (encrypted DMs) locally** — three new tools take the registry to 62: `xchat_status`, `xchat_list_conversations`, `xchat_get_history`. X's web client already decrypts your conversations and stores the plaintext in a local SQLite file; these read it. **No new dependencies, no network, no credentials, no write path** — the database is opened `mode=ro&immutable=1`, every statement is a SELECT, encryption keys are never read, and reading here does not mark anything read on X. Configure with `XCHAT_BROWSER` (chrome/chromium/edge/brave/aside), `XCHAT_BROWSER_PROFILE`, or `XCHAT_DATABASE_PATH`; with none set the tools stay dormant and the rest of the server is unaffected. See the [XChat page](xchat.md). (closes #118)
- Thanks to [@DJNgoma](https://github.com/DJNgoma) — the SQLite reading and browser-profile discovery are derived from his work in PR #107.

Upgrade with `uv tool upgrade twikit-mcp` (or `pip install --upgrade twikit-mcp`).

## What's new in 0.1.40

- **DeepSeek Harness (dsh) setup guide** — the [Install page](install.md) now covers [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness). Unlike Pi, dsh has a first-party MCP client (`@deepseek-ai/dsh-mcp-client`), so no community extension is needed — but its config is a plugin entry in `cordis.yml` rather than the usual `mcpServers` map, and it has **no tool allowlist**, so all 59 tools register. The card covers both, plus the `failOnStartupError` and `toolCallTimeoutMs` keys worth knowing. Docs only — no code changes; `twikit-mcp` is a standard stdio MCP server and needs nothing special.

## What's new in 0.1.39

- **Migrated to MCP Python SDK v2** — the server is now built on `MCPServer` (`mcp.server.mcpserver`) instead of the removed `FastMCP`, and the dependency moved from `mcp[cli]>=1.27,<2` to `>=2,<3`. **Nothing changes for you at the protocol level**: the full `tools/list` payload — negotiated protocol version, capabilities, and all 59 tools with their complete input/output schemas — is byte-for-byte identical to 0.1.38 (58,843 bytes, diffed across both SDKs over a real stdio handshake). Upgrading pulls SDK 2.x; if you pin `mcp<2` yourself, stay on 0.1.38. (closes #109)
- **`serverInfo.version` now reports the actual package version** — SDK v1 filled this field with its own version, and v2 leaves it empty unless set. Clients now see `twikit-mcp`'s real version in the initialize response.

Upgrade with `uv tool upgrade twikit-mcp` (or `pip install --upgrade twikit-mcp`).

## What's new in 0.1.38

- **Groundwork for the MCP 2026-07-28 spec** — the MCP Python SDK 2.0.0 is now stable, and it renames the class this server is built on (`FastMCP` → `MCPServer`). Your install is unaffected: the dependency has been pinned to SDK 1.x since 0.1.35. This release funnels every read of the SDK's private tool registry through a single internal accessor, which turns the upcoming v2 migration from a ~70-site sweep into a one-line change. Pure internal refactor — no behavior change, byte-identical generated docs and CLI output. (issue #109 phase 2)

Upgrade with `uv tool upgrade twikit-mcp` (or `pip install --upgrade twikit-mcp`).

## What's new in 0.1.37

- **`get_dm_history` no longer crashes on message requests** — accepting a stranger's message request makes X inject a `trust_conversation` system entry into the conversation timeline, which crashed the tool with `KeyError: 'message'`. Non-message entries are now skipped and surfaced in a new `timeline_events` field, and a `warnings` field flags that history may be incomplete for end-to-end encrypted (X Chat) conversations — the legacy DM API cannot return encrypted bodies, so agents should not conclude "no reply was sent". Clean conversations keep the exact same JSON shape as before. (closes #104)
- **First-time DM reads no longer misreport "User not found"** — reading a conversation right after sending a first DM can transiently 404 on X's side; the tool now retries up to 3 times with short backoff and reports the conversation (not the user) as unavailable if it persists. (closes #102)
- Thanks to [@DJNgoma](https://github.com/DJNgoma) for the live diagnosis and both patches (PRs #103, #105).

Upgrade with `uv tool upgrade twikit-mcp` (or `pip install --upgrade twikit-mcp`).

## What's new in 0.1.36

- **Integer IDs accepted everywhere** — X serializes tweet/user/list IDs as JSON *numbers* (`"id": 2087887408440164663` next to `"id_str"`). Any client that echoed the numeric `id` back — `{"tweet_id": id}` without a `str()` — used to be rejected by validation before the tool even ran (`Input should be a valid string`). Every snowflake-shaped parameter (37 sites across the 59 tools: `tweet_id`, `user_id`, `list_id`, `media_ids`, …) now accepts int or string and coerces losslessly to string. Floats stay rejected: these IDs exceed 2^53, so a float is already precision-corrupted and would silently target the wrong tweet. (closes #111)

Upgrade with `uv tool upgrade twikit-mcp` (or `pip install --upgrade twikit-mcp`).

## What's new in 0.1.35

- **Pinned the MCP SDK below v2** — `mcp[cli]` had no upper bound, so a fresh `uv tool install twikit-mcp` would have pulled SDK v2 the day 2.0.0 leaves pre-release. v2 (implementing the [2026-07-28 spec](https://blog.modelcontextprotocol.io/posts/2026-07-28/)) renames `FastMCP` → `MCPServer` and moves `mcp.server.fastmcp.*` to `mcp.server.mcpserver.*`, which breaks this server at import. Now `>=1.27,<2`, guarded by a sentinel test. No behavior change on an existing install. Migration tracked in issue #109.

## What's new in 0.1.34

- **Pi setup guide** — the [Install page](install.md) now covers [Pi](https://github.com/earendil-works/pi). Pi has no built-in MCP, so the card walks through installing a community MCP extension (`pi-mcp-adapter`) and using its `directTools` allowlist to keep this server's 59 tools from crowding a coding session's context. Docs only — no code changes; `twikit-mcp` is a standard stdio MCP server and needs nothing special.

## What's new in 0.1.33

- **Drop the 200-char text truncation** — `get_timeline` / `search_tweets` / `get_user_tweets` / `get_bookmarks` / `get_list_tweets` / `get_scheduled_tweets` / `get_community_tweets` / `get_communities_timeline` / `search_community_tweet` no longer cut tweet text at 200 characters. `get_tweet` and `get_tweet_replies` also switch to `Tweet.full_text`, which returns the long-form text (up to 4000 chars) for X note tweets. Compact responses are user-controlled via `count`. (closes #97)
- **`get_article_preview` distinguishes quote tweets** — when the input is a quote tweet, the error now says "this is a quote tweet, not an article. Use get_tweet to read the quoted tweet content" instead of the generic "does not embed an article".

## What's new in 0.1.32

- **Read tweet replies** — new `get_tweet_replies(tweet_id, cursor=None)` tool fetches the comments / discussion under a tweet. Uses X's TweetDetail GraphQL via vendored twikit; one page per call with `next_cursor` for more. Returns the same compact reply shape as `get_user_tweets` / `get_timeline`. (closes #94)

## What's new in 0.1.31

- **Per-client install matrix in docs** — new [Install page](install.md) walks through registering `twikit-mcp` with Claude Code / Claude Desktop / Cursor / Windsurf / Cline / opencode (config file path + JSON snippet, ≤ 12 lines per client). Single canonical install command (`uv tool install twikit-mcp`); JSON shape is universal across clients. (closes #92)

## What's new in 0.1.30

- **Localized API docs page** — `/zh/api/` and `/ja/api/` now show Chinese / Japanese chrome (title, intro, table headers, section labels) instead of falling back to English. Tool docstrings stay native (Python source) — same trade-off `mkdocstrings` makes. (closes #90)

## What's new in 0.1.29

- **Community + article-preview reliability** — `get_community` / `get_community_tweets` / `get_community_members` / `get_community_moderators` / `search_community_tweet` no longer crash with `KeyError: 'rest_id'` / `IndexError`. `get_article_preview` now surfaces a clean `ToolError` instead of leaking `HTTPStatusError` when the syndication endpoint returns 404 for a stale article. Defensive `.get()` parsing in `_vendor/twikit/community.py` + `client.py`. Closes issue #76 — `T_DRIFT` is now empty in `live-smoke.yml`. (issue #76 parts 2 + 3)

## What's new in 0.1.28

- **List-tool reliability** — `get_list` / `get_list_tweets` / `get_list_members` / `get_list_subscribers` no longer crash with `KeyError: 'created_at'` / `IndexError` / `Invalid list id` on burner-gated responses. Defensive parsing in `_vendor/twikit/list.py` + `client.py`: missing fields return `None`/`""`/`0`, empty entries return empty `Result`. Live-smoke now catches future regressions of these classes (no more `T_DRIFT` tolerance for the list path). (issue #76 part 1)

## What's new in 0.1.27

- **Download tweet videos via yt-dlp** — new `download_tweet_video` MCP tool + `twikit-mcp video <id>` CLI subcommand. Saves to `~/Downloads/twikit-mcp/` by default. Authenticated via your existing `cookies.json`. Requires [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) on PATH (`uv tool install yt-dlp`); `ffmpeg` only needed if you pass a separate-stream format like `bestvideo+bestaudio`. (closes #84)

## What's new in 0.1.26

- **Quote tweet visibility on `get_tweet`** — the response now includes `is_quote_status`, `quoted_id`, `quoted_author`, and `quoted_text` when the tweet quote-retweets another. Agents can now show the quoted text inline without an extra `get_tweet` round-trip — the data is already in the same GraphQL response, we just expose it. (closes #82)

## What's new in 0.1.25

- **Conversation context on `get_tweet`** — the response now includes `in_reply_to` (parent tweet ID when the tweet is a reply) and `conversation_id` (root tweet ID of the thread). Agents can now reconstruct thread context from a single tweet without needing the user to paste the parent link. (closes #77)

## What's new in 0.1.24

- **Rich-rendered cards** — the terminal cards from 0.1.23 are now produced by [Rich](https://github.com/Textualize/rich), giving correct cell-width math for emoji + CJK (no more right-border drift on `❤ 🔁` lines), and **OSC 8 clickable hyperlinks** for tweet / profile / bio URLs in iTerm2, kitty, WezTerm, Windows Terminal, gnome-terminal ≥ 3.36, etc. The trends list is now a proper table.
- Plain (non-TTY) output unchanged: `| jq` / `> file` / `NO_COLOR=1` consumers stay byte-stable.

## What's new in 0.1.23

- **ASCII Twitter-card UI** — `twikit-mcp tweet`, `user`, `tl`, `search`, `trends` now render box-drawing cards in your terminal (bold author, dim timestamps, separators between body / counts / URL). Piping to a file or another command, or setting `NO_COLOR=1`, auto-falls-back to the previous byte-stable plain text. See [CLI mode](cli.md) for samples.

## What's new in 0.1.22

- **Human-friendly CLI subcommands** — read tweets / profiles / timeline / search / trends straight from your terminal:

  ```bash
  twikit-mcp tweet 20
  twikit-mcp user elonmusk
  twikit-mcp tl 10
  ```

  Plain text output, native unicode, sensible defaults. See the [CLI mode page](cli.md).
- **UTF-8 outputs end-to-end** — no more `\uXXXX` escapes. Greek / 中文 / 日本語 / emoji all flow through tools as readable text.
- **Tri-lingual docs site** — this very page; switch language in the top bar.

## What you get

- **57 tools** covering tweets, users, lists, communities, scheduled tweets + polls, DMs, articles, search, trends, notifications.
- **Browser-cookie auth** — copy `ct0` + `auth_token` from your X session, you're authenticated.
- **Two transports, one binary** — MCP server (default) for AI agents; `twikit-mcp call <tool>` CLI for shells.
- **Vendored [twikit](https://github.com/d60/twikit)** with project-specific defensive patches.

## Where to go

- **[CLI mode](cli.md)** — subcommands, type coercion, exit codes, examples.
- **[MCP Tools API](api.md)** — auto-generated reference: every tool's signature + docstring + CLI example, kept in sync with code.
- **[Technical design](TECHNICAL.md)** — internals (currently 中文 only — translation welcome).
- **[Vendoring twikit](VENDORING.md)** — every patch and the issue that motivated it (currently 中文 only).
- **[GitHub repo](https://github.com/tangivis/twitter-mcp)** — README has full install / quickstart in three languages.

## Quick install

```bash
# 1. Drop your X cookies into ~/.config/twitter-mcp/cookies.json
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json <<'EOF'
{"ct0": "...", "auth_token": "..."}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json

# 2. Install (recommended for daily use)
uv tool install twikit-mcp

# 3. Register with Claude Code
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

Use `uv tool upgrade twikit-mcp` to update; full alternatives (uvx / pip / pipx) on the [GitHub README](https://github.com/tangivis/twitter-mcp#readme).
