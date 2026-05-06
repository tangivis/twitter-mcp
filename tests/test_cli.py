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
    for sub in ("serve", "list", "call"):
        assert sub in out
