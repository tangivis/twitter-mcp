# CLI mode

`twikit-mcp` is a multi-mode binary. Same install, three flavors:

| Mode | Command | When |
|---|---|---|
| **MCP server** (default) | `twikit-mcp` or `twikit-mcp serve` | Inside an AI agent (Claude Code, Cursor, Cline, …). LLM sends JSON-RPC over stdio. |
| **Human-friendly CLI** | `twikit-mcp tweet 20`, `twikit-mcp user elonmusk`, etc. | You're at a shell, you want to read a tweet / profile / timeline. Output is plain text, native unicode. |
| **Machine CLI** | `twikit-mcp list` / `twikit-mcp call <tool> key=value …` | Shell scripts, automation, debugging. Raw JSON output, every one of the 57 tools available. |

All three share the same cookies file (`~/.config/twitter-mcp/cookies.json`).

## Human-friendly subcommands

Pretty-printed text output, positional args, no JSON. Five subcommands cover the common "I want to read X" cases:

```bash
twikit-mcp tweet 20                       # one tweet pretty-printed
twikit-mcp tweet https://x.com/jack/status/20  # URL works too
twikit-mcp user elonmusk                  # one profile
twikit-mcp tl 10                          # last 10 from your home timeline
twikit-mcp search "AI" 5                  # 5 top search results
twikit-mcp trends 20                      # top 20 trending topics
```

Sample output in a terminal (0.1.24+ Rich-rendered card with clickable links):

```text
╭──────────────────────────────────────────────────────────────────────────────╮
│ Pathfinder Sports · @pathfinderSport                                         │
│ Sat Feb 21 16:55:22 +0000 2009                                               │
│ ──────────────────────────────────────────────────────────────────────────── │
│ Άρσεναλ - Σάντερλαντ: (X) 0-0 τελικό                                         │
│ ──────────────────────────────────────────────────────────────────────────── │
│ ❤ 7,269    🔁 5,473                                                          │
│ https://x.com/pathfinderSport/status/1234567890                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

In a real terminal: the author handle is bold cyan, the timestamp is dim, `❤` is red, `🔁` is green, and the URL is wrapped in an OSC 8 escape so cmd-clicking opens it in your browser (works in iTerm2, kitty, WezTerm, Windows Terminal, gnome-terminal ≥ 3.36). Emoji and CJK lines are width-correct — Rich's cell-aware measurement is used for padding, no border drift.

Width is clamped to your terminal columns (between 60 and 100). Piping to a file or another command, or setting `NO_COLOR=1`, auto-falls-back to byte-stable plain text — same shape as 0.1.22, safe for `jq`/`grep`/diffing:

```text
@pathfinderSport · Pathfinder Sports
Άρσεναλ - Σάντερλαντ: (X) 0-0 τελικό
❤ 7,269  🔁 5,473  · Sat Feb 21 16:55:22 +0000 2009
https://x.com/pathfinderSport/status/1234567890
```

These are wrappers over the same MCP tools; if you need different args (`product=Latest`, custom `cursor`, etc.), drop down to `call`.

## Machine subcommands

### `serve` (default)

Run the MCP server over stdio. Default when no subcommand given — every existing `mcp.json` / Claude Code / Cursor config keeps working unchanged.

```bash
twikit-mcp           # default — MCP server
twikit-mcp serve     # explicit
```

### `list`

Print all registered tool names, sorted, one per line.

```bash
$ twikit-mcp list
add_list_member
block_user
…
vote
```

### `call <tool> [key=value …]`

Invoke one tool, print its JSON output.

```bash
$ twikit-mcp call get_user_info screen_name=elonmusk
{"id":"44196397","screen_name":"elonmusk", …}

$ twikit-mcp call search_tweets query=AI count=5 product=Top
[…]

$ twikit-mcp call get_tweet tweet_id=20 | jq .text
"just setting up my twttr"
```

## Type coercion

CLI args are strings; we cast to the tool's annotated types:

| Annotation | Coercion |
|---|---|
| `str` | passthrough |
| `int` / `float` | `int(value)` / `float(value)` |
| `bool` | loose: `true / 1 / yes / on` (case-insensitive) → `True`; else `False` |
| `Optional[X]` / `X \| None` | unwrap to `X`; **empty string → `None`** explicitly |
| anything else | passthrough as raw string |

KV split is on the **first** `=` only — URLs / base64 / JWTs with extra `=` survive.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Argparse / usage error |
| `2` | `ToolError` (validation rejected the input or twikit raised typed exception) |
| Other | Uncaught exception — bug, please file an issue |

## Tips

```bash
# Pipe to jq
twikit-mcp call get_user_info screen_name=elonmusk | jq .followers_count

# Cron a snapshot
0 10 * * 1   /usr/local/bin/twikit-mcp call get_trends category=trending count=20 \
             > "$HOME/trends/$(date +%F).json"

# Discover args via 'unknown arg' error
$ twikit-mcp call get_user_info bogus=x
Unknown arg `bogus` for tool `get_user_info`. Valid args: ['screen_name', 'user_id']
```

---

## All tools (machine CLI)

--8<-- "docs/_cli_tools.en.md"
