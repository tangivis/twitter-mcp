"""`twikit-mcp xchat ...` — pairing and debugging commands.

`status`, `list`, `history`, and `doctor` read the configured local database
without launching a browser. Without a database path they fall back to the
paired Playwright profile. `login` is the only command that deliberately opens
a visible browser because pairing is a human step.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from twitter_mcp.xchat.config import load_settings
from twitter_mcp.xchat.discovery import SUPPORTED_BROWSERS, discover_xchat_databases
from twitter_mcp.xchat.errors import XChatError
from twitter_mcp.xchat.oauth import OAuthTokenStore, authorize
from twitter_mcp.xchat.session import (
    STATE_LOGGED_OUT,
    STATE_READY,
    XChatSession,
    profile_is_initialized,
)
from twitter_mcp.xchat.source import configured_reader

LOGIN_POLL_SECONDS = 3
LOGIN_TIMEOUT_SECONDS = 600


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


async def cmd_login(timeout_s: int = LOGIN_TIMEOUT_SECONDS) -> int:  # pragma: no cover
    settings = load_settings()
    print(
        "Opening a browser. Log in to X, then open Messages and complete any "
        "chat-PIN / device setup it asks for.\n"
        f"Profile: {settings.profile_dir}\n"
        + (
            "XCHAT_COOKIE_FILE is set: this login will copy auth_token and ct0 "
            "into the dedicated profile, granting it persistent X access.\n"
            if settings.cookie_file
            else ""
        )
        + "This window stays open until the session is confirmed."
    )
    async with XChatSession(settings=settings, headless=False) as session:
        if await session.import_login_cookies():
            print("Imported two login cookies into the dedicated profile.")
        await session._goto_messages()
        waited = 0
        while waited < timeout_s:
            state = await session.current_state()
            if state == STATE_READY:
                print("\nPaired. The profile is saved; later runs are headless.")
                return 0
            await asyncio.sleep(LOGIN_POLL_SECONDS)
            waited += LOGIN_POLL_SECONDS
        print("\nTimed out waiting for a logged-in session.")
        return 2


async def cmd_status() -> int:  # pragma: no cover - browser I/O
    settings = load_settings()
    reader = configured_reader(settings)
    if reader:
        print(_dumps(reader.status()))
        return 0
    if not profile_is_initialized(settings.profile_dir):
        print(
            _dumps(
                {
                    "state": STATE_LOGGED_OUT,
                    "profile_dir": str(settings.profile_dir),
                    "profile_exists": False,
                    "detail": "No profile yet — run `twikit-mcp xchat login`.",
                }
            )
        )
        return 2
    async with XChatSession(settings=settings) as session:
        status = await session.status()
    print(_dumps(status.to_dict()))
    return 0 if status.state == STATE_READY else 2


async def cmd_list() -> int:  # pragma: no cover - browser I/O
    settings = load_settings()
    reader = configured_reader(settings)
    if reader:
        print(_dumps(reader.list_conversations()))
        return 0
    async with XChatSession(settings=settings) as session:
        print(_dumps(await session.list_conversations()))
    return 0


async def cmd_history(conversation_id: str, limit: int) -> int:  # pragma: no cover
    settings = load_settings()
    reader = configured_reader(settings)
    if reader:
        print(_dumps(reader.get_history(conversation_id, limit)))
        return 0
    async with XChatSession(settings=settings) as session:
        print(_dumps(await session.get_history(conversation_id, limit=limit)))
    return 0


async def cmd_doctor() -> int:  # pragma: no cover - browser I/O
    """Report sanitized accessibility-tree counts — the semantic drift check."""
    settings = load_settings()
    reader = configured_reader(settings)
    if reader:
        print(_dumps(reader.doctor()))
        return 0
    async with XChatSession(settings=settings) as session:
        print(_dumps(await session.doctor()))
    return 0


async def cmd_discover(browser: str, profile: str | None) -> int:
    """Find XChat databases without reading messages or controlling a browser."""
    report = discover_xchat_databases(browser=browser, profile=profile)
    print(_dumps(report))
    return 0 if report["state"] == "found" else 2


async def cmd_oauth(no_open: bool = False) -> int:
    """Create a renewable, read-only OAuth2 PKCE grant."""
    settings = load_settings()
    if not settings.oauth_client_id:
        raise XChatError("Set XCHAT_OAUTH_CLIENT_ID before running OAuth setup.")
    message = await asyncio.to_thread(
        authorize,
        settings.oauth_client_id,
        settings.oauth_redirect_uri,
        OAuthTokenStore(settings.oauth_token_file),
        open_browser=not no_open,
    )
    print(message)
    return 0


def add_parser(subparsers) -> None:
    """Register `xchat` and its subcommands on the main CLI parser."""
    parser = subparsers.add_parser(
        "xchat",
        help="Read X's end-to-end encrypted (XChat) messages via a local session.",
        description=(
            "Read XChat from a registered web client's local decrypted store, "
            "or explicitly select the paid browser-independent chat-xdk API "
            "backend with XCHAT_BACKEND=chatxdk."
        ),
    )
    xsub = parser.add_subparsers(dest="xchat_cmd", required=True)
    xsub.add_parser("login", help="Pair this machine (opens a visible browser, once).")
    xsub.add_parser("status", help="Report session state: ready / locked / logged out.")
    xsub.add_parser("list", help="List XChat conversations.")
    p_hist = xsub.add_parser("history", help="Print one conversation's messages.")
    p_hist.add_argument("conversation_id")
    p_hist.add_argument("-n", "--limit", type=int, default=50)
    xsub.add_parser("doctor", help="Show sanitized semantic role/route diagnostics.")
    p_oauth = xsub.add_parser(
        "oauth", help="Create or replace the renewable read-only X API grant."
    )
    p_oauth.add_argument(
        "--no-open", action="store_true", help="Print the authorization URL only."
    )
    p_discover = xsub.add_parser(
        "discover",
        help="Find XChat databases in local Chromium browser profiles.",
    )
    p_discover.add_argument(
        "--browser",
        choices=("auto", *SUPPORTED_BROWSERS),
        default="auto",
        help="Browser family to scan (default: auto).",
    )
    p_discover.add_argument(
        "--profile",
        help="Optional exact browser profile directory, such as 'Default'.",
    )


def dispatch(args) -> int:  # pragma: no cover - thin async dispatch
    handlers = {
        "login": lambda: cmd_login(),
        "status": lambda: cmd_status(),
        "list": lambda: cmd_list(),
        "history": lambda: cmd_history(args.conversation_id, args.limit),
        "doctor": lambda: cmd_doctor(),
        "oauth": lambda: cmd_oauth(args.no_open),
        "discover": lambda: cmd_discover(args.browser, args.profile),
    }
    try:
        return asyncio.run(handlers[args.xchat_cmd]())
    except XChatError as exc:
        print(f"Error: {exc}")
        return 2


def default_profile_dir() -> Path:
    return load_settings().profile_dir
