# Install + register with your MCP client

Three steps. Pick your client at step 3.

## 1. Install the binary

```bash
uv tool install twikit-mcp
```

Why `uv tool install`: drops `twikit-mcp` on your `PATH` in an isolated env (no dependency conflicts), instant subsequent startups, single command to upgrade later (`uv tool upgrade twikit-mcp`).

If you don't have `uv`: [install it](https://docs.astral.sh/uv/getting-started/installation/) (one curl line on macOS / Linux). Or use `pipx` / `pip` — see the [README "Choose your install"](https://github.com/tangivis/twitter-mcp#choose-your-install) for those alternatives.

## 2. Drop your X cookies

Log into [x.com](https://x.com) in a browser → DevTools (F12) → **Application** → **Cookies** → `https://x.com`. Copy `ct0` and `auth_token`.

```bash
mkdir -p ~/.config/twitter-mcp
cat > ~/.config/twitter-mcp/cookies.json <<'EOF'
{"ct0": "...", "auth_token": "..."}
EOF
chmod 600 ~/.config/twitter-mcp/cookies.json
```

## 3. Register with your client

Same JSON shape (`mcpServers` block) for every client; only the **config file location** differs. Replace `/home/YOU` with your actual home path.

### Claude Code

CLI command — no JSON editing:

```bash
claude mcp add twitter -s user \
  -e "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json" \
  -- twikit-mcp
```

### Claude Desktop

| OS | Config file |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Add (create the file if it doesn't exist):

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

Restart Claude Desktop.

### Cursor

Edit `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (per-project):

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

Cursor reloads automatically; no restart needed.

### Windsurf

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

Restart Windsurf.

### Cline (VS Code extension)

Open the Cline panel → ⚙️ → **MCP Servers** → **Edit MCP Settings**. Cline auto-reloads on save.

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

### opencode

Edit `~/.config/opencode/config.json`:

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

### Any other MCP client

`twikit-mcp` is a standard **stdio** MCP server. Whatever your client's config file looks like, the JSON shape is the same:

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json"
      }
    }
  }
}
```

Some clients use `mcp.servers` instead of `mcpServers`, or wrap it under a different top-level key — check your client's docs. The `command` and `env` fields are universal.

### OpenClaw

OpenClaw can save `twikit-mcp` as an outbound MCP server for OpenClaw-managed agent runs:

```bash
openclaw mcp add twitter \
  --command twikit-mcp \
  --env "TWITTER_COOKIES=$HOME/.config/twitter-mcp/cookies.json"

openclaw mcp doctor twitter --probe
```

Use a tool filter for read-only workflows:

```bash
openclaw mcp tools twitter \
  --include 'get_tweet,search_tweets,get_user_info,get_user_tweets,get_tweet_replies,get_trends'
```

If the same OpenClaw workflow also needs API-backed TweetClaw jobs, install the TweetClaw plugin separately:

```bash
openclaw plugins install npm:@xquik/tweetclaw@1.6.31
openclaw plugins inspect tweetclaw --runtime --json
```

Keep `twikit-mcp` responsible for cookie-backed MCP actions. Use TweetClaw for separate approval-reviewed workflows such as follower export, search tweet replies, media workflows, DMs, monitors, webhooks, giveaway draws, and post or reply jobs. Keep cookie paths and API keys in MCP or OpenClaw config, not prompts, docs, logs, or issue comments.

## Verify

In your client, ask:

> Search tweets about AI

The agent should call `search_tweets` and return results. If you get a permissions error, your `cookies.json` path is wrong; double-check `TWITTER_COOKIES` in the config above.

## Upgrading

```bash
uv tool upgrade twikit-mcp
```

That's it — your client picks up the new binary on next launch.
