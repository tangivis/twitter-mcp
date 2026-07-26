# Local XChat reader

XChat is X's end-to-end encrypted replacement for legacy DMs. Once a
conversation is upgraded, twikit's legacy `dm_conversation` endpoint may return
no rows even though the conversation is visible on x.com. `get_dm_history`
therefore classifies a confirmed upgrade as `[xchat_encrypted]` and does not
retry a permanently incompatible endpoint.

## Architecture

The reader is local-only. Its preferred path is the web client's local database:

1. You log in, register the device, and unlock XChat in a normal local browser.
2. X's web client performs E2EE decryption and stores the synced conversation
   state in its origin-private SQLite filesystem.
3. Configure `XCHAT_DATABASE_PATH` with that SQLite file's absolute path.
4. The reader opens it with SQLite `mode=ro&immutable=1` and selects only
   metadata and `dm_entry.plain_text`. It never selects key bytes, sends a
   message, marks a thread read, or launches browser automation.

The source browser remains responsible for future sync and decryption. If it is
not running or X has not synced, database results may be stale. The database
file must not be copied while the browser is writing it.

When no database path is configured, the original Playwright reader remains a
fallback: it opens a dedicated persistent Chromium profile and extracts
rendered plaintext from Chromium's accessibility tree over CDP.

CSS selectors remain only as legacy safety fallbacks. `xchat doctor` emits
content-free role counts and the route; it never prints message text.

Safari/WebKit automation is not used because its automation session does not
share a durable paired profile. A Playwright/Safari hybrid would split the
session and key material across two browser processes without improving the
security boundary.

[`chat-xdk`](https://github.com/xdevplatform/chat-xdk) has now shipped (v0.4.3
when this design was verified). It supplies XChat cryptography, but its examples
still require an authenticated transport such as OAuth/Activity Stream. It does
not provide a free drop-in transport for this cookie-authenticated MCP server,
so the browser remains the registered device and decryption boundary.

## Direct database setup

Add the discovered local XChat database path to a gitignored `.env.local`:

```bash
XCHAT_DATABASE_PATH=/absolute/path/to/chat.db
twikit-mcp xchat status
twikit-mcp xchat doctor
twikit-mcp xchat list
```

`status`, `doctor`, `list`, and `history` use the database exclusively when
this variable is set; an invalid configured database produces an error instead
of silently launching Playwright.

## Browser fallback setup

```bash
pip install 'twikit-mcp[xchat]'
playwright install chromium
twikit-mcp xchat login
twikit-mcp xchat status
```

`login` is visible and waits for you to complete account authentication and the
XChat passcode flow. Later MCP reads reuse the dedicated profile headlessly:

- `xchat_status`
- `xchat_list_conversations`
- `xchat_get_history`

If X periodically locks the local store, set `XCHAT_PIN` in a gitignored
`.env.local`, or choose `XCHAT_PIN_PROMPT=tty|web`. A passcode is attempted at
most once per process. A failure is never retried automatically because X has a
finite recovery limit.

## Recovering from login rate limits

Do not repeatedly retry a clean browser profile. The preferred recovery path is
to bootstrap the dedicated profile from an existing authenticated cookie file:

```bash
chmod 600 ~/.config/twitter-mcp/cookies.json
XCHAT_COOKIE_FILE=~/.config/twitter-mcp/cookies.json \
  twikit-mcp xchat login
```

This opt-in import copies only `auth_token` and `ct0`, and only during the
visible `login` command. It grants the dedicated XChat profile persistent access
to the X account. Confirm that security consequence before setting the variable.
Do not copy or automate a live normal-browser profile: browser databases can be
locked, partially copied, or tied to OS keychain state.

If X still requests device registration or a passcode, complete those steps in
the visible dedicated-profile window. Never put cookies, passcodes, or browser
profile data in git.

## Diagnostics

```bash
twikit-mcp xchat status
twikit-mcp xchat doctor
twikit-mcp xchat list
twikit-mcp xchat history CONVERSATION_ID -n 50
```

`status` never spends a passcode attempt. In database mode, `doctor` reports
only schema/file/count metadata, including the number of key-material rows but
never their tags or bytes. In browser mode it reports content-free role counts.
