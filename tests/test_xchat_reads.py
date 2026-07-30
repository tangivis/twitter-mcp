"""Reading conversations and history off the decrypted client.

Complements `test_xchat_session.py` (which covers the state machine and the
one-shot PIN rule). Here the browser is faked with canned extractor payloads
so the navigation, scroll-back, and failure-reporting logic can be exercised
without launching Chromium.
"""

from pathlib import Path

import pytest

from twitter_mcp.xchat.config import XChatSettings
from twitter_mcp.xchat.errors import (
    XChatExtractionFailed,
    XChatPinRejected,
    XChatUnavailable,
)
from twitter_mcp.xchat.pin import PinProvider
from twitter_mcp.xchat.session import STATE_READY, XChatSession


class FakePage:
    """Fake page that also answers the two extractor scripts with canned rows."""

    def __init__(self, present=(), conversations=None, messages=None):
        self.present = set(present)
        self.url = "https://x.com/messages"
        self.conversations = conversations or []
        # A list of payloads: each scroll pass pops the next one, which models
        # X loading more history as you page upward.
        self.message_pages = list(messages or [[]])
        self.filled: list[tuple[str, str]] = []
        self.clicked: list[str] = []
        self.visited: list[str] = []
        self.scrolled = 0
        self.keys: list[str] = []
        # Selectors that resolve to an account-password input; empty here
        # because these fixtures model a signed-in client.
        self.login_fields: set[str] = set()
        self.keyboard = self._Keyboard(self)

    class _Keyboard:
        def __init__(self, page):
            self.page = page

        async def press(self, key):
            self.page.keys.append(key)
            self.page._advance()

    @property
    def messages(self):
        return self.message_pages[0]

    def _advance(self):
        if len(self.message_pages) > 1:
            self.message_pages.pop(0)

    async def evaluate(self, script, arg=None):
        if "el.matches(" in script:
            return arg in self.login_fields
        if "sel.conversation" in script:
            return self.conversations
        if "sel.message" in script:
            return self.messages
        if "scrollTop = 0" in script:
            self.scrolled += 1
            self._advance()
            return None
        if "querySelectorAll(c).length" in script:
            if arg in {c for c in self.present}:
                return 1
            # Message-row counting drives scroll-back's stop condition.
            if "messageEntry" in str(arg):
                return len(self.messages)
            return 0
        if "querySelector(c)" in script:
            return arg in self.present
        return []

    async def goto(self, url, **_kwargs):
        self.url = url
        self.visited.append(url)

    async def wait_for_timeout(self, _ms):
        return None

    async def fill(self, selector, value):
        self.filled.append((selector, value))

    async def click(self, selector):
        self.clicked.append(selector)

    async def press(self, selector, key):
        self.clicked.append(f"{selector}:{key}")


def make_session(page, pin=None):
    session = XChatSession(
        settings=XChatSettings(profile_dir=Path("/tmp/xchat-test"), pin=pin),
        pin_provider=PinProvider(pin=pin, mode="none"),
    )
    session._page = page
    return session


def _sel(session, key, index=0):
    return session.selectors[key][index]


def ready_page(session_selectors_from, **kwargs):
    """A page in the `ready` state (inbox rendered, no PIN gate)."""
    page = FakePage(**kwargs)
    page.present.add(session_selectors_from)
    return page


CONVERSATIONS = [
    {
        "id": "1-2",
        "text": "Even Realities\nSee you Tuesday",
        "timestamp": "2026-07-24T10:00:00.000Z",
        "encrypted": True,
        "unread": True,
    },
    # A skeleton row X renders while the list loads — must not reach the caller.
    {"id": None, "text": "", "timestamp": None},
]

MESSAGES = [
    {"index": 0, "text": "first", "timestamp": "t0", "direction": "incoming"},
    {"index": 1, "text": "second", "timestamp": "t1", "direction": "outgoing"},
    {"index": 2, "text": "third", "timestamp": "t2", "direction": "unknown"},
]


# ── listing ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_conversations_returns_normalized_rows():
    session = make_session(FakePage(conversations=CONVERSATIONS))
    session._page.present.add(_sel(session, "conversation_list"))

    rows = await session.list_conversations()

    assert len(rows) == 1  # the id-less skeleton row is dropped
    assert rows[0]["conversation_id"] == "1-2"
    assert rows[0]["name"] == "Even Realities"
    assert rows[0]["preview"] == "See you Tuesday"
    assert rows[0]["encrypted"] is True


@pytest.mark.asyncio
async def test_empty_inbox_is_reported_as_ambiguous_not_as_zero():
    """An empty inbox and a broken selector are indistinguishable from here."""
    session = make_session(FakePage(conversations=[]))
    session._page.present.add(_sel(session, "conversation_list"))

    with pytest.raises(XChatExtractionFailed, match="doctor"):
        await session.list_conversations()


@pytest.mark.asyncio
async def test_unknown_state_points_at_the_doctor_command():
    session = make_session(FakePage())  # nothing matches at all
    with pytest.raises(XChatExtractionFailed, match="doctor"):
        await session._ensure_ready()


# ── history ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_history_navigates_to_the_conversation():
    session = make_session(FakePage(messages=[MESSAGES]))
    session._page.present.add(_sel(session, "conversation_list"))

    messages = await session.get_history("1-2", limit=50)

    assert session._page.visited[-1] == "https://x.com/i/chat/1-2"
    assert [m["text"] for m in messages] == ["first", "second", "third"]
    # The layout guess must stay labelled as a guess.
    assert {m["direction_source"] for m in messages} == {"layout-heuristic"}


@pytest.mark.asyncio
async def test_limit_keeps_the_newest_messages():
    """X renders oldest-first, so "last 2" must slice from the end."""
    session = make_session(FakePage(messages=[MESSAGES]))
    session._page.present.add(_sel(session, "conversation_list"))

    messages = await session.get_history("1-2", limit=2)

    assert [m["text"] for m in messages] == ["second", "third"]


@pytest.mark.asyncio
async def test_history_with_no_messages_raises_rather_than_returning_empty():
    session = make_session(FakePage(messages=[[]]))
    session._page.present.add(_sel(session, "conversation_list"))

    with pytest.raises(XChatExtractionFailed, match="1-2"):
        await session.get_history("1-2")


@pytest.mark.asyncio
async def test_opening_a_conversation_can_trigger_its_own_pin_gate():
    """The inbox can render fine and the conversation still be locked."""
    session = make_session(FakePage(messages=[MESSAGES]), pin="1234")
    session._page.present.update(
        {
            _sel(session, "conversation_list"),
            _sel(session, "pin_dialog"),
            _sel(session, "pin_input"),
        }
    )
    # `current_state` sees the dialog, so _ensure_ready unlocks first; the
    # rejection path is what proves the PIN was actually offered.
    with pytest.raises(XChatPinRejected):
        await session.get_history("1-2")
    assert session._page.filled == [(_sel(session, "pin_input"), "1234")]


# ── scroll-back ────────────────────────────────────────


@pytest.mark.asyncio
async def test_scroll_back_stops_once_the_target_is_reached():
    session = make_session(FakePage(messages=[MESSAGES]))
    session._page.present.add(_sel(session, "message_scroller"))

    await session._scroll_back(2)

    assert session._page.scrolled == 0  # already had enough rows


@pytest.mark.asyncio
async def test_scroll_back_pages_until_history_stops_growing():
    page = FakePage(messages=[MESSAGES[:1], MESSAGES[:2], MESSAGES, MESSAGES])
    session = make_session(page)
    page.present.add(_sel(session, "message_scroller"))

    await session._scroll_back(100)  # more than exists

    # Stops when a pass adds nothing rather than burning all 12 passes.
    assert 0 < len(page.keys) < 12


@pytest.mark.asyncio
async def test_scroll_back_falls_back_to_the_home_key():
    """With no scroller selector matching, paging must still make progress."""
    page = FakePage(messages=[MESSAGES[:1], MESSAGES])
    session = make_session(page)

    await session._scroll_back(100)

    assert page.keys and set(page.keys) == {"Home"}


# ── status ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_reports_ready_with_a_conversation_count():
    session = make_session(FakePage(conversations=CONVERSATIONS))
    session._page.present.add(_sel(session, "conversation_list"))

    status = await session.status()

    assert status.state == STATE_READY
    assert status.to_dict()["conversation_count"] == 1
    assert status.to_dict()["profile_exists"] is False


# ── lifecycle ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_playwright_explains_how_to_install_it(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fail_on_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_on_playwright)
    session = XChatSession(settings=XChatSettings(profile_dir=Path("/tmp/xchat-test")))

    with pytest.raises(XChatUnavailable, match="playwright install chromium"):
        await session.open()


@pytest.mark.asyncio
async def test_reading_before_open_is_a_clear_error():
    session = XChatSession(settings=XChatSettings(profile_dir=Path("/tmp/xchat-test")))
    with pytest.raises(XChatUnavailable, match="not open"):
        await session._goto_messages()


@pytest.mark.asyncio
async def test_close_is_safe_when_nothing_was_opened():
    session = XChatSession(settings=XChatSettings(profile_dir=Path("/tmp/xchat-test")))
    await session.close()
    assert session._page is None


@pytest.mark.asyncio
async def test_a_malformed_selector_falls_through_to_the_next_candidate():
    """`:has()` on an old engine throws; the remaining candidates must still run."""
    page = FakePage()
    session = make_session(page)
    good = _sel(session, "conversation_list", 1)
    page.present.add(good)

    async def evaluate(script, arg=None):
        if arg == _sel(session, "conversation_list", 0):
            raise RuntimeError("unsupported pseudo-class")
        return arg in page.present

    page.evaluate = evaluate
    assert await session._first_matching("conversation_list") == good


@pytest.mark.asyncio
async def test_a_locked_session_with_no_pin_field_names_the_likely_cause():
    session = make_session(FakePage(), pin="1234")
    session._page.present.add(_sel(session, "pin_dialog"))  # gate, but no input

    with pytest.raises(XChatExtractionFailed, match="XCHAT_SELECTORS"):
        await session._unlock()


@pytest.mark.asyncio
async def test_pin_submits_with_enter_when_there_is_no_button():
    """X's PIN pad often submits on the last digit with no submit button."""
    session = make_session(FakePage(), pin="1234")
    pin_input = _sel(session, "pin_input")
    session._page.present.add(pin_input)

    await session._unlock()

    assert session._page.clicked == [f"{pin_input}:Enter"]


@pytest.mark.asyncio
async def test_the_context_manager_opens_and_closes(monkeypatch):
    session = XChatSession(settings=XChatSettings(profile_dir=Path("/tmp/xchat-test")))
    opened = []

    async def fake_open():
        opened.append(True)
        return session

    monkeypatch.setattr(session, "open", fake_open)
    async with session as entered:
        assert entered is session
    assert opened == [True]
    assert session._context is None


@pytest.mark.asyncio
async def test_teardown_failures_do_not_mask_the_real_error():
    """A context that fails to close must not replace the error that got us here."""

    class Exploding:
        async def close(self):
            raise RuntimeError("browser already gone")

    session = XChatSession(settings=XChatSettings(profile_dir=Path("/tmp/xchat-test")))
    session._context = Exploding()
    await session.close()
    assert session._context is None
