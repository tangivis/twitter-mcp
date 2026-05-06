"""Generate docs/api.md from `mcp._tool_manager._tools` at build time.

Loaded by `mkdocs-gen-files` per `mkdocs.yml::plugins`. Runs inside a
mkdocs build, has access to the project's Python environment (i.e.
`twitter_mcp.server` is importable).

Output: a single markdown page that groups all 57 MCP tools by their
implicit category (read / write / list / community / dm / etc.). For
each tool we render the same source-of-truth docstring twice:

  - As **MCP usage** (how an AI agent invokes it)
  - As **CLI usage** (`twikit-mcp call <tool> key=value …`) for shell
    scripts and debugging — same arg names, same behavior.

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


def _annotation_str(ann) -> str:
    """Render a Python annotation in a way close to source form."""
    if ann is inspect.Parameter.empty:
        return ""
    if hasattr(ann, "__name__"):
        return ann.__name__
    return str(ann).replace("typing.", "")


def _signature_str(fn) -> str:
    """One-line type-annotated signature, no `self` / decorator clutter."""
    sig = inspect.signature(fn)
    parts = []
    for p in sig.parameters.values():
        ann = _annotation_str(p.annotation)
        ann_part = f": {ann}" if ann else ""
        default = "" if p.default is inspect.Parameter.empty else f" = {p.default!r}"
        parts.append(f"{p.name}{ann_part}{default}")
    return f"({', '.join(parts)})"


def _cli_example(name: str, fn) -> str:
    """Build a `twikit-mcp call <name> key=value` example.

    Pick required params (no default) + a couple of common optional ones,
    using a placeholder that hints at the expected type. The user-visible
    intent: 'show me what a real CLI invocation looks like'.
    """
    sig = inspect.signature(fn)
    args = []
    for p in sig.parameters.values():
        # Required params: always include. Otherwise: cap at 2 optional
        # examples so the line stays scannable.
        is_required = p.default is inspect.Parameter.empty
        if not is_required and len([a for a in args if a]) >= 2:
            break

        ann = _annotation_str(p.annotation)
        # Choose a placeholder that hints at the type without being
        # cute. Real users substitute their own values.
        if "int" in ann.lower():
            placeholder = "5" if "count" in p.name else "100"
        elif "bool" in ann.lower():
            placeholder = "true"
        elif p.name in ("screen_name", "user"):
            placeholder = "elonmusk"
        elif p.name in ("tweet_id", "id"):
            placeholder = "20"
        elif p.name in ("query",):
            placeholder = '"AI"'
        elif p.name == "list_id":
            placeholder = "1234567890"
        elif p.name == "community_id":
            placeholder = "1234567890"
        elif p.name == "text":
            placeholder = '"hello world"'
        else:
            placeholder = f"<{p.name}>"

        args.append(f"{p.name}={placeholder}")

    # If a tool is parameterless (rare), we still want a clean example.
    arg_part = " " + " ".join(args) if args else ""
    return f"twikit-mcp call {name}{arg_part}"


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
        f"**{len(tools)} tools**. Each tool is documented once below "
        "with both invocation forms.\n\n"
    )
    f.write(
        "| Form | When to use |\n"
        "|---|---|\n"
        "| **MCP** | Inside an AI agent (Claude Code, Cursor, etc.) — the LLM picks the tool and fills args from your prompt. |\n"
        "| **CLI** | Shell scripts, debugging, automations. `twikit-mcp call <tool> key=value …` — same arg names, types coerced from strings. |\n\n"
    )
    f.write(
        "Tool docstrings are the source of truth — if a section here "
        "looks wrong, fix the docstring in `twitter_mcp/server.py` and "
        "the next docs build will catch up.\n\n"
    )
    f.write("---\n\n")

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

            # Signature block.
            try:
                f.write(f"```python\n{name}{_signature_str(fn)}\n```\n\n")
            except (ValueError, TypeError):
                pass

            # Docstring.
            doc = inspect.getdoc(fn) or "_(no docstring)_"
            f.write(doc + "\n\n")

            # CLI usage example.
            try:
                cli = _cli_example(name, fn)
                f.write("**CLI:**\n\n")
                f.write(f"```bash\n{cli}\n```\n\n")
            except (ValueError, TypeError):
                pass

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
