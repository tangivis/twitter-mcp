# twikit-mcp

**Twitter/X MCP server + CLI — no API key needed.**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

An [MCP](https://modelcontextprotocol.io/) server that lets Claude (or any MCP-compatible AI agent) interact with Twitter/X using browser cookies. The same `twikit-mcp` binary doubles as a CLI for shell scripts and debugging.

## What's new in 0.1.27

- **Download tweet videos via yt-dlp** — new `download_tweet_video` MCP tool + `twikit-mcp video <id>` CLI subcommand. Saves to `~/Downloads/twikit-mcp/` by default. Authenticated via your existing `cookies.json`. Requires [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) on PATH (`uv tool install yt-dlp`); `ffmpeg` only needed if you pass a separate-stream format like `bestvideo+bestaudio`. (closes #84)

Upgrade with `uv tool upgrade twikit-mcp` (or `pip install --upgrade twikit-mcp`).

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
