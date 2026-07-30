"""PIN acquisition: env, TTY, and the loopback web form.

The web form is the fallback that matters most — an MCP server spawned by a
GUI client has no terminal, so without it a locked session fails with no way
for the user to intervene. It is also the only part of this package that opens
a socket, so its access control is tested rather than assumed.
"""

import urllib.error
import urllib.request

import pytest

from twitter_mcp.xchat.pin import PinProvider, prompt_tty, prompt_web


def _post(url: str, body: str = "pin=246810") -> int:
    request = urllib.request.Request(
        url,
        data=body.encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


# ── the loopback form ──────────────────────────────────


def test_web_prompt_returns_the_submitted_pin():
    captured = {}

    def opener(url):
        captured["url"] = url
        assert _post(url) == 200

    assert prompt_web(timeout_s=10, opener=opener, announce=lambda _u: None) == "246810"
    # Loopback only: a form asking for a decryption PIN must not be reachable
    # from the network.
    assert captured["url"].startswith("http://127.0.0.1:")


def test_web_prompt_serves_the_form_on_get():
    seen = {}

    def opener(url):
        with urllib.request.urlopen(url, timeout=5) as response:
            seen["body"] = response.read().decode()
        assert _post(url) == 200

    prompt_web(timeout_s=10, opener=opener, announce=lambda _u: None)
    assert 'name="pin"' in seen["body"]
    # The PIN field must never round-trip as readable text in the DOM.
    assert 'type="password"' in seen["body"]


def test_web_prompt_rejects_a_wrong_token():
    """Without this, any page in the user's browser could POST a guess."""
    outcomes = {}

    def opener(url):
        base = url.rsplit("/", 1)[0]
        try:
            urllib.request.urlopen(f"{base}/not-the-token", timeout=5)
            outcomes["code"] = 200
        except urllib.error.HTTPError as exc:
            outcomes["code"] = exc.code
        assert _post(url) == 200

    prompt_web(timeout_s=10, opener=opener, announce=lambda _u: None)
    assert outcomes["code"] == 404


def test_web_prompt_returns_none_on_timeout():
    assert (
        prompt_web(timeout_s=1, opener=lambda _u: None, announce=lambda _u: None)
        is None
    )


def test_web_prompt_ignores_an_empty_submission():
    """An empty field is not a PIN; returning "" would be typed as a wrong guess."""
    prompt_web(
        timeout_s=10,
        opener=lambda url: _post(url, body="pin="),
        announce=lambda _u: None,
    )


def test_announce_writes_to_stderr_not_stdout(capsys):
    """stdout is the MCP JSON-RPC channel; a stray line there corrupts it."""
    prompt_web(timeout_s=1, opener=lambda _u: None)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "127.0.0.1" in captured.err


# ── the terminal prompt ────────────────────────────────


def test_tty_prompt_returns_none_without_a_terminal(monkeypatch):
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": lambda _s: False})())
    assert prompt_tty() is None


def test_tty_prompt_reads_from_getpass(monkeypatch):
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": lambda _s: True})())
    assert prompt_tty(getpass_fn=lambda _p: "  1357 ") == "1357"


@pytest.mark.parametrize("boom", [EOFError, KeyboardInterrupt])
def test_tty_prompt_treats_interruption_as_no_pin(monkeypatch, boom):
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": lambda _s: True})())

    def raiser(_prompt):
        raise boom()

    assert prompt_tty(getpass_fn=raiser) is None


# ── strategy selection ─────────────────────────────────


def test_env_pin_short_circuits_every_prompt():
    def explode(*_args):
        raise AssertionError("must not prompt when .env.local supplies a PIN")

    provider = PinProvider(pin="9999", tty_fn=explode, web_fn=explode)
    assert provider.get() == "9999"


def test_auto_falls_through_tty_to_web():
    provider = PinProvider(mode="auto", tty_fn=lambda: None, web_fn=lambda _t: "5555")
    assert provider.get() == "5555"


def test_tty_mode_does_not_fall_through_to_web():
    """An explicit mode is a constraint, not a preference."""

    def explode(_t):
        raise AssertionError("XCHAT_PIN_PROMPT=tty must not open a browser form")

    provider = PinProvider(mode="tty", tty_fn=lambda: None, web_fn=explode)
    assert provider.get() is None


def test_none_mode_never_prompts():
    def explode(*_args):
        raise AssertionError("XCHAT_PIN_PROMPT=none must not prompt")

    provider = PinProvider(mode="none", tty_fn=explode, web_fn=explode)
    assert provider.get() is None


def test_an_unknown_mode_falls_back_to_auto():
    provider = PinProvider(
        mode="telepathy", tty_fn=lambda: "1212", web_fn=lambda _t: None
    )
    assert provider.mode == "auto"
    assert provider.get() == "1212"


def test_a_prompted_pin_is_cached_for_the_process():
    """A long-running MCP server must not re-prompt on every tool call."""
    calls = []

    def once():
        calls.append(1)
        return "7777"

    provider = PinProvider(mode="tty", tty_fn=once)
    assert provider.get() == "7777"
    assert provider.get() == "7777"
    assert len(calls) == 1


def test_invalidate_forces_a_fresh_prompt():
    provider = PinProvider(pin="wrong", mode="tty", tty_fn=lambda: "right")
    assert provider.get() == "wrong"
    provider.invalidate()
    assert provider.get() == "right"
