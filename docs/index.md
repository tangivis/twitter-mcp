# twikit-mcp

**Twitter/X MCP server — no API key needed.**

[![PyPI](https://img.shields.io/pypi/v/twikit-mcp)](https://pypi.org/project/twikit-mcp/)
[![CI](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tangivis/twitter-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tangivis/twitter-mcp/blob/main/LICENSE)

An [MCP](https://modelcontextprotocol.io/) server that lets Claude (or any MCP-compatible AI agent) interact with Twitter/X using browser cookies. No Twitter API key, no developer-account approval, no monthly bill.

## What you get

- **57 tools** covering tweets, users, lists, communities, scheduled tweets + polls, DMs, articles, search, trends, notifications.
- **Browser-cookie auth** — copy `ct0` + `auth_token` from your X session, and you're authenticated.
- **Single binary** — `pip install twikit-mcp` or `uvx twikit-mcp`. No background services.
- **Vendored [twikit](https://github.com/d60/twikit)** with project-specific defensive patches (see [Vendoring](VENDORING.md)).

## Where to go next

- **[MCP Tools API](api.md)** — auto-generated reference of all 57 tools, with arg signatures and behavior. Read this if you want to know what a specific tool does.
- **[Technical design](TECHNICAL.md)** — how the server works internally, how tool output shapes are kept compact, etc.
- **[Vendoring twikit](VENDORING.md)** — every patch applied to the vendored copy, with the issue that motivated it.
- **[Repo on GitHub](https://github.com/tangivis/twitter-mcp)** — README has install / quickstart in English / 中文 / 日本語.

## Quick install

```bash
# Copy ct0 + auth_token from x.com cookies, then:
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json <<'EOF'
{"ct0": "...", "auth_token": "..."}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json

# Install + register with Claude Code:
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- uvx twikit-mcp
```

Full instructions including 中文 / 日本語 versions are on [the GitHub README](https://github.com/tangivis/twitter-mcp#readme).
