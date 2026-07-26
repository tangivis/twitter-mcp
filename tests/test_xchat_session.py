"""Session state machine, PIN handling, and profile detection.

The browser is faked. What is worth testing here is the decision logic — in
particular the one-shot PIN rule: X permanently destroys message keys after a
limited number of wrong guesses, so any path that could retry a PIN in a loop
is a data-loss bug, not a UX wart.
"""

from unittest.mock import AsyncMock

import pytest

from twitter_mcp.xchat.config import XChatSettings
from twitter_mcp.xchat.errors import (
    XChatLoginRequired,
    XChatNoPin,
    XChatPinRejected,
)
from twitter_mcp.xchat.pin import PinProvider
from twitter_mcp.xchat.session import (
    STATE_LOCKED,
    STATE_LOGGED_OUT,
    STATE_READY,
    STATE_UNKNOWN,
    XChatSession,
    load_bootstrap_cookies,
    profile_is_initialized,
)


class FakePage:
    """Minimal stand-in: a set of selectors that "exist", plus a call log."""

    def __init__(self, present=(), url="https://x.com/messages"):
        self.present = set(present)
        self.url = url
        self.filled: list[tuple[str, str]] = []
        self.clicked: list[str] = []
        # Selectors that resolve to an account-password input, for the
        # `_looks_like_a_login_field` probe.
        self.login_fields: set[str] = set()

    async def evaluate(self, script, arg=None):
        if "el.matches(" in script:
            return arg in self.login_fields
        if "querySelector(c)" in script and "querySelectorAll" not in script:
            return arg in self.present
        if "querySelectorAll(c).length" in script:
            return 1 if arg in self.present else 0
        return []

    async def goto(self, url, **_kwargs):
        self.url = url

    async def wait_for_timeout(self, _ms):
        return None

    async def fill(self, selector, value):
        self.filled.append((selector, value))

    async def click(self, selector):
        self.clicked.append(selector)

    async def press(self, selector, key):
        self.clicked.append(f"{selector}:{key}")


def make_session(present=(), url="https://x.com/messages", pin=None, mode="auto"):
    settings = XChatSettings(profile_dir=__import__("pathlib").Path("/tmp/x"), pin=pin)
    session = XChatSession(
        settings=settings,
        pin_provider=PinProvider(pin=pin, mode=mode),
    )
    session._page = FakePage(present=present, url=url)
    return session


def _sel(session, key, index=0):
    return session.selectors[key][index]


@pytest.mark.asyncio
async def test_state_logged_out_from_url():
    session = make_session(url="https://x.com/i/flow/login")
    assert await session.current_state() == STATE_LOGGED_OUT


@pytest.mark.asyncio
async def test_state_logged_out_from_marker():
    session = make_session()
    session._page.present.add(_sel(session, "login_marker"))
    assert await session.current_state() == STATE_LOGGED_OUT


@pytest.mark.asyncio
async def test_locked_beats_ready():
    """A rendered inbox behind a PIN gate is locked, not ready."""
    session = make_session()
    session._page.present.update(
        {_sel(session, "pin_dialog"), _sel(session, "conversation_list")}
    )
    assert await session.current_state() == STATE_LOCKED


@pytest.mark.asyncio
async def test_state_ready_and_unknown():
    session = make_session()
    session._page.present.add(_sel(session, "conversation_list"))
    assert await session.current_state() == STATE_READY
    assert await make_session().current_state() == STATE_UNKNOWN


@pytest.mark.asyncio
async def test_logged_out_asks_for_login_not_a_pin():
    session = make_session(pin="1234")
    session._page.present.add(_sel(session, "login_marker"))
    with pytest.raises(XChatLoginRequired):
        await session._ensure_ready()
    # Must not have burned a PIN guess on a session that was merely logged out.
    assert session._page.filled == []


# ── the login-sheet confusion (found against live x.com) ──
#
# X serves logged-out visitors `/i/jf/onboarding/web?...&mode=login`, a sheet
# that contains `div[role="dialog"] input[type="password"]` — the *account*
# password field. That used to match `pin_input`, so the session was classified
# `locked` and `_unlock()` typed the chat PIN into X's login form and submitted
# it. Each test below closes one layer of that hole.


LOGIN_SHEET_PASSWORD = 'div[role="dialog"] input[name="password"]'


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/i/jf/onboarding/web?redirect_after_login=%2Fmessages&mode=login",
        "https://x.com/i/flow/login",
        "https://x.com/login",
        "https://x.com/account/access",
    ],
)
@pytest.mark.asyncio
async def test_login_flow_urls_are_recognised_as_logged_out(url):
    assert await make_session(url=url).current_state() == STATE_LOGGED_OUT


@pytest.mark.asyncio
async def test_the_login_sheet_is_logged_out_not_locked():
    """The regression: a password field in a dialog is a login, not a PIN gate."""
    session = make_session(pin="1234")
    session._page.present.add(LOGIN_SHEET_PASSWORD)
    assert await session.current_state() == STATE_LOGGED_OUT


@pytest.mark.asyncio
async def test_the_pin_selector_cannot_match_an_account_password_field():
    """The generic dialog fallback must be negated on password attributes."""
    session = make_session()
    for candidate in session.selectors["pin_input"]:
        if 'input[type="password"]' in candidate:
            assert ':not([name="password"])' in candidate
            assert ':not([autocomplete="current-password"])' in candidate


@pytest.mark.asyncio
async def test_unlock_refuses_a_password_field_even_if_selectors_drift():
    """Defence in depth: the guard reads the live element, not the selector."""
    session = make_session(pin="1234")
    # Simulate a bad override that points `pin_input` straight at the login field.
    session.selectors["pin_input"] = [LOGIN_SHEET_PASSWORD]
    session._page.present.add(LOGIN_SHEET_PASSWORD)
    session._page.login_fields.add(LOGIN_SHEET_PASSWORD)

    with pytest.raises(XChatLoginRequired, match="Refusing to type your PIN"):
        await session._unlock()

    assert session._page.filled == []


@pytest.mark.asyncio
async def test_an_unprobeable_field_is_treated_as_unsafe():
    """If we cannot prove the field is safe, we must not type into it."""
    session = make_session(pin="1234")
    pin_input = _sel(session, "pin_input")
    session._page.present.add(pin_input)

    async def evaluate(script, arg=None):
        if "el.matches(" in script:
            raise RuntimeError("evaluation failed")
        return arg in session._page.present

    session._page.evaluate = evaluate

    with pytest.raises(XChatLoginRequired):
        await session._unlock()
    assert session._page.filled == []


@pytest.mark.asyncio
async def test_unlock_uses_env_pin_and_succeeds():
    session = make_session(pin="4321")
    pin_input = _sel(session, "pin_input")
    session._page.present.add(pin_input)
    await session._unlock()
    assert session._page.filled == [(pin_input, "4321")]


@pytest.mark.asyncio
async def test_unlock_without_a_pin_raises_before_touching_the_form():
    session = make_session(mode="none")
    session._page.present.add(_sel(session, "pin_input"))
    with pytest.raises(XChatNoPin):
        await session._unlock()
    assert session._page.filled == []


@pytest.mark.asyncio
async def test_rejected_pin_is_not_retried():
    """The data-loss guard: a wrong PIN must fail, never loop."""
    session = make_session(pin="0000")
    session._page.present.update(
        {_sel(session, "pin_input"), _sel(session, "pin_error")}
    )
    with pytest.raises(XChatPinRejected):
        await session._unlock()
    assert len(session._page.filled) == 1

    # A second attempt in the same session refuses outright.
    with pytest.raises(XChatPinRejected):
        await session._unlock()
    assert len(session._page.filled) == 1


@pytest.mark.asyncio
async def test_lingering_dialog_counts_as_rejection():
    session = make_session(pin="0000")
    session._page.present.update(
        {_sel(session, "pin_input"), _sel(session, "pin_dialog")}
    )
    with pytest.raises(XChatPinRejected):
        await session._unlock()


@pytest.mark.asyncio
async def test_status_never_consumes_a_pin_guess():
    session = make_session(pin="1234")
    session._page.present.add(_sel(session, "pin_dialog"))
    status = await session.status()
    assert status.state == STATE_LOCKED
    assert session._page.filled == []
    assert "1234" not in repr(status.to_dict())


def test_pin_provider_invalidate_drops_the_env_pin():
    """A wrong .env.local PIN must not be re-offered forever."""
    provider = PinProvider(pin="1111", mode="none")
    assert provider.get() == "1111"
    provider.invalidate()
    assert provider.get() is None


def test_profile_detection(tmp_path):
    assert profile_is_initialized(tmp_path / "missing") is False
    assert profile_is_initialized(tmp_path) is False  # empty dir != paired
    (tmp_path / "Default").mkdir()
    assert profile_is_initialized(tmp_path) is True


def _semantic_node(node_id, role, name="", url=None):
    props = [] if url is None else [{"name": "url", "value": {"value": url}}]
    return {
        "nodeId": node_id,
        "role": {"value": role},
        "name": {"value": name},
        "properties": props,
    }


@pytest.mark.asyncio
async def test_semantic_ready_and_locked_states(monkeypatch):
    session = make_session(url="https://x.com/i/chat")
    ready = [
        _semantic_node("root", "RootWebArea", "X", "https://x.com/i/chat"),
        _semantic_node("title", "StaticText", "Chat"),
    ]
    monkeypatch.setattr(
        "twitter_mcp.xchat.session.capture_accessibility_tree",
        AsyncMock(return_value=ready),
    )
    assert await session.current_state() == STATE_READY

    session._page.url = "https://x.com/i/chat/pin/verify"
    locked = [_semantic_node(str(i), "textbox") for i in range(4)]
    monkeypatch.setattr(
        "twitter_mcp.xchat.session.capture_accessibility_tree",
        AsyncMock(return_value=locked),
    )
    assert await session.current_state() == STATE_LOCKED


@pytest.mark.asyncio
async def test_segmented_passcode_fields_are_filled_once(monkeypatch):
    session = make_session(url="https://x.com/i/chat/pin/verify", pin="4321")

    class Field:
        def __init__(self):
            self.values = []

        async def fill(self, value):
            self.values.append(value)

    fields = [Field() for _ in range(4)]

    class Fields:
        async def count(self):
            return len(fields)

        def nth(self, index):
            return fields[index]

    session._page.get_by_role = lambda role: Fields()
    monkeypatch.setattr(session, "current_state", AsyncMock(return_value=STATE_READY))

    await session._unlock()

    assert [field.values for field in fields] == [["4"], ["3"], ["2"], ["1"]]
    assert session._pin_attempted is True


def test_cookie_bootstrap_accepts_secure_mapping_without_leaking_values(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text('{"auth_token":"top-secret-a","ct0":"top-secret-c"}')
    path.chmod(0o600)

    cookies = load_bootstrap_cookies(path)

    assert [cookie["name"] for cookie in cookies] == ["auth_token", "ct0"]
    assert all(cookie["domain"] == ".x.com" for cookie in cookies)


def test_cookie_bootstrap_rejects_insecure_permissions(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text('{"auth_token":"a","ct0":"c"}')
    path.chmod(0o644)

    from twitter_mcp.xchat.errors import XChatUnavailable

    with pytest.raises(XChatUnavailable, match="chmod 600") as exc:
        load_bootstrap_cookies(path)
    assert '"a"' not in str(exc.value)


@pytest.mark.asyncio
async def test_cookie_import_requires_visible_login(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text('{"auth_token":"a","ct0":"c"}')
    path.chmod(0o600)
    settings = XChatSettings(profile_dir=tmp_path / "profile", cookie_file=path)
    session = XChatSession(settings=settings, headless=True)

    from twitter_mcp.xchat.errors import XChatUnavailable

    with pytest.raises(XChatUnavailable, match="visible"):
        await session.import_login_cookies()


@pytest.mark.asyncio
async def test_visible_login_imports_only_two_allowed_cookies(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text('{"auth_token":"a","ct0":"c","guest_id":"must-not-import"}')
    path.chmod(0o600)
    settings = XChatSettings(profile_dir=tmp_path / "profile", cookie_file=path)
    session = XChatSession(settings=settings, headless=False)

    class Context:
        def __init__(self):
            self.cookies = None

        async def add_cookies(self, cookies):
            self.cookies = cookies

    session._context = Context()

    assert await session.import_login_cookies() == 2
    assert [cookie["name"] for cookie in session._context.cookies] == [
        "auth_token",
        "ct0",
    ]


@pytest.mark.asyncio
async def test_doctor_report_is_content_free(monkeypatch):
    session = make_session(url="https://x.com/i/chat/1-2")
    nodes = [
        _semantic_node("root", "RootWebArea", "X", "https://x.com/i/chat/1-2"),
        _semantic_node("message", "listitem", "private message body"),
    ]
    monkeypatch.setattr(session, "_goto_messages", AsyncMock())
    monkeypatch.setattr(session, "current_state", AsyncMock(return_value=STATE_READY))
    monkeypatch.setattr(session, "_semantic_nodes", AsyncMock(return_value=nodes))

    report = await session.doctor()

    assert report["state"] == STATE_READY
    assert report["message_items"] == 0
    assert "private message body" not in str(report)
