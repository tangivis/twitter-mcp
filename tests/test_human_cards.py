"""Issue #61: ASCII Twitter-card rendering for human CLI subcommands.

Tests for the new TTY-aware card formatters. The card path activates
when `sys.stdout.isatty()` is true; pipes / redirects fall back to the
existing plain text format (so `| jq` / `> file` still get sane output).

Key invariants:

- Box-drawing chars (`╭ ╮ ╰ ╯ │ ─`) appear ONLY in TTY mode.
- Plain mode output is byte-equivalent to the pre-#61 format.
- Card width is `min(max(terminal_columns, 60), 100)` — clamped.
- ANSI escape codes only fire when TTY=True AND `NO_COLOR` env unset.
- Long body text wraps INSIDE the card without breaking the right border.
"""

import os
from unittest.mock import patch

import pytest

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
    # Content still present.
    assert "@jack" in out
    assert "just setting up my twttr" in out
    assert "https://x.com/jack/status/20" in out


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
    assert "@elonmusk" in out
    assert "200.5M" in out


def test_format_trends_renders_box_in_tty(tty_env):
    from twitter_mcp.server import _format_trends

    out = _format_trends({"trends": [{"name": "AI", "tweets_count": 50_000}]})
    for required in ("╭", "│", "╰"):
        assert required in out
    assert "AI" in out


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
    top_lines = [line for line in out.splitlines() if line.startswith("╭")]
    assert top_lines, "no top-border line found in TTY card output"
    # Width is 100 visible chars (box chars are single-width Unicode).
    assert len(top_lines[0]) == 100, (
        f"top border {top_lines[0]!r} length {len(top_lines[0])}, "
        f"expected 100 (clamp ceiling)"
    )


# ── NO_COLOR honored ────────────────────────────────


def test_no_color_env_disables_ansi_in_tty():
    """`NO_COLOR=1` must suppress ANSI escape codes even when stdout is a tty.
    De-facto standard documented at https://no-color.org."""
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
        f"NO_COLOR=1 set but ANSI escape codes leaked into output:\n{out}"
    )


# ── Long-text wrap inside card ──────────────────────


def test_long_tweet_wraps_inside_card(tty_env):
    """Body longer than the available content width wraps on word
    boundaries; every line still ends with the right border `│`."""
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
    # Every body line — i.e., every line that begins with `│` — has the
    # same width. (Last char also `│`.) Width consistency means borders
    # don't break when text is long.
    from twitter_mcp.server import _ANSI_RE

    body_lines = [line for line in out.splitlines() if line.startswith("│")]
    assert len(body_lines) >= 3, "long text should wrap to multiple lines"
    # Compare VISIBLE widths (raw len() differs across colored vs plain
    # lines because ANSI escape bytes don't render).
    widths = {len(_ANSI_RE.sub("", line)) for line in body_lines}
    assert len(widths) == 1, (
        f"body lines have inconsistent visible widths {widths!r} — borders broken"
    )


# ── Additional edge cases (cover the rare branches) ──


def test_box_line_truncates_oversized_unwrapped():
    """Single unwrappable token longer than the inner width gets cut with ellipsis."""
    from twitter_mcp.server import _box_line

    long_token = "x" * 120
    line = _box_line(80, long_token)
    assert line.endswith("│")
    assert "…" in line, "oversized token should be truncated with ellipsis"


def test_blank_paragraph_rendered_as_empty_card_line(tty_env):
    """A blank line in tweet body produces an empty-content card line, not nothing."""
    from twitter_mcp.server import _format_tweet

    out = _format_tweet(
        {
            "id": "1",
            "author": "alice",
            "author_name": "Alice",
            "text": "first paragraph\n\nsecond paragraph",  # blank in middle
            "created_at": "2026-01-01",
            "likes": 1,
            "retweets": 0,
        }
    )
    body_lines = [line for line in out.splitlines() if line.startswith("│")]
    # First + blank + second + counts + URL → ≥4 │ lines.
    assert len(body_lines) >= 4


def test_tweet_with_no_text_renders_blank_body(tty_env):
    """A tweet with empty `text` field still renders the body section."""
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
    # No crash + box still closed.
    assert "╰" in out


def test_user_with_created_and_url_renders_those_lines(tty_env):
    """Coverage: `created_at` + `url` paths in `_card_user`."""
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
    assert "Joined      Mon Jan 01 2024" in out
    assert "https://example.com" in out


def test_card_trends_empty_returns_no_trends_in_tty(tty_env):
    """When trends list is empty, fall back to plain '(no trends)'."""
    from twitter_mcp.server import _format_trends

    out = _format_trends({"trends": []})
    assert out == "(no trends)"


def test_card_trends_with_domain_context_renders_dash_separator(tty_env):
    """Coverage: trend with `domain_context` adds an `— context` suffix."""
    from twitter_mcp.server import _format_trends

    out = _format_trends(
        {"trends": [{"name": "AI", "tweets_count": 10000, "domain_context": "Tech"}]}
    )
    assert "Tech" in out
    assert "—" in out


def test_visible_len_ignores_ansi():
    """Padding logic must not count ANSI escapes toward the visible width."""
    from twitter_mcp.server import _visible_len

    plain = "hello"
    colored = "\x1b[1;36mhello\x1b[0m"
    assert _visible_len(plain) == 5
    assert _visible_len(colored) == 5  # same visible width


def test_colored_card_aligns_right_border(tty_env):
    """Visible-length padding regression: TTY-rendered lines with colored
    content must produce visible-width consistent with plain lines.

    Without _visible_len, `_box_line` would pad based on raw len(),
    over-counting ANSI bytes → right border drifts left."""
    from twitter_mcp.server import _ANSI_RE, _format_tweet

    out = _format_tweet(
        {
            "id": "20",
            "author": "jack",
            "author_name": "jack",
            "text": "hi",
            "created_at": "2026-01-01",
            "likes": 1,
            "retweets": 0,
        }
    )
    # Strip ANSI; every │-line has the same VISIBLE width.
    visible_lines = [
        _ANSI_RE.sub("", line) for line in out.splitlines() if line.startswith("│")
    ]
    widths = {len(line) for line in visible_lines}
    assert len(widths) == 1, (
        f"colored body lines have inconsistent visible widths "
        f"{widths!r} — _box_line is using raw len() not _visible_len()"
    )
