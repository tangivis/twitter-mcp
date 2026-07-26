"""XChat (X's end-to-end encrypted DMs) support — local-only, client-driven.

Why this package exists and why it is shaped the way it is
----------------------------------------------------------
XChat messages are end-to-end encrypted. The decryption key is derived on a
*registered device*, unlocked by the account PIN, and X has published neither
the key-derivation protocol nor the `chat-xdk` SDK. There is therefore no
supported way — free or paid, including X's own paid API — to decrypt an
XChat payload from a cookie jar or an HTTP client. `twikit` (and every tool
built on it, including the rest of this repo) talks to the *legacy* v1.1 DM
endpoint, which silently stops returning a conversation once it is upgraded
to XChat.

So this package does not attempt to reimplement X's cryptography. It drives a
real, locally-persisted X web client — the one piece of software that legitimately
holds your key — and reads the plaintext that client has already decrypted.
Concretely:

* `session.py` keeps a persistent browser profile on disk, the same way
  whatsmeow keeps a paired WhatsApp session. You log in once; the profile is
  reused for every later run.
* `pin.py` supplies the unlock PIN when X asks for it: from `.env.local`
  first, otherwise by prompting on the terminal or a loopback-only web page.
* `reader.py` turns the decrypted DOM into structured conversations/messages.

Everything stays on this machine: the profile directory, the PIN, and the
plaintext. Nothing is sent anywhere except to x.com by the browser itself.
"""

from twitter_mcp.xchat.config import XChatSettings, load_settings
from twitter_mcp.xchat.errors import (
    XChatError,
    XChatLocked,
    XChatLoginRequired,
    XChatUnavailable,
)

__all__ = [
    "XChatSettings",
    "load_settings",
    "XChatError",
    "XChatLoginRequired",
    "XChatLocked",
    "XChatUnavailable",
]
