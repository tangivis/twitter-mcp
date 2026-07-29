"""Issue #109 phase 1: the `mcp` SDK dependency must carry an upper bound.

Why this sentinel exists
------------------------

`twitter_mcp/server.py` is built on `mcp.server.fastmcp.FastMCP`. The
Python SDK v2 (implementing the 2026-07-28 spec) **renames that class**
— `FastMCP` becomes `MCPServer`, and everything under
`mcp.server.fastmcp.*` moves to `mcp.server.mcpserver.*`. So a v2
resolve breaks us at import time, before a single tool runs.

`uv.lock` does not protect against this. The lock pins our CI and dev
environment; end users install with `uv tool install twikit-mcp` /
`pip install twikit-mcp`, which resolves `mcp[cli]` fresh against the
index with whatever ceiling `pyproject.toml` declares. With no ceiling,
the day `mcp` 2.0.0 leaves pre-release every new install dies.

Parsed with a regex rather than `tomllib` on purpose: `tomllib` is
3.11+, and `requires-python` here is `>=3.10`.
"""

import re
from pathlib import Path

import pytest

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# `"mcp[cli]>=1.27,<2",` → captures the specifier `>=1.27,<2`.
# Extras are optional so the sentinel survives a future `"mcp>=..."`.
_MCP_DEP_RE = re.compile(r"""["']mcp(?:\[[^\]]*\])?([^"']*)["']""")


def _mcp_specifier() -> str:
    """The version specifier declared for the `mcp` runtime dependency."""
    src = _PYPROJECT.read_text(encoding="utf-8")
    # Narrow to the [project] dependencies array so `keywords = ["mcp", ...]`
    # and the dev/docs groups can't be mistaken for the runtime dep.
    block = re.search(r"^dependencies = \[(.*?)^\]", src, re.S | re.M)
    assert block, "could not locate [project] dependencies array in pyproject.toml"
    match = _MCP_DEP_RE.search(block.group(1))
    assert match, (
        "no `mcp` entry found in [project] dependencies — did the runtime "
        "dependency get renamed or removed?"
    )
    return match.group(1).strip()


def test_mcp_dependency_declares_an_upper_bound():
    """A bare `mcp[cli]` would let a fresh install pull SDK v2, which
    renamed `FastMCP` → `MCPServer` and breaks `twitter_mcp/server.py`
    at import (issue #109)."""
    spec = _mcp_specifier()
    assert "<" in spec, (
        f"`mcp` dependency specifier is {spec!r} — no upper bound. A fresh "
        f"`uv tool install twikit-mcp` will pull SDK v2 as soon as 2.0.0 "
        f"leaves pre-release, and `from mcp.server.fastmcp import FastMCP` "
        f"will fail at import. Pin `<2` until issue #109 phase 3 lands."
    )


def test_mcp_dependency_upper_bound_excludes_v2():
    """The bound must actually exclude the 2.x line, not merely exist."""
    spec = _mcp_specifier()
    upper = re.search(r"<\s*([0-9][^,\s]*)", spec)
    assert upper, f"expected a `<VERSION` clause in {spec!r}"
    major = int(re.match(r"(\d+)", upper.group(1)).group(1))
    assert major <= 2, (
        f"`mcp` upper bound is {upper.group(1)!r}, which admits the v2 SDK. "
        f"Migrating past v2 requires the import/constructor rename tracked "
        f"in issue #109 phase 3 — bump this bound in the same PR, not before."
    )


def test_mcp_dependency_keeps_a_lower_bound():
    """Guard the floor too — the codebase uses `@mcp.tool()` behavior that
    predates neither, but an accidental `mcp[cli]<2` alone would allow
    resolving something ancient."""
    spec = _mcp_specifier()
    assert ">=" in spec, (
        f"`mcp` dependency specifier is {spec!r} — no lower bound. Keep a "
        f"floor so resolvers can't pick an ancient SDK to satisfy `<2`."
    )


@pytest.mark.parametrize("forbidden", ["mcp.server.mcpserver"])
def test_server_still_targets_v1_import_path(forbidden):
    """Cross-check: while the pin says `<2`, the code must still import from
    the v1 path. If someone migrates the imports without moving the pin
    (or vice versa) this catches the mismatch."""
    server_src = (
        _PYPROJECT.parent / "twitter_mcp" / "server.py"
    ).read_text(encoding="utf-8")
    assert forbidden not in server_src, (
        f"server.py imports from {forbidden!r} (SDK v2) while pyproject still "
        f"pins `mcp<2`. Move both together — see issue #109 phase 3."
    )
    assert "from mcp.server.fastmcp import FastMCP" in server_src, (
        "server.py no longer imports FastMCP from the v1 path; if this is the "
        "v2 migration, update this sentinel and the pin together (issue #109)."
    )
