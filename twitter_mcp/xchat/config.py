"""Settings for the XChat path, loaded from `.env.local` / `.env` + process env.

We parse dotenv files ourselves rather than adding `python-dotenv`: the format
we need is a dozen lines of code, and this package is an optional extra — it
should not drag a runtime dependency into the base install.

Precedence, highest first:
    1. the real process environment
    2. `.env.local`   (the file the maintainer actually uses for secrets)
    3. `.env`
That ordering matters: a value exported in the shell must win, otherwise a
stale file silently overrides what the user just typed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Searched in order, first match wins per key (see module docstring).
ENV_FILENAMES = (".env.local", ".env")

DEFAULT_PROFILE_DIR = "~/.config/twitter-mcp/xchat-profile"
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_MESSAGES_URL = "https://x.com/i/chat"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

# How to obtain a PIN when X asks for one.
PIN_PROMPT_MODES = ("auto", "tty", "web", "none")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_env_file(text: str) -> dict[str, str]:
    """Parse dotenv-style text into a dict.

    Supports `KEY=value`, `export KEY=value`, `#` comments, blank lines, and
    single/double quoted values. Deliberately does NOT do variable expansion —
    a PIN like `12$34` must survive verbatim.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key:
            continue
        out[key] = _strip_quotes(value.strip())
    return out


def load_env_files(search_from: Path | None = None) -> dict[str, str]:
    """Collect env values from `.env.local` then `.env`, walking up to the repo root.

    Walking upward means `twikit-mcp xchat ...` works from a subdirectory, which
    is how it will actually be invoked most of the time.
    """
    start = Path(search_from or Path.cwd()).resolve()
    merged: dict[str, str] = {}
    # Nearest directory wins, and within a directory `.env.local` beats `.env`.
    for directory in (start, *start.parents):
        for name in ENV_FILENAMES:
            path = directory / name
            if not path.is_file():
                continue
            try:
                parsed = parse_env_file(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            for key, value in parsed.items():
                merged.setdefault(key, value)
        if (directory / ".git").exists():
            break
    return merged


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    return default


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


@dataclass
class XChatSettings:
    """Resolved XChat configuration.

    `pin` is a secret: `__repr__` is overridden so it cannot leak into a log
    line, a traceback, or an MCP error payload by accident.
    """

    profile_dir: Path
    headless: bool = True
    pin: str | None = None
    pin_prompt: str = "auto"
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    messages_url: str = DEFAULT_MESSAGES_URL
    # Playwright browser channel, e.g. "chrome". None uses the bundled
    # Chromium; pointing at a real Chrome build helps when X's login flow
    # treats plain Chromium as suspicious.
    browser_channel: str | None = None
    # Optional, explicit bootstrap source for `xchat login`. The file is never
    # consulted during normal headless reads; importing these credentials into
    # the dedicated profile grants it persistent access to the X account.
    cookie_file: Path | None = None
    selector_overrides: Path | None = None
    raw: dict[str, str] = field(default_factory=dict, repr=False)

    def __repr__(self) -> str:  # pragma: no cover - trivial formatting
        return (
            f"XChatSettings(profile_dir={self.profile_dir!r}, "
            f"headless={self.headless!r}, pin={'<set>' if self.pin else None}, "
            f"pin_prompt={self.pin_prompt!r}, timeout_ms={self.timeout_ms!r})"
        )

    @property
    def has_pin(self) -> bool:
        return bool(self.pin)


def load_settings(
    environ: dict[str, str] | None = None,
    search_from: Path | None = None,
) -> XChatSettings:
    """Resolve settings from process env layered over dotenv files."""
    process_env = dict(os.environ if environ is None else environ)
    file_env = load_env_files(search_from)

    def get(key: str) -> str | None:
        value = process_env.get(key)
        if value is None or value == "":
            value = file_env.get(key)
        return value or None

    pin_prompt = (get("XCHAT_PIN_PROMPT") or "auto").strip().lower()
    if pin_prompt not in PIN_PROMPT_MODES:
        pin_prompt = "auto"

    overrides = get("XCHAT_SELECTORS")
    cookie_file = get("XCHAT_COOKIE_FILE")

    return XChatSettings(
        profile_dir=Path(
            os.path.expanduser(get("XCHAT_PROFILE_DIR") or DEFAULT_PROFILE_DIR)
        ),
        headless=_as_bool(get("XCHAT_HEADLESS"), True),
        pin=get("XCHAT_PIN"),
        pin_prompt=pin_prompt,
        timeout_ms=_as_int(get("XCHAT_TIMEOUT_MS"), DEFAULT_TIMEOUT_MS),
        messages_url=get("XCHAT_MESSAGES_URL") or DEFAULT_MESSAGES_URL,
        browser_channel=get("XCHAT_BROWSER_CHANNEL"),
        cookie_file=(Path(os.path.expanduser(cookie_file)) if cookie_file else None),
        selector_overrides=Path(os.path.expanduser(overrides)) if overrides else None,
        raw=file_env,
    )
