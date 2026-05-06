"""Generate docs/api.md from `mcp._tool_manager._tools` at build time.

Loaded by `mkdocs-gen-files` per `mkdocs.yml::plugins`. Runs inside a
mkdocs build, has access to the project's Python environment (i.e.
`twitter_mcp.server` is importable).

Output: a single markdown page that groups all 57 MCP tools by their
implicit category (read / write / list / community / dm / etc.) and
emits one mkdocstrings `:::` directive per tool. mkdocstrings then
resolves each ref into a heading + signature + docstring at render
time — no need to commit the rendered file.

We don't hand-write `api.md` because the tool set changes on most PRs
and a hand-written file always drifts.
"""

import inspect
from collections import defaultdict

import mkdocs_gen_files

from twitter_mcp.server import mcp


def _categorize(name: str) -> str:
    """Bucket a tool name into a section. Heuristic; tweak when tool count grows."""
    if name.endswith(("_dm", "dm_history")) or "dm" in name:
        return "Direct Messages"
    if "list" in name:
        return "Lists"
    if "communit" in name:
        return "Communities"
    if any(
        name.startswith(p)
        for p in (
            "get_user",
            "follow_",
            "unfollow_",
            "block",
            "mute",
            "unblock",
            "unmute",
            "search_user",
        )
    ):
        return "Users"
    if any(
        name.startswith(p)
        for p in (
            "get_tweet",
            "get_timeline",
            "search_tweets",
            "send_tweet",
            "delete_tweet",
            "like_",
            "unfavorite_",
            "retweet",
            "delete_retweet",
            "bookmark",
            "delete_bookmark",
            "get_bookmarks",
            "get_favoriters",
            "get_retweeters",
        )
    ):
        return "Tweets"
    if "article" in name:
        return "Articles"
    if "trend" in name or "notification" in name:
        return "Discovery & notifications"
    if "scheduled" in name or "poll" in name or name == "vote":
        return "Scheduled tweets & polls"
    return "Other"


def _signature_str(fn) -> str:
    """Render a one-line type-annotated signature, no `self` / decorator clutter."""
    sig = inspect.signature(fn)
    params = []
    for p in sig.parameters.values():
        if p.annotation is inspect.Parameter.empty:
            ann = ""
        else:
            ann = f": {p.annotation.__name__ if hasattr(p.annotation, '__name__') else p.annotation}"
        default = "" if p.default is inspect.Parameter.empty else f" = {p.default!r}"
        params.append(f"{p.name}{ann}{default}")
    return f"({', '.join(params)})"


tools = mcp._tool_manager._tools
by_section: dict[str, list[str]] = defaultdict(list)
for name in sorted(tools):
    by_section[_categorize(name)].append(name)


# Stable section ordering — most user-facing first, "Other" last.
SECTION_ORDER = [
    "Tweets",
    "Users",
    "Lists",
    "Communities",
    "Articles",
    "Direct Messages",
    "Discovery & notifications",
    "Scheduled tweets & polls",
    "Other",
]


with mkdocs_gen_files.open("api.md", "w") as f:
    f.write("# MCP Tools API Reference\n\n")
    f.write(
        "Auto-generated from the `@mcp.tool()`-decorated functions in "
        "`twitter_mcp.server` at docs build time. Total: "
        f"**{len(tools)} tools**.\n\n"
    )
    f.write(
        "Tool docstrings are the source of truth — if a section here "
        "looks wrong, fix the docstring in `twitter_mcp/server.py` and "
        "the next docs build will catch up.\n\n"
    )

    for section in SECTION_ORDER:
        names = by_section.get(section, [])
        if not names:
            continue
        f.write(f"## {section}\n\n")
        for name in names:
            tool = tools[name]
            # Pull the underlying fn off twikit/FastMCP's wrapper if needed.
            fn = getattr(tool, "fn", None) or getattr(tool, "func", None) or tool
            f.write(f"### `{name}`\n\n")
            try:
                f.write(f"```python\n{name}{_signature_str(fn)}\n```\n\n")
            except (ValueError, TypeError):
                pass
            doc = inspect.getdoc(fn) or "_(no docstring)_"
            f.write(doc + "\n\n")
            f.write("---\n\n")

    # Catch any tool that didn't fit a section — surface so we tweak
    # the categoriser instead of silently dropping it.
    expected = sum(len(v) for v in by_section.values())
    if expected != len(tools):
        missing = sorted(set(tools) - {n for ns in by_section.values() for n in ns})
        f.write(
            "\n\n> ⚠️ **Categoriser mismatch** — these tools weren't placed: "
            + ", ".join(f"`{n}`" for n in missing)
            + ". Update `_categorize()` in `scripts/gen_api_docs.py`.\n"
        )
