"""Issue #109: the `mcp` SDK dependency must stay bounded on both ends.

Why this sentinel exists
------------------------

`twitter_mcp/server.py` is built on `mcp.server.mcpserver.MCPServer`.
The SDK has already renamed that class out from under us once: v1's
`mcp.server.fastmcp.FastMCP` became v2's `MCPServer`, and the entire
`mcp.server.fastmcp.*` namespace moved to `mcp.server.mcpserver.*` with
no compatibility shim left behind. A resolve that crosses a major line
therefore breaks us at import time, before a single tool runs.

`uv.lock` does not protect against this. The lock pins our CI and dev
environment; end users install with `uv tool install twikit-mcp` /
`pip install twikit-mcp`, which resolves `mcp[cli]` fresh against the
index with whatever ceiling `pyproject.toml` declares. With no ceiling,
the day `mcp` 3.0.0 lands every new install dies the same way.

Phase 3 (0.1.39) moved the floor to v2 and this file with it. If you are
here doing the v3 migration: flip the import assertions and the ceiling
in the *same* PR, exactly as phase 3 did.

Parsed with a regex rather than `tomllib` on purpose: `tomllib` is
3.11+, and `requires-python` here is `>=3.10`.
"""

import re
from pathlib import Path

import pytest

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# `"mcp[cli]>=2,<3",` → captures the specifier `>=2,<3`.
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
    """A bare `mcp[cli]` would let a fresh install pull the next major SDK.
    v2 renamed `FastMCP` → `MCPServer` and deleted the old namespace
    outright; assume v3 is free to do the same (issue #109)."""
    spec = _mcp_specifier()
    assert "<" in spec, (
        f"`mcp` dependency specifier is {spec!r} — no upper bound. A fresh "
        f"`uv tool install twikit-mcp` will pull the next major SDK the day "
        f"it ships, and `from mcp.server.mcpserver import MCPServer` may "
        f"fail at import. Keep a ceiling until that migration is done."
    )


def test_mcp_dependency_upper_bound_excludes_the_next_major():
    """The bound must actually exclude the 3.x line, not merely exist."""
    spec = _mcp_specifier()
    upper = re.search(r"<\s*([0-9][^,\s]*)", spec)
    assert upper, f"expected a `<VERSION` clause in {spec!r}"
    major = int(re.match(r"(\d+)", upper.group(1)).group(1))
    assert major <= 3, (
        f"`mcp` upper bound is {upper.group(1)!r}, which admits an SDK major "
        f"beyond v2. Crossing a major line has already required an "
        f"import/constructor rename once (issue #109 phase 3) — bump this "
        f"bound in the same PR as that migration, not before."
    )


def test_mcp_dependency_floor_is_v2():
    """Guard the floor too: the code imports `mcp.server.mcpserver`, which
    does not exist in v1. An accidental `mcp[cli]<3` alone would let a
    resolver pick a 1.x that breaks at import."""
    spec = _mcp_specifier()
    assert ">=" in spec, (
        f"`mcp` dependency specifier is {spec!r} — no lower bound. Keep a "
        f"floor so resolvers can't pick an ancient SDK to satisfy `<3`."
    )
    lower = re.search(r">=\s*([0-9][^,\s]*)", spec)
    assert lower, f"expected a `>=VERSION` clause in {spec!r}"
    major = int(re.match(r"(\d+)", lower.group(1)).group(1))
    assert major >= 2, (
        f"`mcp` floor is {lower.group(1)!r}, which admits SDK v1. v1 has no "
        f"`mcp.server.mcpserver` module, so server.py fails at import — the "
        f"floor moved to v2 in issue #109 phase 3 and must stay there."
    )


@pytest.mark.parametrize("forbidden", ["mcp.server.fastmcp"])
def test_server_targets_the_v2_import_path(forbidden):
    """Cross-check: while the pin says `>=2`, the code must import from the
    v2 path. If someone reverts the imports without moving the pin (or vice
    versa) this catches the mismatch."""
    server_src = (_PYPROJECT.parent / "twitter_mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    assert forbidden not in server_src, (
        f"server.py imports from {forbidden!r} (SDK v1) while pyproject pins "
        f"`mcp>=2`. That namespace no longer exists in v2 — move both "
        f"together, see issue #109 phase 3."
    )
    assert "from mcp.server.mcpserver import MCPServer" in server_src, (
        "server.py no longer imports MCPServer from the v2 path; if this is "
        "the v3 migration, update this sentinel and the pin together "
        "(issue #109)."
    )


def test_server_advertises_its_package_version():
    """`serverInfo.version` in the initialize response.

    SDK v1 filled this in with its own version when left unset; v2
    defaults it to `""`, which would silently downgrade what clients see.
    We pass the package version explicitly — assert it survives.
    """
    from twitter_mcp import server

    assert server.mcp.version == server._get_version()
    assert server.mcp.version, "serverInfo.version is empty — clients lose it"
