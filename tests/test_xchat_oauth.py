"""Renewable OAuth2 PKCE token storage for chat-xdk."""

from __future__ import annotations

import io
import json
import stat
import time
from types import SimpleNamespace

import pytest

from twitter_mcp.xchat.errors import XChatUnavailable
from twitter_mcp.xchat.oauth import (
    OAuthTokenStore,
    authorize,
    configured_access_token,
    refresh_access_token,
)


class Response:
    ok = True
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_token_store_is_owner_only_and_atomic(tmp_path):
    path = tmp_path / "private" / "token.json"
    store = OAuthTokenStore(path)
    store.save({"access_token": "one", "refresh_token": "rotate"})
    store.save({"access_token": "two", "refresh_token": "rotate"})

    assert json.loads(path.read_text())["access_token"] == "two"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(path.parent.glob("*.tmp"))


def test_unexpired_token_does_not_call_network(tmp_path):
    store = OAuthTokenStore(tmp_path / "token.json")
    store.save({"access_token": "fresh", "expires_at": time.time() + 3600})

    assert refresh_access_token("client", store, post=lambda *a, **k: 1 / 0) == "fresh"


def test_public_client_refresh_rotates_and_preserves_refresh_token(tmp_path):
    store = OAuthTokenStore(tmp_path / "token.json")
    store.save({"access_token": "old", "refresh_token": "keep", "expires_at": 0})
    seen = {}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return Response({"access_token": "new", "expires_in": 7200})

    assert refresh_access_token("public-client", store, post=post) == "new"
    assert seen["data"] == {
        "grant_type": "refresh_token",
        "refresh_token": "keep",
        "client_id": "public-client",
    }
    assert "auth" not in seen
    saved = store.load()
    assert saved["refresh_token"] == "keep"
    assert saved["expires_at"] > time.time()


def test_stored_client_id_makes_harness_config_portable(tmp_path):
    path = tmp_path / "token.json"
    OAuthTokenStore(path).save(
        {
            "access_token": "fresh",
            "expires_at": time.time() + 3600,
            "client_id": "stored-public-client",
        }
    )
    settings = type(
        "Settings",
        (),
        {
            "api_access_token": None,
            "oauth_client_id": None,
            "oauth_token_file": path,
        },
    )()
    assert configured_access_token(settings) == "fresh"


def test_token_store_reports_missing_invalid_and_incomplete_files(tmp_path):
    path = tmp_path / "token.json"
    store = OAuthTokenStore(path)
    with pytest.raises(XChatUnavailable, match="No XChat OAuth grant"):
        store.load()

    path.write_text("not-json")
    with pytest.raises(XChatUnavailable, match="unreadable"):
        store.load()

    path.write_text("{}")
    with pytest.raises(XChatUnavailable, match="incomplete"):
        store.load()


def test_refresh_reports_missing_grant_http_failure_and_incomplete_response(tmp_path):
    store = OAuthTokenStore(tmp_path / "token.json")
    store.save({"access_token": "expired", "expires_at": 0})
    with pytest.raises(XChatUnavailable, match="cannot refresh"):
        refresh_access_token("client", store)

    store.save({"access_token": "expired", "refresh_token": "rotate", "expires_at": 0})
    rejected = SimpleNamespace(ok=False, status_code=401)
    with pytest.raises(XChatUnavailable, match="HTTP 401"):
        refresh_access_token("client", store, post=lambda *a, **k: rejected)

    incomplete = Response({"expires_in": 3600})
    with pytest.raises(XChatUnavailable, match="incomplete OAuth refresh"):
        refresh_access_token("client", store, post=lambda *a, **k: incomplete)


def test_configured_access_token_accepts_direct_token_and_requires_client_id(tmp_path):
    direct = SimpleNamespace(
        api_access_token="direct",
        oauth_client_id=None,
        oauth_token_file=tmp_path / "unused.json",
    )
    assert configured_access_token(direct) == "direct"

    path = tmp_path / "token.json"
    OAuthTokenStore(path).save({"access_token": "expired", "expires_at": 0})
    missing_client = SimpleNamespace(
        api_access_token=None,
        oauth_client_id=None,
        oauth_token_file=path,
    )
    with pytest.raises(XChatUnavailable, match="OAUTH_CLIENT_ID"):
        configured_access_token(missing_client)


class FakeCallbackServer:
    callback_path = "/callback?state=fixed-state&code=authorization-code"

    def __init__(self, address, handler_class):
        self.address = address
        self.handler_class = handler_class
        self.timeout = None
        self.closed = False

    def handle_request(self):
        if self.callback_path is None:
            return
        handler = self.handler_class.__new__(self.handler_class)
        handler.path = self.callback_path
        handler.wfile = io.BytesIO()
        handler.send_response = lambda status: setattr(handler, "status", status)
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        handler.do_GET()

    def server_close(self):
        self.closed = True


def test_authorize_exchanges_pkce_code_and_saves_renewable_grant(tmp_path, monkeypatch):
    monkeypatch.setattr("twitter_mcp.xchat.oauth.HTTPServer", FakeCallbackServer)
    monkeypatch.setattr(
        "twitter_mcp.xchat.oauth.secrets.token_urlsafe",
        lambda size: "fixed-state",
    )
    seen = {}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return Response(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 7200,
            }
        )

    store = OAuthTokenStore(tmp_path / "oauth.json")
    message = authorize(
        "public-client",
        "http://localhost:8080/callback",
        store,
        open_browser=False,
        post=post,
    )

    assert "mode 600" in message
    assert seen["url"].endswith("/2/oauth2/token")
    assert seen["data"]["grant_type"] == "authorization_code"
    assert seen["data"]["code"] == "authorization-code"
    assert seen["data"]["code_verifier"] == "fixed-state"
    saved = store.load()
    assert saved["client_id"] == "public-client"
    assert saved["refresh_token"] == "refresh"


def test_authorize_rejects_unsafe_redirect_and_callback_errors(tmp_path, monkeypatch):
    store = OAuthTokenStore(tmp_path / "oauth.json")
    with pytest.raises(XChatUnavailable, match="loopback HTTP"):
        authorize("client", "https://example.com/callback", store, open_browser=False)

    monkeypatch.setattr("twitter_mcp.xchat.oauth.HTTPServer", FakeCallbackServer)
    monkeypatch.setattr(
        "twitter_mcp.xchat.oauth.secrets.token_urlsafe",
        lambda size: "fixed-state",
    )
    monkeypatch.setattr(
        FakeCallbackServer, "callback_path", "/callback?code=wrong-state"
    )
    with pytest.raises(XChatUnavailable, match="state did not match"):
        authorize(
            "client",
            "http://127.0.0.1:8080/callback",
            store,
            open_browser=False,
        )


def test_authorize_reports_timeout_exchange_failure_and_incomplete_token(
    tmp_path, monkeypatch
):
    store = OAuthTokenStore(tmp_path / "oauth.json")
    monkeypatch.setattr("twitter_mcp.xchat.oauth.HTTPServer", FakeCallbackServer)
    monkeypatch.setattr(
        "twitter_mcp.xchat.oauth.secrets.token_urlsafe",
        lambda size: "fixed-state",
    )

    monkeypatch.setattr(FakeCallbackServer, "callback_path", None)
    with pytest.raises(XChatUnavailable, match="Timed out"):
        authorize("client", "http://localhost:8080/callback", store, open_browser=False)

    monkeypatch.setattr(
        FakeCallbackServer,
        "callback_path",
        "/callback?state=fixed-state&code=authorization-code",
    )
    rejected = SimpleNamespace(ok=False, status_code=400)
    with pytest.raises(XChatUnavailable, match="HTTP 400"):
        authorize(
            "client",
            "http://localhost:8080/callback",
            store,
            open_browser=False,
            post=lambda *a, **k: rejected,
        )

    with pytest.raises(XChatUnavailable, match="renewable OAuth token"):
        authorize(
            "client",
            "http://localhost:8080/callback",
            store,
            open_browser=False,
            post=lambda *a, **k: Response({"access_token": "only-access"}),
        )
