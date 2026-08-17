"""Local, read-only XChat reader (issue #118).

XChat is X's end-to-end-encrypted DM system. The legacy DM API cannot
return encrypted bodies, so `get_dm_history` reports them as unreadable
(#104). X's web client, however, decrypts conversations locally and
stores the plaintext in a SQLite database — this package reads that file
and nothing else.

Deliberately narrow: stdlib only, no network, no credentials, no browser
automation, and no write path of any kind. Configuration comes from the
process environment, matching how the rest of the server is configured:

    XCHAT_DATABASE_PATH     explicit path to the SQLite file
    XCHAT_BROWSER           auto | chrome | chromium | edge | brave | aside
    XCHAT_BROWSER_PROFILE   profile directory name, e.g. "Profile 2"

With none of these set the feature reports itself unavailable and the
rest of the server is unaffected.
"""

from __future__ import annotations

import os

from twitter_mcp.xchat.database import XChatDatabase
from twitter_mcp.xchat.discovery import (
    SUPPORTED_BROWSERS,
    discover_xchat_databases,
    resolve_xchat_database_path,
)
from twitter_mcp.xchat.errors import (
    XChatError,
    XChatExtractionFailed,
    XChatUnavailable,
)

# Discovery only runs when the user opted in by naming a browser; an
# unconfigured install never walks the filesystem looking for profiles.
_DEFAULT_BROWSER = None


def env_config() -> dict[str, str | None]:
    """The three settings this feature reads, straight from the environment."""
    return {
        "database_path": os.environ.get("XCHAT_DATABASE_PATH") or None,
        "browser": os.environ.get("XCHAT_BROWSER") or _DEFAULT_BROWSER,
        "profile": os.environ.get("XCHAT_BROWSER_PROFILE") or None,
    }


def database_from_env() -> XChatDatabase | None:
    """Build a reader from the environment, or None if nothing is configured.

    Raises `XChatUnavailable` when the user *did* configure a browser but
    discovery could not settle on exactly one database — silence there
    would be worse than an actionable error.
    """
    config = env_config()
    path = resolve_xchat_database_path(
        config["database_path"], config["browser"], config["profile"]
    )
    return XChatDatabase(path) if path else None


__all__ = [
    "SUPPORTED_BROWSERS",
    "XChatDatabase",
    "XChatError",
    "XChatExtractionFailed",
    "XChatUnavailable",
    "database_from_env",
    "discover_xchat_databases",
    "env_config",
    "resolve_xchat_database_path",
]
