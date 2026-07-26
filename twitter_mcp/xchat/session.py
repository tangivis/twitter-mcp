"""The paired local X session — this package's equivalent of a whatsmeow device.

Lifecycle, and why it is shaped this way:

    twikit-mcp xchat login     visible browser, human logs in + registers the
                               device + sets/enters the chat PIN. Once.
    (profile on disk)          a Chromium persistent context, i.e. the pairing
                               artifact. Cookies, IndexedDB, and the registered
                               device's key material all live here.
    every later run            headless, reusing that profile. If X re-locks
                               the store, the PIN comes from `.env.local` or a
                               prompt, and the browser types it — we never see
                               or reimplement the key derivation.

The one rule that shapes the unlock path: X's PIN recovery has a hard guess
limit, and exhausting it destroys the key material permanently. So this module
tries a PIN **once per session** and then fails loudly. An automatic retry loop
here would be a config typo away from making your entire history unreadable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twitter_mcp.xchat.config import XChatSettings, load_settings
from twitter_mcp.xchat.errors import (
    XChatExtractionFailed,
    XChatLoginRequired,
    XChatNoPin,
    XChatPinRejected,
    XChatUnavailable,
)
from twitter_mcp.xchat.pin import PinProvider
from twitter_mcp.xchat.reader import (
    EXTRACT_CONVERSATIONS_JS,
    EXTRACT_MESSAGES_JS,
    LOGIN_PASSWORD_ATTRS,
    capture_accessibility_tree,
    extract_conversations_from_ax,
    extract_messages_from_ax,
    load_selectors,
    normalize_conversations,
    normalize_messages,
    scroll_semantic_message_list,
    semantic_diagnostics,
)

STATE_READY = "ready"
STATE_LOCKED = "locked"
STATE_LOGGED_OUT = "logged_out"
STATE_UNKNOWN = "unknown"

# URL fragments that mean "this is a login flow, not the app". X has moved this
# more than once (`/login`, `/i/flow/login`, now `/i/jf/onboarding/web?...
# &mode=login`), and every miss here risks the PIN being typed into a login
# form, so the list is deliberately broad — a false "logged out" costs the user
# one `xchat login`, a false "locked" costs them a leaked secret.
LOGGED_OUT_URL_MARKERS = (
    "/login",
    "/i/flow/login",
    "/i/flow/signup",
    "/i/jf/onboarding",
    "/account/access",
    "mode=login",
    "redirect_after_login",
)

# How long to let the client settle before deciding what state it is in. X
# renders the inbox shell before it has decrypted anything, so an immediate
# read reports "no conversations" on a perfectly healthy session.
SETTLE_MS = 2_500
# Scroll passes when paging back through history. Each pass loads roughly a
# screenful; 12 is ~a few hundred messages, past which callers should page.
MAX_SCROLL_PASSES = 12
SCROLL_SETTLE_MS = 700


def load_bootstrap_cookies(path: Path | str) -> list[dict[str, Any]]:
    """Load only the two X credentials needed to seed the dedicated profile.

    Values are deliberately never included in errors or diagnostics. On POSIX,
    reject files readable by group/other because these cookies grant persistent
    account access. Both the historic twikit mapping format and a browser-style
    cookie list are accepted.
    """
    cookie_path = Path(path).expanduser()
    try:
        mode = cookie_path.stat().st_mode
        if os.name == "posix" and mode & 0o077:
            raise XChatUnavailable(
                f"Cookie file {cookie_path} must not be readable by group/other; "
                "run `chmod 600` on it."
            )
        raw = json.loads(cookie_path.read_text(encoding="utf-8"))
    except XChatUnavailable:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise XChatUnavailable(
            f"Could not read XCHAT_COOKIE_FILE at {cookie_path}: {type(exc).__name__}."
        ) from exc

    values: dict[str, str] = {}
    if isinstance(raw, dict):
        values = {
            name: value
            for name in ("auth_token", "ct0")
            if isinstance((value := raw.get(name)), str) and value
        }
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or item.get("name") not in {
                "auth_token",
                "ct0",
            }:
                continue
            value = item.get("value")
            if isinstance(value, str) and value:
                values[str(item["name"])] = value

    missing = sorted({"auth_token", "ct0"} - values.keys())
    if missing:
        raise XChatUnavailable(
            "XCHAT_COOKIE_FILE must contain non-empty auth_token and ct0 values "
            f"(missing: {', '.join(missing)})."
        )
    return [
        {
            "name": name,
            "value": values[name],
            "domain": ".x.com",
            "path": "/",
            "secure": True,
            "httpOnly": name == "auth_token",
            "sameSite": "Lax",
        }
        for name in ("auth_token", "ct0")
    ]


def profile_is_initialized(profile_dir: Path | str) -> bool:
    """True if `profile_dir` looks like a real Chromium profile, not an empty dir.

    Checked before launching anything: distinguishing "never paired" from
    "paired but logged out" is the difference between telling the user to run
    `login` and telling them their session expired, and launching a browser to
    find that out costs seconds for no information.
    """
    path = Path(profile_dir)
    if not path.is_dir():
        return False
    return (path / "Default").is_dir() or (path / "Local State").is_file()


@dataclass
class SessionStatus:
    state: str
    profile_dir: str
    profile_exists: bool
    detail: str
    conversation_count: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "state": self.state,
            "profile_dir": self.profile_dir,
            "profile_exists": self.profile_exists,
            "detail": self.detail,
        }
        if self.conversation_count is not None:
            out["conversation_count"] = self.conversation_count
        out.update(self.extras)
        return out


class XChatSession:
    """A headless (or visible) X web client bound to the local paired profile."""

    def __init__(
        self,
        settings: XChatSettings | None = None,
        headless: bool | None = None,
        pin_provider: PinProvider | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        # An explicit argument beats config: `login` must be visible even when
        # `XCHAT_HEADLESS=true` is set for normal operation.
        self.headless = self.settings.headless if headless is None else headless
        self.selectors = load_selectors(self.settings.selector_overrides)
        self.pin_provider = pin_provider or PinProvider(
            pin=self.settings.pin, mode=self.settings.pin_prompt
        )
        self._playwright = None
        self._context = None
        self._page = None
        # Guards the one-shot PIN rule described in the module docstring.
        self._pin_attempted = False
        self._last_ax_nodes: list[dict[str, Any]] | None = None

    # ── lifecycle ──────────────────────────────────────

    async def open(self) -> "XChatSession":
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise XChatUnavailable(
                "XChat support needs Playwright. Install it with:\n"
                "  pip install 'twikit-mcp[xchat]' && playwright install chromium"
            ) from exc

        self.settings.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        launch: dict[str, Any] = {
            "user_data_dir": str(self.settings.profile_dir),
            "headless": self.headless,
            # X's client lays out the DM list responsively; a phone-sized
            # viewport collapses the columns the extractors walk.
            "viewport": {"width": 1280, "height": 900},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if self.settings.browser_channel:
            launch["channel"] = self.settings.browser_channel
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                **launch
            )
        except Exception as exc:  # playwright raises its own error hierarchy
            await self._shutdown()
            raise XChatUnavailable(
                f"Could not launch the browser for the XChat profile: {exc}\n"
                "If this says the executable is missing, run: playwright install chromium"
            ) from exc

        self._context.set_default_timeout(self.settings.timeout_ms)
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else (await self._context.new_page())
        )
        return self

    async def close(self) -> None:
        await self._shutdown()

    async def _shutdown(self) -> None:
        for closer in (
            getattr(self._context, "close", None),
            getattr(self._playwright, "stop", None),
        ):
            if closer is None:
                continue
            try:
                await closer()
            except Exception:
                # Teardown failures must not mask the real error that got us
                # here; the process is exiting or the context is already gone.
                pass
        self._context = None
        self._page = None
        self._playwright = None

    async def __aenter__(self) -> "XChatSession":
        return await self.open()

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    # ── page helpers ───────────────────────────────────

    async def _first_matching(self, key: str):
        """Return the first candidate selector for `key` that matches, or None."""
        for candidate in self.selectors.get(key, []):
            try:
                if await self._page.evaluate(
                    "(c) => !!document.querySelector(c)", candidate
                ):
                    return candidate
            except Exception:
                # A malformed candidate (e.g. `:has()` on an old engine) should
                # fall through to the next one, not abort the whole probe.
                continue
        return None

    async def _looks_like_a_login_field(self, selector: str) -> bool:
        """True if `selector` resolves to an account-password input.

        Checked against the live element rather than the selector text, so a
        user-supplied `XCHAT_SELECTORS` override is covered too.
        """
        probe = (
            "(c) => { const el = document.querySelector(c); if (!el) return false;"
            " return "
            + " || ".join(f"el.matches('{a}')" for a in LOGIN_PASSWORD_ATTRS)
            + "; }"
        )
        try:
            return bool(await self._page.evaluate(probe, selector))
        except Exception:
            # If we cannot prove the field is safe, treat it as unsafe.
            return True

    async def _goto_messages(self) -> None:
        if self._page is None:
            raise XChatUnavailable("Session is not open; call `open()` first.")
        await self._page.goto(
            self.settings.messages_url,
            wait_until="domcontentloaded",
            timeout=self.settings.timeout_ms,
        )
        await self._page.wait_for_timeout(SETTLE_MS)

    async def import_login_cookies(self) -> int:
        """Seed the visible pairing profile from an explicitly configured file."""
        if self.settings.cookie_file is None:
            return 0
        if self.headless:
            raise XChatUnavailable(
                "Cookie bootstrap is allowed only during visible `xchat login`."
            )
        cookies = load_bootstrap_cookies(self.settings.cookie_file)
        await self._context.add_cookies(cookies)
        return len(cookies)

    async def _semantic_nodes(self) -> list[dict[str, Any]] | None:
        """Capture the AX tree, with a fake-compatible fallback for old tests."""
        try:
            nodes = await capture_accessibility_tree(self._page)
        except (AttributeError, NotImplementedError):
            return None
        self._last_ax_nodes = nodes
        return nodes

    @staticmethod
    def _semantic_names(nodes: list[dict[str, Any]]) -> set[str]:
        return {
            str((node.get("name") or {}).get("value") or "").strip().lower()
            for node in nodes
            if isinstance(node.get("name"), dict)
        }

    async def current_state(self) -> str:
        """Classify the client: ready / locked / logged_out / unknown.

        Logged-out is checked *first and hardest*. X's login sheet contains an
        account-password field, so a logged-out session misread as `locked`
        would send the chat PIN to the login form (see `_unlock`).
        """
        url = (self._page.url or "").lower()
        if any(marker in url for marker in LOGGED_OUT_URL_MARKERS):
            return STATE_LOGGED_OUT
        nodes = await self._semantic_nodes()
        if nodes is not None:
            names = self._semantic_names(nodes)
            if "/i/chat/pin/" in url or (
                "enter passcode" in names
                and sum(
                    (node.get("role") or {}).get("value") == "textbox" for node in nodes
                )
                == 4
            ):
                return STATE_LOCKED
            if extract_conversations_from_ax(nodes) or (
                url.startswith("https://x.com/i/chat") and "chat" in names
            ):
                return STATE_READY
        if await self._first_matching("login_marker"):
            return STATE_LOGGED_OUT
        if await self._first_matching("pin_dialog") or await self._first_matching(
            "pin_input"
        ):
            return STATE_LOCKED
        if await self._first_matching("conversation_list"):
            return STATE_READY
        return STATE_UNKNOWN

    # ── unlocking ──────────────────────────────────────

    async def _unlock(self) -> None:
        """Type the PIN into X's own unlock UI. One attempt, ever, per session.

        See the module docstring: X's PIN recovery has a hard guess limit and
        burning it destroys the keys, so a rejected PIN raises instead of
        looping.
        """
        if self._pin_attempted:
            raise XChatPinRejected(
                "The chat PIN was already tried once in this session and did not "
                "unlock it. Not retrying — X permanently destroys your message "
                "keys after a limited number of wrong PIN guesses. Fix XCHAT_PIN "
                "in .env.local, then start a new session."
            )
        self._pin_attempted = True

        pin = self.pin_provider.get()
        if not pin:
            raise XChatNoPin(
                "This XChat session is locked and needs your chat PIN. Either set "
                "XCHAT_PIN in .env.local, or allow a prompt "
                "(XCHAT_PIN_PROMPT=tty|web; currently "
                f"{self.pin_provider.mode!r})."
            )

        # The verified 2026 XChat UI uses four semantic textboxes, one per
        # digit, under `/i/chat/pin/...`. This avoids selectors entirely and
        # the route guard prevents an account-login form from ever receiving
        # the chat passcode.
        url = (self._page.url or "").lower()
        if "/i/chat/pin/" in url and hasattr(self._page, "get_by_role"):
            if not (len(pin) == 4 and pin.isdigit()):
                raise XChatNoPin("XChat requires a four-digit passcode.")
            fields = self._page.get_by_role("textbox")
            count = await fields.count()
            if count != 4:
                raise XChatExtractionFailed(
                    f"The passcode route exposed {count} textboxes, expected 4. "
                    "Not typing the passcode; run `twikit-mcp xchat doctor`."
                )
            for index, digit in enumerate(pin):
                await fields.nth(index).fill(digit)
            await self._page.wait_for_timeout(SETTLE_MS)
            if await self.current_state() == STATE_LOCKED:
                self.pin_provider.invalidate()
                raise XChatPinRejected(
                    "The passcode screen is still showing after one submission. "
                    "Not retrying automatically."
                )
            return

        pin_input = await self._first_matching("pin_input")
        if not pin_input:
            raise XChatExtractionFailed(
                "The session is locked but no PIN field matched a known selector. "
                "Run `twikit-mcp xchat doctor` to see the current DOM, then set "
                "XCHAT_SELECTORS to a corrected override file."
            )
        # Last line of defence, independent of every selector above: never type
        # the PIN into an account-password field. Selectors drift, and the cost
        # of getting this wrong is not a failed read — it is the user's chat PIN
        # submitted to X's login form and logged as a failed sign-in.
        if await self._looks_like_a_login_field(pin_input):
            raise XChatLoginRequired(
                "The page is showing X's login form, not the chat-PIN prompt. "
                "Refusing to type your PIN into a password field. Run "
                "`twikit-mcp xchat login` to sign in again."
            )
        await self._page.fill(pin_input, pin)

        submit = await self._first_matching("pin_submit")
        if submit:
            await self._page.click(submit)
        else:
            # X's PIN pad often submits on the last digit with no button.
            await self._page.press(pin_input, "Enter")

        # Settle, then read the outcome rather than assuming success.
        await self._page.wait_for_timeout(SETTLE_MS)
        if await self._first_matching("pin_error"):
            self.pin_provider.invalidate()
            raise XChatPinRejected(
                "X rejected the chat PIN. Not retrying automatically — repeated "
                "wrong guesses permanently destroy your message keys. Correct "
                "XCHAT_PIN in .env.local and run again."
            )
        if await self._first_matching("pin_dialog"):
            self.pin_provider.invalidate()
            raise XChatPinRejected(
                "The PIN was submitted but the unlock prompt is still showing. "
                "Treating this as a rejection rather than guessing again."
            )

    async def _ensure_ready(self) -> None:
        """Navigate to Messages and get the client into `ready`, or explain why not."""
        await self._goto_messages()
        state = await self.current_state()

        if state == STATE_LOGGED_OUT:
            raise XChatLoginRequired(
                "The local X session is logged out. Run `twikit-mcp xchat login` "
                "once to pair this machine (opens a visible browser)."
            )
        if state == STATE_LOCKED:
            await self._unlock()
            state = await self.current_state()
        if state == STATE_READY:
            return
        if state == STATE_LOCKED:
            raise XChatPinRejected("Still locked after supplying the PIN.")
        raise XChatExtractionFailed(
            f"X's Messages page loaded but matched no known state (url={self._page.url}). "
            "This usually means X changed the DOM — run `twikit-mcp xchat doctor`."
        )

    # ── reads ──────────────────────────────────────────

    async def status(self) -> SessionStatus:
        """Report state without unlocking — a probe, not an action.

        Deliberately does not call `_unlock()`: a status check should never be
        able to consume one of the account's finite PIN guesses.
        """
        await self._goto_messages()
        state = await self.current_state()
        detail = {
            STATE_READY: "Encrypted messages are readable.",
            STATE_LOCKED: (
                "Logged in but PIN-locked. Set XCHAT_PIN in .env.local, or let a "
                "read prompt for it."
            ),
            STATE_LOGGED_OUT: "Not logged in — run `twikit-mcp xchat login`.",
            STATE_UNKNOWN: (
                "Page loaded but matched no known state; run `twikit-mcp xchat doctor`."
            ),
        }[state]

        count = None
        if state == STATE_READY:
            count = len(await self._read_conversations())
        return SessionStatus(
            state=state,
            profile_dir=str(self.settings.profile_dir),
            profile_exists=profile_is_initialized(self.settings.profile_dir),
            detail=detail,
            conversation_count=count,
        )

    async def _read_conversations(self) -> list[dict[str, Any]]:
        nodes = await self._semantic_nodes()
        if nodes is not None:
            return extract_conversations_from_ax(nodes)
        raw = await self._page.evaluate(EXTRACT_CONVERSATIONS_JS, self.selectors)
        return normalize_conversations(raw)

    async def list_conversations(self) -> list[dict[str, Any]]:
        await self._ensure_ready()
        conversations = await self._read_conversations()
        if not conversations:
            # An empty inbox and a broken selector look identical from here, so
            # say both rather than implying the account has no messages.
            raise XChatExtractionFailed(
                "No conversations matched. Either the inbox is genuinely empty, "
                "or X changed the DOM — `twikit-mcp xchat doctor` will say which."
            )
        return conversations

    async def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        await self._ensure_ready()
        await self._page.goto(
            f"https://x.com/i/chat/{conversation_id}",
            wait_until="domcontentloaded",
            timeout=self.settings.timeout_ms,
        )
        await self._page.wait_for_timeout(SETTLE_MS)

        # Opening a specific conversation can itself trigger the passcode gate
        # even when the inbox rendered fine. Reuse the semantic state classifier
        # so the verified segmented-input UI does not depend on a CSS fallback.
        if await self.current_state() == STATE_LOCKED:
            await self._unlock()
            await self._page.wait_for_timeout(SETTLE_MS)

        await self._scroll_back(limit)
        nodes = await self._semantic_nodes()
        if nodes is not None:
            messages = extract_messages_from_ax(nodes, limit=limit)
        else:
            raw = await self._page.evaluate(EXTRACT_MESSAGES_JS, self.selectors)
            messages = normalize_messages(raw, limit=limit)
        if not messages:
            raise XChatExtractionFailed(
                f"No messages matched in conversation {conversation_id}. Run "
                "`twikit-mcp xchat doctor` to check the semantic page shape."
            )
        return messages

    async def _scroll_back(self, target: int) -> None:
        """Page upward until `target` messages are rendered or the top is reached.

        X virtualises the message list, so what is in the DOM is roughly what
        has been scrolled through. Stops early when a pass adds nothing, which
        is both the top-of-history case and the nothing-is-loading case.
        """
        previous = -1
        for _ in range(MAX_SCROLL_PASSES):
            rows = await self._count_messages()
            if rows >= target or rows == previous:
                return
            previous = rows
            try:
                scrolled = await scroll_semantic_message_list(self._page)
            except (AttributeError, NotImplementedError):
                scrolled = False
            if not scrolled:
                await self._page.keyboard.press("Home")
            await self._page.wait_for_timeout(SCROLL_SETTLE_MS)

    async def _count_messages(self) -> int:
        nodes = await self._semantic_nodes()
        if nodes is not None:
            return len(extract_messages_from_ax(nodes))
        for candidate in self.selectors.get("message", []):
            count = await self._page.evaluate(
                "(c) => document.querySelectorAll(c).length", candidate
            )
            if count:
                return int(count)
        return 0

    async def doctor(self) -> dict[str, Any]:
        """Return content-free semantic diagnostics; never unlocks or logs text."""
        await self._goto_messages()
        state = await self.current_state()
        nodes = self._last_ax_nodes or await self._semantic_nodes()
        report = semantic_diagnostics(nodes or [])
        report["state"] = state
        report["profile_dir"] = str(self.settings.profile_dir)
        return report


async def open_session(settings: XChatSettings | None = None) -> XChatSession:
    """Convenience constructor mirroring the MCP layer's usage."""
    return await XChatSession(settings=settings).open()


__all__ = [
    "STATE_READY",
    "STATE_LOCKED",
    "STATE_LOGGED_OUT",
    "STATE_UNKNOWN",
    "SessionStatus",
    "XChatSession",
    "load_bootstrap_cookies",
    "open_session",
    "profile_is_initialized",
]
