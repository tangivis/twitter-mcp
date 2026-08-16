"""Failure modes of the local XChat reader (issue #118).

Two distinct conditions, because the fix differs:

`XChatUnavailable` — there is nothing to read. No store configured, no
browser profile found, or the configured path does not exist. The user
needs to open XChat and let it sync, or point the config at the right
file.

`XChatExtractionFailed` — a store was found but could not be read as
XChat. Wrong file, corrupt database, unexpected schema, or no rows for
the requested conversation.

Both are translated to `ToolError` at the MCP boundary so a client sees
an actionable message rather than a traceback.
"""

from __future__ import annotations


class XChatError(Exception):
    """Base class for every local-XChat failure."""


class XChatUnavailable(XChatError):
    """No readable XChat store is configured or discoverable."""


class XChatExtractionFailed(XChatError):
    """A store was located but its contents could not be read."""


__all__ = ["XChatError", "XChatExtractionFailed", "XChatUnavailable"]
