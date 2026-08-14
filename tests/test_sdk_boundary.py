"""Issue #109 phase 2: the SDK's private tool registry has ONE call site.

`MCPServer._tool_manager._tools` is private API — a leading underscore on
both hops, no compatibility promise. We depend on it in shipped code
(`twikit-mcp list` / `twikit-mcp call`), in the docs generator, and in
~70 per-tool schema assertions across the test suite.

That breadth is the actual cost of the v2 migration: an SDK-side rename
would be a 70-file sweep instead of a one-line edit. `_registered_tools()`
in `twitter_mcp/server.py` is the choke point; this sentinel keeps it the
*only* one, so phase 3 stays cheap.

(Verified 2026-08-14 against `mcp[cli]==2.0.0`: v2's `MCPServer` still
exposes `_tool_manager._tools` with the same `Tool` shape — `.parameters`,
`.fn`, `.description`, `.run`. So the accessor body is expected to survive
the migration untouched. That is luck, not contract: keep the choke point.)
"""

from pathlib import Path

from twitter_mcp import server

_REPO = Path(__file__).resolve().parent.parent

# Built at runtime rather than written literally — belt and braces with the
# self-exclusion below.
_NEEDLE = "_tool" + "_manager"

# Directories that are not ours to police: the vendored twikit tree carries
# upstream's own code, and virtualenvs / build output hold installed copies.
_SKIP_DIRS = {"_vendor", ".venv", "venv", ".git", "site", "build", "dist"}

# This file names the attribute path it forbids (in prose, for whoever trips
# the assertion) so it cannot police itself.
_SELF = Path(__file__).resolve()


def _python_sources():
    """Every first-party .py file in the repo, except this sentinel."""
    for path in _REPO.rglob("*.py"):
        if path.resolve() == _SELF:
            continue
        if _SKIP_DIRS.isdisjoint(path.relative_to(_REPO).parts):
            yield path


def _needle_hits():
    """(path, line_number, line) for every private-registry reference."""
    for path in _python_sources():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _NEEDLE in line:
                yield path, lineno, line.strip()


def test_private_tool_registry_has_exactly_one_call_site():
    """The whole point of phase 2. If this fails, someone reached past
    `_registered_tools()` straight into the SDK's privates again."""
    hits = list(_needle_hits())
    rendered = "\n".join(f"  {p.relative_to(_REPO)}:{n}: {line}" for p, n, line in hits)
    assert len(hits) == 1, (
        f"expected exactly 1 reference to the SDK's private tool registry "
        f"(the body of `server._registered_tools()`), found {len(hits)}:\n"
        f"{rendered}\n"
        f"Route new code through `server._registered_tools()` instead — it "
        f"keeps the SDK v2 migration a one-line change (issue #109 phase 2)."
    )


def test_the_one_call_site_is_the_accessor():
    """...and it lives where we think it does."""
    (path, _, _) = next(iter(_needle_hits()))
    assert path == _REPO / "twitter_mcp" / "server.py", (
        f"the private registry is referenced from {path.relative_to(_REPO)}, "
        f"not from the `_registered_tools()` accessor in twitter_mcp/server.py"
    )


def test_registered_tools_returns_the_live_registry():
    """The accessor must hand back the real thing, not a copy — callers
    index it by tool name and read `.parameters` / `.fn` / `.run`."""
    tools = server._registered_tools()
    assert isinstance(tools, dict)
    assert "get_tweet" in tools
    tool = tools["get_tweet"]
    for attr in ("parameters", "fn", "description", "run"):
        assert hasattr(tool, attr), f"registry entries lost `.{attr}`"


def test_registered_tools_covers_every_tool():
    """Sanity: the accessor is not filtering anything out."""
    assert len(server._registered_tools()) >= 59
