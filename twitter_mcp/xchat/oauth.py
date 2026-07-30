"""OAuth2 PKCE setup and token refresh for the browser-independent XChat API."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from twitter_mcp.xchat.errors import XChatUnavailable

AUTHORIZATION_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
READ_SCOPES = ("dm.read", "users.read", "tweet.read", "offline.access")


class OAuthTokenStore:
    """Owner-only JSON storage with atomic replacement for rotating tokens."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise XChatUnavailable(
                "No XChat OAuth grant is stored; run `twikit-mcp xchat oauth`."
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise XChatUnavailable(
                "The stored XChat OAuth token is unreadable."
            ) from exc
        if not isinstance(data, dict) or not data.get("access_token"):
            raise XChatUnavailable("The stored XChat OAuth token is incomplete.")
        return data

    def save(self, token: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        )
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(token, handle, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _normalize_token(
    payload: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    token = dict(payload)
    if not token.get("refresh_token") and previous:
        token["refresh_token"] = previous.get("refresh_token")
    if token.get("expires_in"):
        token["expires_at"] = time.time() + int(token["expires_in"])
    return token


def refresh_access_token(
    client_id: str,
    store: OAuthTokenStore,
    *,
    post: Callable[..., Any] = httpx.post,
) -> str:
    token = store.load()
    expires_at = float(token.get("expires_at") or 0)
    if expires_at > time.time() + 60:
        return str(token["access_token"])
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise XChatUnavailable(
            "The XChat OAuth grant cannot refresh; run `twikit-mcp xchat oauth`."
        )
    response = post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        timeout=30,
    )
    if not response.ok:
        raise XChatUnavailable(
            f"X rejected the XChat OAuth refresh (HTTP {response.status_code})."
        )
    refreshed = _normalize_token(response.json(), token)
    if not refreshed.get("access_token"):
        raise XChatUnavailable("X returned an incomplete OAuth refresh response.")
    store.save(refreshed)
    return str(refreshed["access_token"])


def configured_access_token(settings: Any) -> str:
    if settings.api_access_token:
        return str(settings.api_access_token)
    store = OAuthTokenStore(settings.oauth_token_file)
    client_id = settings.oauth_client_id
    if not client_id:
        client_id = store.load().get("client_id")
    if not client_id:
        raise XChatUnavailable(
            "XCHAT_OAUTH_CLIENT_ID or XCHAT_API_ACCESS_TOKEN is required for chatxdk."
        )
    return refresh_access_token(str(client_id), store)


def authorize(
    client_id: str,
    redirect_uri: str,
    store: OAuthTokenStore,
    *,
    open_browser: bool = True,
    post: Callable[..., Any] = httpx.post,
) -> str:
    """Run one local PKCE grant and return a sanitized success message."""
    parsed_redirect = urlparse(redirect_uri)
    if parsed_redirect.scheme != "http" or parsed_redirect.hostname not in {
        "localhost",
        "127.0.0.1",
    }:
        raise XChatUnavailable("The OAuth redirect must use loopback HTTP.")
    verifier = secrets.token_urlsafe(96)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(READ_SCOPES),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    authorization_url = f"{AUTHORIZATION_URL}?{query}"
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            query_values = parse_qs(urlparse(self.path).query)
            if query_values.get("state", [None])[0] != state:
                result["error"] = "OAuth state did not match."
                status = 400
            elif query_values.get("error"):
                result["error"] = str(query_values["error"][0])
                status = 400
            elif query_values.get("code"):
                result["code"] = str(query_values["code"][0])
                status = 200
            else:
                result["error"] = "OAuth callback did not contain a code."
                status = 400
            body = (
                b"XChat OAuth complete. You can return to the terminal."
                if status == 200
                else b"XChat OAuth failed. You can return to the terminal."
            )
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(
        (parsed_redirect.hostname or "localhost", parsed_redirect.port or 80),
        CallbackHandler,
    )
    print(f"Authorize XChat with these read-only scopes: {' '.join(READ_SCOPES)}")
    print(authorization_url)
    if open_browser:
        webbrowser.open(authorization_url)
    server.timeout = 300
    server.handle_request()
    server.server_close()
    if result.get("error"):
        raise XChatUnavailable(result["error"])
    if not result.get("code"):
        raise XChatUnavailable("Timed out waiting for the X OAuth callback.")
    response = post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": result["code"],
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "client_id": client_id,
        },
        timeout=30,
    )
    if not response.ok:
        raise XChatUnavailable(
            f"X rejected the OAuth code exchange (HTTP {response.status_code})."
        )
    token = _normalize_token(response.json())
    if not token.get("access_token") or not token.get("refresh_token"):
        raise XChatUnavailable("X did not return a renewable OAuth token.")
    token["client_id"] = client_id
    store.save(token)
    return f"OAuth grant saved to {store.path} with mode 600."


__all__ = [
    "OAuthTokenStore",
    "READ_SCOPES",
    "authorize",
    "configured_access_token",
    "refresh_access_token",
]
