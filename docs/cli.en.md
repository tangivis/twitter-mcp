# CLI mode

`twikit-mcp` is a dual-mode binary: same install, two transports.

| Mode | Command | When |
|---|---|---|
| **MCP server** (default) | `twikit-mcp` or `twikit-mcp serve` | Inside an AI agent (Claude Code, Cursor, Cline, …). LLM sends JSON-RPC over stdio. |
| **CLI** | `twikit-mcp list` / `twikit-mcp call <tool> …` | Shell scripts, automation, debugging. |

Both share the same cookies file (`~/.config/twitter-mcp/cookies.json`) and the same 57 tools.

## Subcommands

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
