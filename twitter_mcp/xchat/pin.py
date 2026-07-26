"""Supplying the XChat unlock PIN.

Order of attempts (`XCHAT_PIN_PROMPT` picks/limits the strategy):

    env  → `XCHAT_PIN` from the process env or `.env.local`
    tty  → hidden prompt on the controlling terminal (`getpass`)
    web  → one-shot form on 127.0.0.1, for when there is no usable TTY
           (the common case when the MCP server is spawned by a GUI client)

The web fallback exists because an MCP server started by Claude Desktop / Codex
has no terminal to prompt on, and a silent "locked" failure there is
indistinguishable from a bug. It binds loopback only, serves exactly one
submission, and requires an unguessable token in the URL path so that a random
page in your browser cannot POST a guess at it.

The PIN is never written to disk by this module and never included in an
exception message.
"""

from __future__ import annotations

import secrets
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from urllib.parse import parse_qs

DEFAULT_PROMPT_TIMEOUT_S = 180

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>XChat unlock</title>
<style>
 body{{font:16px -apple-system,system-ui,sans-serif;background:#15202b;color:#e7e9ea;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
 form{{background:#1e2732;padding:32px;border-radius:16px;width:320px}}
 h1{{font-size:18px;margin:0 0 8px}} p{{color:#8b98a5;font-size:13px;margin:0 0 20px}}
 input{{width:100%;box-sizing:border-box;padding:12px;font-size:20px;letter-spacing:6px;
       text-align:center;border-radius:8px;border:1px solid #38444d;background:#15202b;
       color:#e7e9ea}}
 button{{width:100%;margin-top:16px;padding:12px;border:0;border-radius:999px;
        background:#1d9bf0;color:#fff;font-weight:600;font-size:15px;cursor:pointer}}
</style></head>
<body><form method="POST" action="/{token}">
 <h1>Unlock XChat</h1>
 <p>X needs your chat PIN to decrypt messages on this device. It stays on this
    machine and is used only to unlock the local session.</p>
 <input name="pin" type="password" inputmode="numeric" autocomplete="off" autofocus>
 <button type="submit">Unlock</button>
</form></body></html>
"""

_DONE = """<!doctype html><html><head><meta charset="utf-8"><title>Unlocked</title>
<style>body{font:16px -apple-system,system-ui,sans-serif;background:#15202b;color:#e7e9ea;
display:flex;min-height:100vh;align-items:center;justify-content:center}</style></head>
<body>PIN received — you can close this tab.</body></html>
"""


@dataclass
class _Captured:
    pin: str | None = None


def _make_handler(token: str, captured: _Captured, stop: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        # Silence the default stderr access log — it would be noise on the
        # MCP stdio transport's sibling stream.
        def log_message(self, *args):  # noqa: A003 - stdlib signature
            pass

        def _reject(self):
            self.send_response(404)
            self.end_headers()

        def do_GET(self):  # noqa: N802 - stdlib signature
            if self.path.strip("/") != token:
                return self._reject()
            body = _PAGE.format(token=token).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802 - stdlib signature
            if self.path.strip("/") != token:
                return self._reject()
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8", "replace")
            values = parse_qs(raw).get("pin") or []
            pin = values[0].strip() if values else ""
            body = _DONE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            if pin:
                captured.pin = pin
            stop.set()

    return Handler


def prompt_web(
    timeout_s: int = DEFAULT_PROMPT_TIMEOUT_S,
    opener: Callable[[str], object] | None = None,
    announce: Callable[[str], None] | None = None,
) -> str | None:
    """Serve a one-shot loopback PIN form. Returns the PIN, or None on timeout."""
    token = secrets.token_urlsafe(16)
    captured = _Captured()
    stop = threading.Event()

    server = HTTPServer(("127.0.0.1", 0), _make_handler(token, captured, stop))
    url = f"http://127.0.0.1:{server.server_port}/{token}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        (announce or _announce)(url)
        (opener or webbrowser.open)(url)
        stop.wait(timeout_s)
    finally:
        server.shutdown()
        server.server_close()
    return captured.pin


def _announce(url: str) -> None:
    # stderr, not stdout: stdout is the MCP JSON-RPC channel.
    print(f"XChat needs your PIN — open {url}", file=sys.stderr, flush=True)


def prompt_tty(getpass_fn: Callable[[str], str] | None = None) -> str | None:
    """Prompt on the controlling terminal. Returns None if there is no TTY."""
    if not (sys.stdin and sys.stdin.isatty()):
        return None
    if getpass_fn is None:  # pragma: no cover - stdlib indirection
        from getpass import getpass as getpass_fn
    try:
        pin = getpass_fn("XChat PIN: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return pin or None


class PinProvider:
    """Resolves a PIN on demand, per the configured strategy.

    Holds the value in memory for the life of the process so a long-running
    MCP server does not re-prompt on every tool call, but re-prompts if X
    rejects the cached value (see `invalidate`).
    """

    def __init__(
        self,
        pin: str | None = None,
        mode: str = "auto",
        timeout_s: int = DEFAULT_PROMPT_TIMEOUT_S,
        tty_fn: Callable[[], str | None] = prompt_tty,
        web_fn: Callable[[int], str | None] | None = None,
    ) -> None:
        self._env_pin = pin or None
        self._cached = self._env_pin
        self._mode = mode if mode in {"auto", "tty", "web", "none"} else "auto"
        self._timeout_s = timeout_s
        self._tty_fn = tty_fn
        self._web_fn = web_fn or (lambda t: prompt_web(t))

    @property
    def mode(self) -> str:
        return self._mode

    def invalidate(self) -> None:
        """Forget the current PIN — call this when X rejects it.

        The env-provided PIN is dropped too: if `.env.local` holds a wrong or
        rotated PIN, silently retrying it forever would lock the account out.
        """
        self._cached = None
        self._env_pin = None

    def get(self) -> str | None:
        if self._cached:
            return self._cached
        if self._mode == "none":
            return None
        if self._mode in ("auto", "tty"):
            pin = self._tty_fn()
            if pin:
                self._cached = pin
                return pin
            if self._mode == "tty":
                return None
        if self._mode in ("auto", "web"):
            pin = self._web_fn(self._timeout_s)
            if pin:
                self._cached = pin
                return pin
        return None
