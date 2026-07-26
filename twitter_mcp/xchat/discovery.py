"""Discover XChat's SQLite store in local Chromium browser profiles.

Discovery is content-free: candidate files are identified by SQLite's header
and the required table names in ``sqlite_master``. Message rows and key material
are never queried. Browser profiles are never copied or modified.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from twitter_mcp.xchat.errors import XChatUnavailable

SUPPORTED_BROWSERS = ("chrome", "chromium", "edge", "brave", "aside")
_ALIASES = {
    "google-chrome": "chrome",
    "microsoft-edge": "edge",
    "brave-browser": "brave",
}
_SQLITE_HEADER = b"SQLite format 3\x00"
_REQUIRED_TABLES = frozenset(
    {"dm_conversation", "dm_entry", "dm_user", "dm_key_material"}
)


def _default_roots() -> dict[str, Path]:
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
        return {
            "chrome": base / "Google" / "Chrome",
            "chromium": base / "Chromium",
            "edge": base / "Microsoft Edge",
            "brave": base / "BraveSoftware" / "Brave-Browser",
            "aside": base / "Aside",
        }
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return {
            "chrome": local / "Google" / "Chrome" / "User Data",
            "chromium": local / "Chromium" / "User Data",
            "edge": local / "Microsoft" / "Edge" / "User Data",
            "brave": local / "BraveSoftware" / "Brave-Browser" / "User Data",
        }
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return {
        "chrome": config / "google-chrome",
        "chromium": config / "chromium",
        "edge": config / "microsoft-edge",
        "brave": config / "BraveSoftware" / "Brave-Browser",
    }


def _profile_directories(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.iterdir()
            if path.is_dir()
            and (
                path.name == "Default"
                or path.name.startswith("Profile ")
                or path.name == "Guest Profile"
            )
        ),
        key=lambda path: (path.name != "Default", path.name),
    )


def _sqlite_schema_matches(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            if stream.read(len(_SQLITE_HEADER)) != _SQLITE_HEADER:
                return False
        uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as con:
            tables = {
                str(row[0])
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        return _REQUIRED_TABLES <= tables
    except (OSError, sqlite3.DatabaseError):
        return False


def _last_updated(path: Path) -> str:
    return (
        datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _scan_profile(profile_dir: Path) -> tuple[list[Path], bool]:
    filesystem = profile_dir / "File System"
    try:
        filesystem.stat()
    except FileNotFoundError:
        return [], False
    except PermissionError:
        return [], True
    if not filesystem.is_dir():
        return [], False

    denied = False

    def onerror(exc: OSError) -> None:
        nonlocal denied
        if isinstance(exc, PermissionError):
            denied = True

    matches: list[Path] = []
    for directory, _, filenames in os.walk(filesystem, onerror=onerror):
        for filename in filenames:
            candidate = Path(directory) / filename
            if _sqlite_schema_matches(candidate):
                matches.append(candidate.resolve())
    return matches, denied


def discover_xchat_databases(
    browser: str = "auto",
    profile: str | None = None,
    *,
    roots: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Return sanitized XChat database matches from local browser profiles.

    ``roots`` is an injectable complete root map used by tests and embedders.
    Normal callers omit it to use platform-specific profile locations.
    """
    requested = _ALIASES.get(browser.strip().lower(), browser.strip().lower())
    if requested != "auto" and requested not in SUPPORTED_BROWSERS:
        supported = ", ".join(SUPPORTED_BROWSERS)
        raise XChatUnavailable(
            f"Unsupported browser {browser!r}. Supported browsers: {supported}. "
            "Safari discovery is not implemented yet."
        )

    resolved_roots = (
        {name: Path(path).expanduser() for name, path in roots.items()}
        if roots is not None
        else _default_roots()
    )
    browser_names = list(resolved_roots) if requested == "auto" else [requested]
    matches: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for browser_name in browser_names:
        root = resolved_roots.get(browser_name)
        if root is None:
            continue
        try:
            root.stat()
            if profile:
                selected = root / profile
                selected.stat()
                profile_dirs = [selected] if selected.is_dir() else []
            else:
                profile_dirs = _profile_directories(root)
        except FileNotFoundError:
            continue
        except PermissionError:
            errors.append(
                {
                    "browser": browser_name,
                    "path": str(root),
                    "error": "permission_denied",
                }
            )
            continue

        browser_denied = False
        for profile_dir in profile_dirs:
            candidates, denied = _scan_profile(profile_dir)
            browser_denied = browser_denied or denied
            for candidate in candidates:
                try:
                    matches.append(
                        {
                            "browser": browser_name,
                            "profile": profile_dir.name,
                            "database_path": str(candidate),
                            "database_size": candidate.stat().st_size,
                            "last_updated": _last_updated(candidate),
                        }
                    )
                except OSError:
                    continue
        if browser_denied:
            errors.append(
                {
                    "browser": browser_name,
                    "path": str(root),
                    "error": "permission_denied",
                }
            )

    matches.sort(key=lambda row: str(row["last_updated"]), reverse=True)
    state = "found" if matches else ("permission_denied" if errors else "not_found")
    return {
        "state": state,
        "requested_browser": requested,
        "requested_profile": profile,
        "matches": matches,
        "errors": errors,
    }


def resolve_xchat_database_path(
    database_path: Path | str | None,
    browser: str | None,
    profile: str | None,
) -> Path | None:
    """Resolve explicit-path or browser discovery configuration to one file."""
    if database_path:
        return Path(database_path).expanduser().resolve()
    if not browser:
        return None

    report = discover_xchat_databases(browser=browser, profile=profile)
    matches = report["matches"]
    if len(matches) == 1:
        return Path(matches[0]["database_path"])
    if not matches and report["state"] == "permission_denied":
        raise XChatUnavailable(
            "Browser profile access was denied. Grant the MCP host Full Disk "
            "Access on macOS, then restart it and retry."
        )
    if not matches:
        requested = browser + (f" profile {profile!r}" if profile else "")
        raise XChatUnavailable(
            f"No local XChat database was found for {requested}. Open XChat in "
            "that browser, unlock it, and let it finish syncing."
        )
    choices = ", ".join(f"{row['browser']}/{row['profile']}" for row in matches[:5])
    raise XChatUnavailable(
        "Multiple local XChat databases matched "
        f"({choices}). Set XCHAT_BROWSER_PROFILE or XCHAT_DATABASE_PATH."
    )


__all__ = [
    "SUPPORTED_BROWSERS",
    "discover_xchat_databases",
    "resolve_xchat_database_path",
]
