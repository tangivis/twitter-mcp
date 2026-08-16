# XChat (encrypted DMs)

XChat is X's end-to-end-encrypted direct-message system. The regular DM
API cannot return encrypted message bodies — `get_dm_history` reports
that in its `warnings` field rather than pretending a conversation is
empty.

X's own web client decrypts your conversations locally and stores the
plaintext in a SQLite database. `twikit-mcp` reads that file. The browser
did the decryption; this only opens the result.

## What this is, precisely

- **Local only.** No network request is made. No X API, no paid API, no
  browser automation.
- **Read-only.** The database is opened with SQLite's `mode=ro` and
  `immutable=1` flags, so it takes no locks and writes no `-wal`/`-shm`
  sidecars next to your browser profile. Every statement is a `SELECT`.
- **No credentials.** No PIN, no OAuth token, no encryption key. Your
  `cookies.json` is not used or read by these tools.
- **Reading here does not mark anything read on X.** Nothing is sent to
  X at all.
- **Encryption keys are never read.** The key-material table is counted
  for diagnostics and otherwise untouched.

## Requirements

Open XChat in a Chromium-family browser, unlock it, and let it finish
syncing. Supported: Chrome, Chromium, Edge, Brave, Aside. Safari is not
supported — WebKit does not use Chromium's storage layout.

## Configuration

Set these in your MCP client's `env` block, next to `TWITTER_COOKIES`:

| Variable | Meaning |
|---|---|
| `XCHAT_BROWSER` | `auto`, or one of `chrome` / `chromium` / `edge` / `brave` / `aside` |
| `XCHAT_BROWSER_PROFILE` | Profile directory name, e.g. `Default` or `Profile 2` |
| `XCHAT_DATABASE_PATH` | Explicit path to the SQLite file — skips discovery entirely |

With none of these set, XChat tools report `not_configured` and list
what was found on your machine, so you can pick one. The rest of the
server is unaffected either way.

```json
{
  "mcpServers": {
    "twitter": {
      "command": "twikit-mcp",
      "env": {
        "TWITTER_COOKIES": "/home/YOU/.config/twitter-mcp/cookies.json",
        "XCHAT_BROWSER": "chrome"
      }
    }
  }
}
```

If discovery finds several databases it refuses to guess and asks you to
name one — reading the wrong profile would silently return a different
account's conversations.

On macOS the MCP host needs **Full Disk Access** to read a browser
profile. Grant it in System Settings → Privacy & Security, restart the
host, and retry; the tools say so explicitly when access is denied.

## Tools

| Tool | What it does |
|---|---|
| `xchat_status` | Whether a store is readable, where it is, how many conversations — plus discovery results when nothing is configured |
| `xchat_list_conversations` | Conversations newest-first with a preview of the latest message |
| `xchat_get_history` | One conversation's messages, oldest-first |

Messages that carry only an attachment render as `[image attachment]`
rather than empty text, so an agent never mistakes an image for silence.

## Limitations

- **Only what your browser has synced.** This reads a local cache, not
  X's servers. Conversations the browser hasn't fetched aren't there.
- **Attachment contents are not available** — only a type placeholder.
- **This depends on X's internal database schema**, which X can change
  without notice. When that happens the tools fail with a clear
  "missing required XChat tables" error rather than returning wrong
  data. It is the same class of fragility as the vendored twikit
  parsing; see [issue #118](https://github.com/tangivis/twitter-mcp/issues/118).

## Privacy

These tools return private message content into your agent's context.
That is the entire point, but it is worth being deliberate about: the
conversations go wherever your MCP client sends its context. The tool
docstrings are marked so a well-behaved agent treats them as sensitive.
