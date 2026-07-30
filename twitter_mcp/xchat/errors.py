"""Error types for the XChat path.

These are deliberately distinct from `ToolError` so the MCP layer can map each
failure to an *actionable* message. The failure that matters most is
`XChatLoginRequired` vs `XChatLocked`: the first means "run `twikit-mcp xchat
login`", the second means "the session is alive but needs the PIN" — two very
different fixes that both look like "no messages" if you conflate them.
"""


class XChatError(Exception):
    """Base class for all XChat failures."""


class XChatUnavailable(XChatError):
    """Playwright (or its browser) is not installed."""


class XChatLoginRequired(XChatError):
    """No usable logged-in profile; the user must run the interactive login."""


class XChatLocked(XChatError):
    """The client is logged in but the encrypted store is PIN-locked."""


class XChatPinRejected(XChatLocked):
    """A PIN was supplied and X rejected it."""


class XChatNoPin(XChatLocked):
    """A PIN is required but none could be obtained (no env value, no prompt)."""


class XChatExtractionFailed(XChatError):
    """The page loaded but no known selector matched.

    Almost always means X shipped a DOM change. `twikit-mcp xchat doctor`
    dumps what was actually on the page so selectors can be re-pinned.
    """
