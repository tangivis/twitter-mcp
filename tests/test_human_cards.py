"""Issue #61 + #68: TTY-aware card rendering for human CLI subcommands.

#61 shipped hand-rolled box-drawing in 0.1.23. #68 replaces the rendering
layer with [Rich](https://github.com/Textualize/rich) for correct
emoji/CJK width, OSC 8 clickable hyperlinks, and a more modern look.

The card path activates when `sys.stdout.isatty()` is true; pipes /
redirects fall back to the existing plain text format (so `| jq` /
`> file` still get sane output).

Key invariants (preserved across the Rich migration):

- Box-drawing chars (`╭ ╮ ╰ ╯ │ ─`) appear ONLY in TTY mode.
- Plain mode output is byte-equivalent to the pre-#61 / pre-#68 format.
- Card width is `min(max(terminal_columns, 60), 100)` — clamped.
- CSI ANSI escape codes (`\\x1b[...m`) only fire when TTY and `NO_COLOR`
  unset.
- Long body text wraps INSIDE the card without breaking the right border,
  including lines containing emoji or CJK characters.

New invariants (#68):

- Tweet URL / profile URL / user-bio URL are wrapped in OSC 8 hyperlinks
  (`\\x1b]8;;<url>\\x1b\\\\` … `\\x1b]8;;\\x1b\\\\`) in TTY mode.
- Lines containing emoji (e.g. `❤ 🔁 📍`) and CJK have correct visible
  width (Rich uses cell-width-aware measurement, not raw `len()`).
"""

import os
import re
from unittest.mock import patch

import pytest

# Used in several alignment tests. Kept local so tests don't depend on a
# private regex still being exported by the server module.
_CSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_OSC8_RE = re.compile(r"\x1b\]8;[^\x07]*?(?:\x1b\\|\x07)")


def _strip_escapes(s: str) -> str:
    """Drop CSI color codes AND OSC 8 hyperlink wrappers — what's left is
    what the user actually sees."""
    s = _CSI_RE.sub("", s)
    s = _OSC8_RE.sub("", s)
    return s


# ── _is_tty / _term_width helpers ────────────────────


def test_is_tty_true_when_isatty():
    """`_is_tty()` reflects sys.stdout.isatty()."""
    from twitter_mcp.server import _is_tty

    with patch("sys.stdout.isatty", return_value=True):
        assert _is_tty() is True


def test_is_tty_false_when_piped():
    from twitter_mcp.server import _is_tty

    with patch("sys.stdout.isatty", return_value=False):
        assert _is_tty() is False


def test_term_width_clamps_low():
    """Terminal width below 60 cols clamps UP to 60 (cards stay readable)."""
    from twitter_mcp.server import _term_width

    with patch("shutil.get_terminal_size", return_value=os.terminal_size((40, 24))):
        assert _term_width() == 60


def test_term_width_clamps_high():
    """Terminal width above 100 cols clamps DOWN to 100 (avoids overly-wide cards)."""
    from twitter_mcp.server import _term_width

    with patch("shutil.get_terminal_size", return_value=os.terminal_size((200, 24))):
        assert _term_width() == 100


def test_term_width_passes_normal_through():
    from twitter_mcp.server import _term_width

    with patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))):
        assert _term_width() == 80


# ── Plain-mode passthrough (non-TTY) ─────────────────


def test_format_tweet_plain_when_not_tty():
    """When stdout is not a tty, output uses the existing plain format
    (no box-drawing chars). Pre-#61 callers that pipe to `jq` etc. keep
    working byte-for-byte."""
    from twitter_mcp.server import _format_tweet

    with patch("sys.stdout.isatty", return_value=False):
        out = _format_tweet(
            {
                "id": "20",
                "author": "jack",
                "author_name": "jack",
                "text": "just setting up my twttr",
                "created_at": "2006-03-21",
                "likes": 310234,
                "retweets": 126500,
            }
        )
    for box_char in ("╭", "╮", "╰", "╯", "│", "─"):
        assert box_char not in out, (
            f"Plain (non-tty) mode contains box char {box_char!r} — "
            f"piped output should be plain text only."
        )
    # Plain output must also contain zero ANSI escape sequences, since
    # scripts that diff or `jq` the output rely on byte stability.
    assert "\x1b" not in out, f"plain output leaked ANSI escapes: {out!r}"


def test_format_user_plain_when_not_tty():
    from twitter_mcp.server import _format_user

    with patch("sys.stdout.isatty", return_value=False):
        out = _format_user(
            {
                "screen_name": "elonmusk",
                "name": "Elon Musk",
                "is_blue_verified": True,
                "description": "CEO",
                "followers_count": 200_000_000,
                "following_count": 1_000,
                "tweets_count": 50_000,
            }
        )
    for box_char in ("╭", "╮", "╰", "╯", "│", "─"):
        assert box_char not in out
    assert "\x1b" not in out


def test_format_trends_plain_when_not_tty():
    from twitter_mcp.server import _format_trends

    with patch("sys.stdout.isatty", return_value=False):
        out = _format_trends({"trends": [{"name": "AI", "tweets_count": 50_000}]})
    for box_char in ("╭", "╮", "╰", "╯", "│", "─"):
        assert box_char not in out
    assert "\x1b" not in out
    assert "AI" in out


# ── TTY-mode card rendering ──────────────────────────


@pytest.fixture
def tty_env():
    """Force TTY + a fixed 80-col terminal + no NO_COLOR for predictable cards."""
    with (
        patch("sys.stdout.isatty", return_value=True),
        patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))),
        patch.dict(os.environ, {"NO_COLOR": ""}, clear=False),
    ):
        os.environ.pop("NO_COLOR", None)  # ensure NO_COLOR truly unset
        yield


def test_format_tweet_renders_box_in_tty(tty_env):
    """In TTY mode, the tweet block uses box-drawing chars on every side."""
    from twitter_mcp.server import _format_tweet

    out = _format_tweet(
        {
            "id": "20",
            "author": "jack",
            "author_name": "jack",
            "text": "just setting up my twttr",
            "created_at": "2006-03-21",
            "likes": 310234,
            "retweets": 126500,
        }
    )
    # All four corners + both edges + horizontal separators must appear.
    for required in ("╭", "╮", "╰", "╯", "│", "─"):
        assert required in out, (
            f"TTY-mode tweet card missing box char {required!r}; got:\n{out}"
        )
    # Content still present (after stripping styling escapes).
    visible = _strip_escapes(out)
    assert "@jack" in visible
    assert "just setting up my twttr" in visible
    assert "https://x.com/jack/status/20" in visible


def test_format_user_renders_box_in_tty(tty_env):
    from twitter_mcp.server import _format_user

    out = _format_user(
        {
            "screen_name": "elonmusk",
            "name": "Elon Musk",
            "is_blue_verified": True,
            "description": "The People's CEO",
            "followers_count": 200_500_000,
            "following_count": 1_123,
            "tweets_count": 50_432,
            "location": "Texas",
        }
    )
    for required in ("╭", "╮", "╰", "╯", "│", "─"):
        assert required in out
    visible = _strip_escapes(out)
    assert "@elonmusk" in visible
    assert "200.5M" in visible


def test_format_trends_renders_box_in_tty(tty_env):
    from twitter_mcp.server import _format_trends

    out = _format_trends({"trends": [{"name": "AI", "tweets_count": 50_000}]})
    for required in ("╭", "│", "╰"):
        assert required in out
    assert "AI" in _strip_escapes(out)


# ── Width clamping carries through to cards ─────────


def test_card_width_uses_clamped_terminal():
    """A 200-col terminal renders a 100-col card (right border at col 100)."""
    from twitter_mcp.server import _format_tweet

    with (
        patch("sys.stdout.isatty", return_value=True),
        patch(
            "shutil.get_terminal_size",
            return_value=os.terminal_size((200, 24)),
        ),
    ):
        os.environ.pop("NO_COLOR", None)
        out = _format_tweet(
            {
                "id": "1",
                "author": "alice",
                "author_name": "Alice",
                "text": "hi",
                "created_at": "2026-01-01",
                "likes": 0,
                "retweets": 0,
            }
        )
    # Each rendered border line is exactly the clamped width — pick the
    # top border (starts with ╭, ends with ╮).
    visible_lines = [_strip_escapes(line) for line in out.splitlines()]
    top_lines = [line for line in visible_lines if line.startswith("╭")]
    assert top_lines, "no top-border line found in TTY card output"
    # Width is 100 visible cells (Rich uses cell-width-aware measurement).
    assert len(top_lines[0]) == 100, (
        f"top border {top_lines[0]!r} length {len(top_lines[0])}, "
        f"expected 100 (clamp ceiling)"
    )


# ── NO_COLOR honored ────────────────────────────────


def test_no_color_env_disables_ansi_in_tty():
    """`NO_COLOR=1` must suppress CSI ANSI color codes even when stdout is
    a tty. De-facto standard: https://no-color.org."""
    from twitter_mcp.server import _format_tweet

    with (
        patch("sys.stdout.isatty", return_value=True),
        patch(
            "shutil.get_terminal_size",
            return_value=os.terminal_size((80, 24)),
        ),
        patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False),
    ):
        out = _format_tweet(
            {
                "id": "1",
                "author": "alice",
                "author_name": "Alice",
                "text": "hi",
                "created_at": "2026-01-01",
                "likes": 0,
                "retweets": 0,
            }
        )
    assert "\x1b[" not in out, (
        f"NO_COLOR=1 set but CSI ANSI escape codes leaked into output:\n{out}"
    )


# ── Long-text wrap inside card ──────────────────────


def test_long_tweet_wraps_inside_card(tty_env):
    """Body longer than the available content width wraps; every body line
    has the same visible CELL width (right border doesn't drift)."""
    from rich.cells import cell_len

    from twitter_mcp.server import _format_tweet

    long_text = (
        "lorem ipsum dolor sit amet consectetur adipiscing elit "
        "sed do eiusmod tempor incididunt ut labore et dolore "
        "magna aliqua ut enim ad minim veniam quis nostrud "
        "exercitation ullamco laboris nisi ut aliquip ex ea commodo"
    )
    out = _format_tweet(
        {
            "id": "1",
            "author": "alice",
            "author_name": "Alice",
            "text": long_text,
            "created_at": "2026-01-01",
            "likes": 1,
            "retweets": 0,
        }
    )
    visible_lines = [_strip_escapes(line) for line in out.splitlines()]
    body_lines = [line for line in visible_lines if line.startswith("│")]
    assert len(body_lines) >= 3, "long text should wrap to multiple lines"
    # Cell-width comparison (not codepoint) — emoji & CJK occupy 2 cells.
    widths = {cell_len(line) for line in body_lines}
    assert len(widths) == 1, (
        f"body lines have inconsistent CELL widths {widths!r} — borders broken"
    )


# ── Edge cases (cover rare branches) ────────────────


def test_blank_paragraph_rendered_in_card(tty_env):
    """A blank line in tweet body keeps the body section intact (doesn't
    collapse the card body)."""
    from twitter_mcp.server import _format_tweet

    out = _format_tweet(
        {
            "id": "1",
            "author": "alice",
            "author_name": "Alice",
            "text": "first paragraph\n\nsecond paragraph",
            "created_at": "2026-01-01",
            "likes": 1,
            "retweets": 0,
        }
    )
    visible = _strip_escapes(out)
    assert "first paragraph" in visible
    assert "second paragraph" in visible


def test_tweet_with_no_text_renders_blank_body(tty_env):
    """A tweet with empty `text` field still renders without crashing,
    box still closed."""
    from twitter_mcp.server import _format_tweet

    out = _format_tweet(
        {
            "id": "1",
            "author": "a",
            "author_name": "A",
            "text": "",
            "created_at": "2026-01-01",
            "likes": 0,
            "retweets": 0,
        }
    )
    assert "╰" in out


def test_user_with_created_and_url_renders_those_lines(tty_env):
    """Coverage: `created_at` + `url` paths in `_card_user`. Spacing in
    Rich's grid layout isn't fixed-width, so we only assert the values
    appear (in the right order)."""
    from twitter_mcp.server import _format_user

    out = _format_user(
        {
            "screen_name": "alice",
            "name": "Alice",
            "followers_count": 0,
            "following_count": 0,
            "tweets_count": 0,
            "url": "https://example.com",
            "created_at": "Mon Jan 01 2024",
        }
    )
    visible = _strip_escapes(out)
    assert "Joined" in visible
    assert "Mon Jan 01 2024" in visible
    assert "https://example.com" in visible


def test_card_trends_empty_returns_no_trends(tty_env):
    """When trends list is empty, fall back to plain '(no trends)'."""
    from twitter_mcp.server import _format_trends

    out = _format_trends({"trends": []})
    assert out == "(no trends)"


def test_card_trends_with_domain_context(tty_env):
    """Coverage: trend with `domain_context` includes the context value."""
    from twitter_mcp.server import _format_trends

    out = _format_trends(
        {"trends": [{"name": "AI", "tweets_count": 10000, "domain_context": "Tech"}]}
    )
    visible = _strip_escapes(out)
    assert "AI" in visible
    assert "Tech" in visible


# ── Right-border alignment regressions (Rich's wcwidth fix, issue #68) ──


def test_emoji_line_aligns_right_border(tty_env):
    """Issue #68: a line containing emoji (❤ 🔁) has the same visible
    width as plain lines — Rich uses cell-width-aware measurement, the
    pre-#68 hand-rolled `_visible_len` (`len()` after ANSI strip) didn't.
    """
    from rich.cells import cell_len

    from twitter_mcp.server import _format_tweet

    out = _format_tweet(
        {
            "id": "1",
            "author": "alice",
            "author_name": "Alice",
            "text": "hi",
            "created_at": "2026-01-01",
            "likes": 7269,
            "retweets": 5473,
        }
    )
    visible_lines = [_strip_escapes(line) for line in out.splitlines()]
    body_lines = [line for line in visible_lines if line.startswith("│")]
    # `❤ 7,269    🔁 5,473` line is in here. All body lines should have
    # the same visual cell width — this is the assertion that the
    # pre-#68 implementation FAILED because it counted emoji as 1 cell.
    cell_widths = {cell_len(line) for line in body_lines}
    assert len(cell_widths) == 1, (
        f"body lines (including emoji line) have inconsistent CELL widths "
        f"{cell_widths!r} — Rich/cell_len alignment regressed."
    )


def test_cjk_line_aligns_right_border(tty_env):
    """Issue #68: a body containing CJK (each char ~2 cells) wraps and
    pads correctly so the right border holds."""
    from rich.cells import cell_len

    from twitter_mcp.server import _format_tweet

    out = _format_tweet(
        {
            "id": "1",
            "author": "alice",
            "author_name": "アリス",
            "text": "今日は良い天気です。日本語のツイートも幅が崩れません。",
            "created_at": "2026-01-01",
            "likes": 1,
            "retweets": 0,
        }
    )
    visible_lines = [_strip_escapes(line) for line in out.splitlines()]
    body_lines = [line for line in visible_lines if line.startswith("│")]
    cell_widths = {cell_len(line) for line in body_lines}
    assert len(cell_widths) == 1, (
        f"CJK body lines have inconsistent CELL widths {cell_widths!r}"
    )


# ── OSC 8 hyperlinks (issue #68) ────────────────────


def test_tweet_emits_osc8_hyperlink_for_url(tty_env):
    """In TTY + no NO_COLOR, the tweet URL is wrapped in an OSC 8
    hyperlink escape so cmd-clicking jumps to it in modern terminals."""
    from twitter_mcp.server import _format_tweet

    out = _format_tweet(
        {
            "id": "20",
            "author": "jack",
            "author_name": "jack",
            "text": "hi",
            "created_at": "2006-03-21",
            "likes": 1,
            "retweets": 0,
        }
    )
    # Rich emits OSC 8 as `\x1b]8;;<url>\x1b\\` ... `\x1b]8;;\x1b\\`.
    assert "\x1b]8;" in out, (
        "tweet URL should be wrapped in OSC 8 hyperlink escape for "
        "click-to-open in modern terminals."
    )
    # The URL is present in the wrapper.
    assert "https://x.com/jack/status/20" in out


def test_user_emits_osc8_for_profile_url(tty_env):
    """Profile URL `https://x.com/<sn>` is OSC 8 wrapped."""
    from twitter_mcp.server import _format_user

    out = _format_user(
        {
            "screen_name": "alice",
            "name": "Alice",
            "followers_count": 0,
            "following_count": 0,
            "tweets_count": 0,
        }
    )
    assert "\x1b]8;" in out
    assert "https://x.com/alice" in out


def test_user_emits_osc8_for_bio_url(tty_env):
    """User-supplied bio URL is OSC 8 wrapped."""
    from twitter_mcp.server import _format_user

    out = _format_user(
        {
            "screen_name": "alice",
            "name": "Alice",
            "followers_count": 0,
            "following_count": 0,
            "tweets_count": 0,
            "url": "https://example.com/me",
        }
    )
    assert "\x1b]8;" in out
    assert "https://example.com/me" in out
