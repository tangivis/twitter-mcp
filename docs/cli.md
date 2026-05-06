# CLI mode

`twikit-mcp` is a dual-mode binary: same install, two transports.

| Mode | Command | When |
|---|---|---|
| **MCP server** (default) | `twikit-mcp` or `twikit-mcp serve` | Inside an AI agent (Claude Code, Cursor, Cline, …). The LLM sends JSON-RPC over stdio. |
| **CLI** | `twikit-mcp list` / `twikit-mcp call <tool> …` | Shell scripts, automation, debugging. |

Both modes share the same cookies file (`~/.config/twitter-mcp/cookies.json`) and the same 57 tools.

## Subcommands

### `serve` (default)

Run the MCP server over stdio. This is the default when no subcommand is given — every existing `mcp.json` / Claude Code / Cursor config keeps working unchanged.

```bash
twikit-mcp           # default — MCP server
twikit-mcp serve     # explicit, same behavior
```

Reads `~/.config/twitter-mcp/cookies.json` (or wherever `TWITTER_COOKIES` env var points). Speaks JSON-RPC 2.0 on stdin/stdout.

### `list`

Print the names of all registered MCP tools, one per line, sorted.

```bash
$ twikit-mcp list
add_list_member
block_user
bookmark_tweet
…
unmute_user
vote
```

Useful in scripts: `twikit-mcp list | grep ^get_` to find every read-only tool.

### `call <tool> [key=value …]`

Invoke one tool from the shell and print its JSON output to stdout. Args use `key=value` form; the tool's Python signature drives type coercion.

```bash
$ twikit-mcp call get_user_info screen_name=elonmusk
{"id":"44196397","screen_name":"elonmusk","name":"Elon Musk", …}

$ twikit-mcp call search_tweets query=AI count=5 product=Top
[…]

$ twikit-mcp call get_tweet tweet_id=20 | jq .text
"just setting up my twttr"
```

#### Type coercion

CLI args are always strings; we cast them to the tool's annotated types:

| Annotation | Coercion | Examples |
|---|---|---|
| `str` | passthrough | `text="hello world"` |
| `int` | `int(value)` | `count=5` |
| `float` | `float(value)` | (rare in this project) |
| `bool` | loose: `true / 1 / yes / on` (case-insensitive) → `True`, anything else → `False` | `is_private=true` |
| `Optional[X]` / `X \| None` | unwrap to `X`; **empty string → `None`** explicitly | `cursor=` (forces None) |
| Anything else | passthrough as raw string | (tool's own validation runs next) |

#### KV splitting

Each `key=value` token is split on the **first** `=` only. URLs, base64 strings, JWT tokens with extra `=` survive intact:

```bash
twikit-mcp call get_tweet tweet_id="https://x.com/user/status/1234567890"
```

#### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success — tool returned, JSON written to stdout. |
| `1` | Argparse / shell-level error (e.g. missing required arg, bad subcommand). |
| `2` | `ToolError` — tool's own validation rejected the input or the underlying twikit call typed an exception (`TooManyRequests`, `NotFound`). Error message goes to stderr. |
| Other | Uncaught exception. Indicates a bug; please file an issue with the traceback. |

## Tips

### Pipe to `jq`

The output is always valid JSON, so `jq` works natively:

```bash
twikit-mcp call get_user_info screen_name=elonmusk | jq .followers_count

# follower count of every user in a list
twikit-mcp call get_user_info screen_name=elonmusk | jq '.followers_count, .following_count'
```

### Cron a scheduled poll

```bash
# Every Monday 10:00, snapshot trending topics
0 10 * * 1   /usr/local/bin/twikit-mcp call get_trends category=trending count=20 \
             > "$HOME/trends/$(date +%F).json"
```

### Discover a tool's args

The CLI lists valid args when you give an unknown one:

```bash
$ twikit-mcp call get_user_info bogus=x
Unknown arg `bogus` for tool `get_user_info`. Valid args: ['screen_name', 'user_id']
```

For deeper help — including full docstrings + return shape — see the [MCP Tools API reference](api.md), which is auto-generated from the same docstrings the LLM sees over MCP.
