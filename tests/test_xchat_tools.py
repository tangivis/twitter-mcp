"""The three MCP tools that front the XChat session.

These tools own two things the session itself does not: turning `XChatError`
into an actionable `ToolError`, and closing the browser on every path. A leaked
Chromium process per failed call is the kind of bug that only shows up after a
day of use, so the teardown is asserted explicitly rather than assumed.
"""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from twitter_mcp import server
from twitter_mcp.xchat.errors import (
    XChatExtractionFailed,
    XChatLoginRequired,
    XChatUnavailable,
)
from twitter_mcp.xchat.session import SessionStatus


class FakeSession:
    """Stands in for `XChatSession`, recording that it was closed."""

    def __init__(self, status=None, conversations=None, messages=None, raises=None):
        self._status = status
        self._conversations = conversations or []
        self._messages = messages or []
        self._raises = raises
        self.closed = False
        self.opened = False

    async def open(self):
        if isinstance(self._raises, XChatUnavailable):
            raise self._raises
        self.opened = True
        return self

    async def close(self):
        self.closed = True

    async def status(self):
        return self._status

    async def list_conversations(self):
        if self._raises:
            raise self._raises
        return self._conversations

    async def get_history(self, conversation_id, limit=50):
        if self._raises:
            raise self._raises
        return self._messages[-limit:]


@pytest.fixture
def paired(monkeypatch, tmp_path):
    """Make the profile look paired, and hand each tool a FakeSession."""
    profile = tmp_path / "profile"
    (profile / "Default").mkdir(parents=True)

    from twitter_mcp.xchat.config import XChatSettings

    monkeypatch.setattr(
        "twitter_mcp.xchat.config.load_settings",
        lambda *a, **k: XChatSettings(profile_dir=profile),
    )

    def install(session):
        monkeypatch.setattr(
            "twitter_mcp.xchat.session.XChatSession", lambda *a, **k: session
        )
        return session

    return install


# ── status ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_without_a_profile_says_run_login(monkeypatch, tmp_path):
    """The un-paired case must not launch a browser just to say "not paired"."""
    from twitter_mcp.xchat.config import XChatSettings

    monkeypatch.setattr(
        "twitter_mcp.xchat.config.load_settings",
        lambda *a, **k: XChatSettings(profile_dir=tmp_path / "nothing-here"),
    )
    monkeypatch.setattr(
        "twitter_mcp.xchat.session.XChatSession",
        lambda *a, **k: pytest.fail("must not open a browser without a profile"),
    )

    out = json.loads(await server.xchat_status())

    assert out["state"] == "logged_out"
    assert out["profile_exists"] is False
    assert "xchat login" in out["detail"]


@pytest.mark.asyncio
async def test_status_reports_a_ready_session_and_closes_it(paired):
    session = paired(
        FakeSession(
            status=SessionStatus(
                state="ready",
                profile_dir="/tmp/p",
                profile_exists=True,
                detail="Encrypted messages are readable.",
                conversation_count=3,
            )
        )
    )

    out = json.loads(await server.xchat_status())

    assert out["state"] == "ready"
    assert out["conversation_count"] == 3
    assert session.closed is True


# ── listing ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_conversations_returns_rows_and_closes(paired):
    rows = [{"conversation_id": "1-2", "name": "Even Realities", "encrypted": True}]
    session = paired(FakeSession(conversations=rows))

    out = json.loads(await server.xchat_list_conversations())

    assert out["conversations"] == rows
    assert session.closed is True


@pytest.mark.asyncio
async def test_a_logged_out_session_becomes_an_actionable_tool_error(paired):
    session = paired(
        FakeSession(raises=XChatLoginRequired("Run `twikit-mcp xchat login`."))
    )

    with pytest.raises(ToolError, match="xchat login"):
        await server.xchat_list_conversations()

    # The browser must still be torn down on the failure path.
    assert session.closed is True


@pytest.mark.asyncio
async def test_a_failed_open_is_translated_not_leaked(paired):
    paired(FakeSession(raises=XChatUnavailable("Install Playwright.")))

    with pytest.raises(ToolError, match="Playwright"):
        await server.xchat_list_conversations()


# ── history ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_history_returns_messages_and_echoes_the_id(paired):
    messages = [
        {"text": "hi", "timestamp": "t0", "direction": "incoming"},
        {"text": "hello", "timestamp": "t1", "direction": "outgoing"},
    ]
    session = paired(FakeSession(messages=messages))

    out = json.loads(await server.xchat_get_history("1-2"))

    assert out["conversation_id"] == "1-2"
    assert out["messages"] == messages
    assert session.closed is True


@pytest.mark.asyncio
async def test_get_history_applies_the_limit(paired):
    paired(FakeSession(messages=[{"text": t} for t in ("a", "b", "c")]))

    out = json.loads(await server.xchat_get_history("1-2", limit=1))

    assert [m["text"] for m in out["messages"]] == ["c"]


@pytest.mark.asyncio
async def test_an_empty_conversation_id_fails_before_opening_a_browser(monkeypatch):
    monkeypatch.setattr(
        "twitter_mcp.xchat.session.XChatSession",
        lambda *a, **k: pytest.fail("must validate args before launching a browser"),
    )

    with pytest.raises(ToolError, match="conversation_id"):
        await server.xchat_get_history("")


@pytest.mark.asyncio
async def test_selector_drift_surfaces_as_a_tool_error(paired):
    session = paired(FakeSession(raises=XChatExtractionFailed("Run doctor.")))

    with pytest.raises(ToolError, match="doctor"):
        await server.xchat_get_history("1-2")

    assert session.closed is True
