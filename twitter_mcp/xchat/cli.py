"""`twikit-mcp xchat ...` — pairing and debugging commands.

`login` is the only command that opens a visible browser, and it is the only
one that ever needs to: pairing is a human step (password, 2FA, chat PIN,
device registration). Everything after it runs headless against the profile
that step leaves behind.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from twitter_mcp.xchat.config import load_settings
from twitter_mcp.xchat.errors import XChatError
from twitter_mcp.xchat.session import (
    STATE_LOGGED_OUT,
    STATE_READY,
    XChatSession,
    profile_is_initialized,
)

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
        "This window stays open until the session is confirmed."
    )
    async with XChatSession(settings=settings, headless=False) as session:
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
    async with XChatSession() as session:
        print(_dumps(await session.list_conversations()))
    return 0


async def cmd_history(conversation_id: str, limit: int) -> int:  # pragma: no cover
    async with XChatSession() as session:
        print(_dumps(await session.get_history(conversation_id, limit=limit)))
    return 0


async def cmd_doctor() -> int:  # pragma: no cover - browser I/O
    """Report which selector candidates actually match — the drift check."""
    async with XChatSession() as session:
        await session._goto_messages()
        report: dict[str, object] = {"state": await session.current_state()}
        for key, candidates in session.selectors.items():
            matched = []
            for candidate in candidates:
                count = await session._page.evaluate(
                    "(c) => document.querySelectorAll(c).length", candidate
                )
                if count:
                    matched.append({"selector": candidate, "count": count})
            report[key] = matched or "NO MATCH"
        print(_dumps(report))
    return 0


def add_parser(subparsers) -> None:
    """Register `xchat` and its subcommands on the main CLI parser."""
    parser = subparsers.add_parser(
        "xchat",
        help="Read X's end-to-end encrypted (XChat) messages via a local session.",
        description=(
            "XChat messages cannot be decrypted from cookies or from X's API — "
            "the key lives on a registered device. These commands pair this "
            "machine as that device and read what it decrypts locally."
        ),
    )
    xsub = parser.add_subparsers(dest="xchat_cmd", required=True)
    xsub.add_parser("login", help="Pair this machine (opens a visible browser, once).")
    xsub.add_parser("status", help="Report session state: ready / locked / logged out.")
    xsub.add_parser("list", help="List XChat conversations.")
    p_hist = xsub.add_parser("history", help="Print one conversation's messages.")
    p_hist.add_argument("conversation_id")
    p_hist.add_argument("-n", "--limit", type=int, default=50)
    xsub.add_parser("doctor", help="Show which DOM selectors currently match.")


def dispatch(args) -> int:  # pragma: no cover - thin async dispatch
    handlers = {
        "login": lambda: cmd_login(),
        "status": lambda: cmd_status(),
        "list": lambda: cmd_list(),
        "history": lambda: cmd_history(args.conversation_id, args.limit),
        "doctor": lambda: cmd_doctor(),
    }
    try:
        return asyncio.run(handlers[args.xchat_cmd]())
    except XChatError as exc:
        print(f"Error: {exc}")
        return 2


def default_profile_dir() -> Path:
    return load_settings().profile_dir
