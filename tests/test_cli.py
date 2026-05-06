"""Tests for the CLI subcommand layer in `twitter_mcp.server.main`.

Two layers of coverage:

1. **Unit tests** of the helper functions (`_coerce`, `_list_tools_text`,
   `_parse_kv_pairs`, `_call_tool_async`) — fast, exercise the type
   coercion + lookup logic without spawning a process.
2. **Subprocess integration tests** that run `python -m twitter_mcp.server`
   end-to-end, asserting the binary's behavior is correct from the
   user's perspective.

We do NOT live-test the `serve` subcommand here — that's the existing
MCP server behavior and `tests/test_server.py::test_mcp_handshake_*`
already covers it.
"""

import json
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from tests.test_tools import _fake_user_full
from twitter_mcp import server
from twitter_mcp.server import (
    _call_tool_async,
    _coerce,
    _list_tools_text,
    _parse_kv_pairs,
)

# ── _coerce ──────────────────────────────────────────


def test_coerce_str_passthrough():
    assert _coerce("hello", str) == "hello"


def test_coerce_int():
    assert _coerce("42", int) == 42


def test_coerce_float():
    assert _coerce("3.14", float) == 3.14


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
        ("anything-else", False),
    ],
)
def test_coerce_bool(raw, expected):
    assert _coerce(raw, bool) is expected


def test_coerce_pep604_union_int_or_none_with_value():
    """`int | None` → unwrap to int when value is non-empty."""
    assert _coerce("42", int | None) == 42


def test_coerce_pep604_union_int_or_none_with_empty_string_returns_none():
    """`int | None` + empty string → explicit None (CLI escape hatch)."""
    assert _coerce("", int | None) is None


def test_coerce_optional_str_passes_through():
    assert _coerce("hi", str | None) == "hi"


def test_coerce_unknown_annotation_falls_back_to_string():
    """Anything we don't recognise → pass the raw string. The tool's own
    validation surfaces a ToolError if the value is wrong."""

    class Weird:
        pass

    assert _coerce("anything", Weird) == "anything"


def test_coerce_pep604_union_falls_through_to_next_member_on_error():
    """`int | str`: 'abc' fails int(), falls through to str (passthrough)."""
    assert _coerce("abc", int | str) == "abc"


# ── _parse_kv_pairs ──────────────────────────────────


def test_parse_kv_pairs_simple():
    assert _parse_kv_pairs(["a=1", "b=2"]) == {"a": "1", "b": "2"}


def test_parse_kv_pairs_value_can_contain_equals():
    """Splitting only on the FIRST `=` keeps URLs / base64 / etc. intact."""
    assert _parse_kv_pairs(["url=https://x.com/a=b"]) == {"url": "https://x.com/a=b"}


def test_parse_kv_pairs_empty_list():
    assert _parse_kv_pairs([]) == {}


def test_parse_kv_pairs_rejects_bare_value():
    with pytest.raises(SystemExit, match="key=value"):
        _parse_kv_pairs(["positional"])


# ── _list_tools_text ─────────────────────────────────


def test_list_tools_text_is_sorted():
    out = _list_tools_text()
    lines = out.splitlines()
    assert lines == sorted(lines)
    assert "send_tweet" in lines
    assert "get_tweet" in lines
    # Spot-check community tool from latest tier.
    assert "join_community" in lines


def test_list_tools_text_count_matches_registry():
    out = _list_tools_text()
    assert len(out.splitlines()) == len(server.mcp._tool_manager._tools)


# ── _call_tool_async ─────────────────────────────────


async def test_call_tool_unknown_tool_exits():
    with pytest.raises(SystemExit, match="Unknown tool"):
        await _call_tool_async("definitely_not_a_tool", {})


async def test_call_tool_unknown_arg_exits(monkeypatch):
    """The error names the tool, the bad arg, AND the legal arg list."""
    with pytest.raises(SystemExit) as exc:
        await _call_tool_async("send_tweet", {"bogus": "x"})
    msg = str(exc.value)
    assert "bogus" in msg
    assert "send_tweet" in msg
    assert "text" in msg  # listed as a valid arg


async def test_call_tool_get_user_info_with_mock(monkeypatch):
    """Happy path: int coercion happens via _coerce, output is JSON-shaped."""
    fake_client = AsyncMock()
    fake_client.get_user_by_screen_name = AsyncMock(return_value=_fake_user_full())
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=fake_client))

    out_str = await _call_tool_async("get_user_info", {"screen_name": "ClaudeDevs"})
    out = json.loads(out_str)
    assert out["screen_name"] == "ClaudeDevs"
    fake_client.get_user_by_screen_name.assert_awaited_once_with("ClaudeDevs")


async def test_call_tool_int_coercion(monkeypatch):
    """count=5 (string) is coerced to int via the tool's int annotation."""
    fake_client = AsyncMock()
    fake_client.get_timeline = AsyncMock(return_value=[])
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=fake_client))

    await _call_tool_async("get_timeline", {"count": "5"})
    fake_client.get_timeline.assert_awaited_once_with(count=5)


# ── Subprocess integration ───────────────────────────
#
# These spawn the actual entry point. They're slower but assert the
# user-visible behavior of the binary is correct (argparse routing,
# stdout/stderr split, exit codes).


def _run_cli(*args: str, **popen_kwargs):
    """Invoke `python -m twitter_mcp.server <args>`, capturing IO."""
    return subprocess.run(
        [sys.executable, "-m", "twitter_mcp.server", *args],
        capture_output=True,
        text=True,
        timeout=15,
        **popen_kwargs,
    )


def test_subprocess_list_lists_tools():
    r = _run_cli("list")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert "send_tweet" in lines
    assert "get_tweet" in lines
    assert len(lines) == len(server.mcp._tool_manager._tools)


def test_subprocess_version_flag():
    r = _run_cli("--version")
    assert r.returncode == 0
    # Format: "twikit-mcp <version>"; in the test sandbox version is
    # "unknown" because the package isn't installed via pip — we just
    # check the prefix.
    assert r.stdout.startswith("twikit-mcp ")


def test_subprocess_call_unknown_tool_nonzero_exit():
    r = _run_cli("call", "nope_not_real")
    assert r.returncode != 0
    # SystemExit string lands on stderr by default for argparse-driven
    # apps; either stream is fine to assert on.
    combined = r.stdout + r.stderr
    assert "Unknown tool" in combined


def test_subprocess_call_bad_kv_form_nonzero_exit():
    r = _run_cli("call", "send_tweet", "no_equals_sign")
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert "key=value" in combined


def test_subprocess_help_mentions_subcommands():
    r = _run_cli("--help")
    assert r.returncode == 0
    out = r.stdout
    # Both machine-shaped and human-shaped subcommands are advertised.
    for sub in ("serve", "list", "call", "tweet", "user", "tl", "search", "trends"):
        assert sub in out


# ── Human-friendly formatters ────────────────────────


def test_compact_num_passes_small_unchanged():
    from twitter_mcp.server import _compact_num

    assert _compact_num(0) == "0"
    assert _compact_num(42) == "42"
    assert _compact_num(9999) == "9,999"


def test_compact_num_thousands_to_K():
    from twitter_mcp.server import _compact_num

    assert _compact_num(12_500) == "12.5K"
    assert _compact_num(999_500) == "999.5K"


def test_compact_num_millions_billions():
    from twitter_mcp.server import _compact_num

    assert _compact_num(1_500_000) == "1.5M"
    assert _compact_num(2_300_000_000) == "2.3B"


def test_compact_num_handles_non_numeric():
    """Defensive: tools sometimes pass through whatever twikit returns."""
    from twitter_mcp.server import _compact_num

    assert _compact_num(None) == "None"
    assert _compact_num("not a number") == "not a number"


def test_format_tweet_renders_unicode_natively():
    """JSON-escape bug regression: real text content (Greek, 中文, …) must
    show as native characters in the human-format output."""
    from twitter_mcp.server import _format_tweet

    block = _format_tweet(
        {
            "id": "1234567890",
            "author": "pathfinderSport",
            "author_name": "Pathfinder Sports",
            "text": "Άρσεναλ - Σάντερλαντ: (X) 0-0 τελικό",
            "created_at": "Sat Feb 21 16:55:22 +0000 2009",
            "likes": 7269,
            "retweets": 5473,
        }
    )
    # All the pieces show up as readable text — no \uXXXX escapes anywhere.
    assert "@pathfinderSport · Pathfinder Sports" in block
    assert "Άρσεναλ - Σάντερλαντ" in block
    assert "❤ 7,269" in block
    assert "🔁 5,473" in block
    assert "https://x.com/pathfinderSport/status/1234567890" in block


def test_format_tweet_tolerates_missing_fields():
    """Tools sometimes omit author_name / created_at / counts on edge cases."""
    from twitter_mcp.server import _format_tweet

    block = _format_tweet({"id": "1", "author": "alice", "text": "hi"})
    assert "@alice" in block
    assert "hi" in block


def test_format_tweet_list_numbers_entries():
    from twitter_mcp.server import _format_tweet_list

    out = _format_tweet_list(
        [
            {"id": "1", "author": "a", "text": "first"},
            {"id": "2", "author": "b", "text": "second"},
        ]
    )
    assert "[1]" in out and "[2]" in out
    assert "first" in out and "second" in out


def test_format_tweet_list_handles_empty():
    from twitter_mcp.server import _format_tweet_list

    assert _format_tweet_list([]) == "(no tweets)"


def test_format_user_renders_compact_followers():
    from twitter_mcp.server import _format_user

    block = _format_user(
        {
            "screen_name": "elonmusk",
            "name": "Elon Musk",
            "is_blue_verified": True,
            "description": "CEO",
            "followers_count": 200_453_876,
            "following_count": 1_123,
            "tweets_count": 50_432,
            "location": "Texas, USA",
            "url": "https://example.com",
            "created_at": "Tue Jun 02 …",
        }
    )
    assert "@elonmusk" in block
    assert "Elon Musk" in block
    assert "✓" in block  # verified glyph
    assert "Followers: 200.5M" in block
    assert "Texas, USA" in block
    assert "https://x.com/elonmusk" in block


def test_format_trends_numbered():
    from twitter_mcp.server import _format_trends

    out = _format_trends(
        {
            "trends": [
                {"name": "AI", "tweets_count": 50000, "domain_context": "Tech"},
                {"name": "コーヒー", "tweets_count": 1234},
            ]
        }
    )
    # Native unicode preserved.
    assert "コーヒー" in out
    assert " 1." in out and " 2." in out
    assert "50.0K tweets" in out
    assert "Tech" in out


def test_format_trends_empty():
    from twitter_mcp.server import _format_trends

    assert _format_trends({"trends": []}) == "(no trends)"
    assert _format_trends({}) == "(no trends)"


# ── Human-CLI subcommands (subprocess integration) ────


def test_subprocess_tweet_unknown_id_clean_error():
    """`tweet` with bogus id → exit 2 (ToolError translated cleanly)."""
    r = _run_cli("tweet", "definitely_not_a_tweet_id_123")
    assert r.returncode != 0


def test_subprocess_user_unknown_clean_error():
    r = _run_cli("user", "screen_name_that_does_not_exist_xyz_42")
    assert r.returncode != 0


# ── Human-CLI dispatcher (unit-mocked) ───────────────


async def _mock_call_tool(monkeypatch, mapping: dict[str, str]):
    """Patch `_call_tool_async` to return fixed JSON strings keyed by tool name."""
    from unittest.mock import AsyncMock

    async def fake(tool_name, kwargs):
        return mapping[tool_name]

    monkeypatch.setattr(server, "_call_tool_async", AsyncMock(side_effect=fake))


async def test_human_tweet_calls_get_tweet_and_formats(monkeypatch):
    await _mock_call_tool(
        monkeypatch,
        {
            "get_tweet": json.dumps(
                {"id": "20", "author": "jack", "text": "hi", "likes": 1, "retweets": 0}
            )
        },
    )
    out = await server._human_tweet("20")
    assert "@jack" in out
    assert "hi" in out


async def test_human_user_calls_get_user_info(monkeypatch):
    await _mock_call_tool(
        monkeypatch,
        {
            "get_user_info": json.dumps(
                {
                    "screen_name": "alice",
                    "name": "Alice",
                    "followers_count": 0,
                    "following_count": 0,
                    "tweets_count": 0,
                }
            )
        },
    )
    out = await server._human_user("alice")
    assert "@alice" in out


async def test_human_timeline_renders_list(monkeypatch):
    await _mock_call_tool(
        monkeypatch,
        {
            "get_timeline": json.dumps(
                [
                    {"id": "1", "author": "a", "text": "first"},
                    {"id": "2", "author": "b", "text": "second"},
                ]
            )
        },
    )
    out = await server._human_timeline(20)
    assert "[1]" in out and "[2]" in out


async def test_human_search_uses_top_product(monkeypatch):
    """search subcommand pins product='Top' — verify it's passed through."""
    captured = {}

    async def fake_call(tool_name, kwargs):
        captured["tool"] = tool_name
        captured["kwargs"] = kwargs
        return json.dumps([])

    from unittest.mock import AsyncMock

    monkeypatch.setattr(server, "_call_tool_async", AsyncMock(side_effect=fake_call))
    await server._human_search("AI", 5)
    assert captured["tool"] == "search_tweets"
    assert captured["kwargs"] == {"query": "AI", "count": "5", "product": "Top"}


async def test_human_trends_renders(monkeypatch):
    await _mock_call_tool(
        monkeypatch,
        {"get_trends": json.dumps({"trends": [{"name": "AI", "tweets_count": 10000}]})},
    )
    out = await server._human_trends(20)
    assert "AI" in out
    assert "10.0K" in out


# ── ensure_ascii regression for tool outputs ─────────


async def test_tool_output_preserves_unicode_raw(monkeypatch):
    """Greek-tweet regression: get_tweet's JSON output must contain native
    non-ASCII chars, not `\\uXXXX` escapes. This is the bug a user hit
    when piping CLI output back through their terminal."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    fake_tweet = SimpleNamespace(
        id="1234567890",
        text="Άρσεναλ - Σάντερλαντ: (X) 0-0 τελικό",
        user=SimpleNamespace(screen_name="pathfinderSport", name="Pathfinder Sports"),
        favorite_count=7269,
        retweet_count=5473,
        created_at="Sat Feb 21 16:55:22 +0000 2009",
        in_reply_to=None,
        conversation_id=None,
    )
    fake_client = AsyncMock()
    fake_client.get_tweets_by_ids = AsyncMock(return_value=[fake_tweet])
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=fake_client))

    out = await server.get_tweet("1234567890")
    # Negative: NOT escaped.
    assert "\\u" not in out
    # Positive: native characters present in the raw string.
    assert "Άρσεναλ" in out
