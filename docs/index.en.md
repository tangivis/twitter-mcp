# twikit-mcp

**Twitter/X MCP server + CLI — no API key needed.**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

An [MCP](https://modelcontextprotocol.io/) server that lets Claude (or any MCP-compatible AI agent) interact with Twitter/X using browser cookies. The same `twikit-mcp` binary doubles as a CLI for shell scripts and debugging.

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
