# Local XChat reader

XChat is X's end-to-end encrypted replacement for legacy DMs. Once a
conversation is upgraded, twikit's legacy `dm_conversation` endpoint may return
no rows even though the conversation is visible on x.com. `get_dm_history`
therefore classifies a confirmed upgrade as `[xchat_encrypted]` and does not
retry a permanently incompatible endpoint.

## Architecture

The reader is local-only:

1. Playwright opens a dedicated persistent Chromium profile.
2. You complete X login, device registration, and any passcode prompt yourself.
3. X's web client retains its cookies, IndexedDB state, and device key material
   in that profile and performs the actual decryption.
4. The reader captures Chromium's accessibility tree over CDP. Conversation
   links, message items, text, and times come from semantic roles. Message
   direction may use bounds and is labelled `layout-heuristic` when it does.

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

## Setup

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

`status` never spends a passcode attempt. `doctor` is safe to attach to a bug
report because it reports counts, route, state, and profile path—not decrypted
content or credentials.
