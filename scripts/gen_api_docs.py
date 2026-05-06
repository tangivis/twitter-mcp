"""Generate docs/api.md from `mcp._tool_manager._tools`.

Run this script BEFORE `mkdocs build` (the docs.yml CI workflow does
this automatically). The output `docs/api.md` is gitignored — generated
fresh on every build, so it can never drift from the live tool registry.

Why a standalone script + gitignore instead of `mkdocs-gen-files`:
the i18n plugin (`mkdocs-static-i18n`) doesn't reliably pick up virtual
files created by gen-files at on_files time — it scans on_config and
misses them. A real on-disk file feeds i18n the same way as any other
markdown page.

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
import sys
from collections import defaultdict
from pathlib import Path

# Ensure repo root is on sys.path so `twitter_mcp.server` resolves when
# this script is run as `python scripts/gen_api_docs.py` from any cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from twitter_mcp.server import mcp  # noqa: E402  (after sys.path tweak)


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


# Localized headers and section labels per locale. Tool docstrings stay
# English — Python signatures + types are language-neutral, and translating
# 57 docstrings would create maintenance drift.
_LOCALES = {
    "en": {
        "title": "MCP Tools API Reference",
        "intro": (
            "Auto-generated from the `@mcp.tool()`-decorated functions in "
            "`twitter_mcp.server` at docs build time. Total: "
        ),
        "intro_after_count": " tools. Each tool is documented once below with both invocation forms.",
        "table_header": "| Form | When to use |",
        "table_div": "|---|---|",
        "table_mcp": "| **MCP** | Inside an AI agent (Claude Code, Cursor, etc.) — the LLM picks the tool and fills args from your prompt. |",
        "table_cli": "| **CLI** | Shell scripts, debugging, automations. `twikit-mcp call <tool> key=value …` — same arg names, types coerced from strings. |",
        "source_note": (
            "Tool docstrings are the source of truth — if a section here looks wrong, "
            "fix the docstring in `twitter_mcp/server.py` and the next docs build will catch up."
        ),
        "cli_label": "**CLI:**",
        "no_doc": "_(no docstring)_",
        "sections": {
            "Tweets": "Tweets",
            "Users": "Users",
            "Lists": "Lists",
            "Communities": "Communities",
            "Articles": "Articles",
            "Direct Messages": "Direct Messages",
            "Discovery & notifications": "Discovery & notifications",
            "Scheduled tweets & polls": "Scheduled tweets & polls",
            "Other": "Other",
        },
    },
    "zh": {
        "title": "MCP 工具 API 参考",
        "intro": (
            "在文档构建时,从 `twitter_mcp.server` 里的 `@mcp.tool()` 装饰函数自动生成。共 "
        ),
        "intro_after_count": " 个工具。每个工具下面都同时给出 MCP 和 CLI 两种调用形式。",
        "table_header": "| 形式 | 何时用 |",
        "table_div": "|---|---|",
        "table_mcp": "| **MCP** | 在 AI agent(Claude Code、Cursor 等)里 — LLM 自己选工具并从你的 prompt 里填参数。 |",
        "table_cli": "| **CLI** | shell 脚本、调试、自动化。`twikit-mcp call <tool> key=value …` — 参数名一样,类型从字符串转换。 |",
        "source_note": (
            "工具的 docstring 是真理之源 — 如果下面某段看起来不对,改 `twitter_mcp/server.py` 里的 docstring,下一次构建就会同步过来。"
        ),
        "cli_label": "**CLI:**",
        "no_doc": "_(无 docstring)_",
        "sections": {
            "Tweets": "推文 (Tweets)",
            "Users": "用户 (Users)",
            "Lists": "列表 (Lists)",
            "Communities": "社群 (Communities)",
            "Articles": "文章 (Articles)",
            "Direct Messages": "私信 (DMs)",
            "Discovery & notifications": "发现与通知",
            "Scheduled tweets & polls": "定时推文与投票",
            "Other": "其他",
        },
    },
    "ja": {
        "title": "MCP ツール API リファレンス",
        "intro": (
            "ドキュメントビルド時に、`twitter_mcp.server` の `@mcp.tool()` デコレータ付き関数から自動生成されています。合計 "
        ),
        "intro_after_count": " ツール。各ツールについて MCP と CLI 両方の呼び出し形式を併記します。",
        "table_header": "| 形式 | 使う場面 |",
        "table_div": "|---|---|",
        "table_mcp": "| **MCP** | AI エージェント(Claude Code、Cursor 等)内 — LLM がツールを選び、プロンプトから引数を埋めます。 |",
        "table_cli": "| **CLI** | シェルスクリプト、デバッグ、自動化。`twikit-mcp call <tool> key=value …` — 引数名は同じ、型は文字列から変換。 |",
        "source_note": (
            "ツールの docstring が真実の源 — 下の説明が間違っているように見える場合は、`twitter_mcp/server.py` の docstring を修正すれば次回のビルドで反映されます。"
        ),
        "cli_label": "**CLI:**",
        "no_doc": "_(docstring なし)_",
        "sections": {
            "Tweets": "ツイート (Tweets)",
            "Users": "ユーザー (Users)",
            "Lists": "リスト (Lists)",
            "Communities": "コミュニティ (Communities)",
            "Articles": "記事 (Articles)",
            "Direct Messages": "DM",
            "Discovery & notifications": "発見と通知",
            "Scheduled tweets & polls": "予約投稿と投票",
            "Other": "その他",
        },
    },
}


def _write_api_page() -> None:
    """Emit a single English `docs/api.md`.

    The api page content is Python signatures + types + CLI examples —
    language-neutral, so localizing it would create maintenance churn
    without meaningful UX gain. Readers in zh/ja locale see this page
    in English (acceptable tradeoff for API ref since types and arg
    names are English regardless).
    """
    L = _LOCALES["en"]
    out_path = _REPO_ROOT / "docs" / "api.md"
    with out_path.open("w") as f:
        f.write(f"# {L['title']}\n\n")
        f.write(L["intro"])
        f.write(f"**{len(tools)}**")
        f.write(L["intro_after_count"] + "\n\n")
        f.write(L["table_header"] + "\n")
        f.write(L["table_div"] + "\n")
        f.write(L["table_mcp"] + "\n")
        f.write(L["table_cli"] + "\n\n")
        f.write(L["source_note"] + "\n\n")
        f.write("---\n\n")

        for section in SECTION_ORDER:
            names = by_section.get(section, [])
            if not names:
                continue
            f.write(f"## {L['sections'][section]}\n\n")
            for name in names:
                tool = tools[name]
                fn = getattr(tool, "fn", None) or getattr(tool, "func", None) or tool
                f.write(f"### `{name}`\n\n")
                try:
                    f.write(f"```python\n{name}{_signature_str(fn)}\n```\n\n")
                except (ValueError, TypeError):
                    pass
                doc = inspect.getdoc(fn) or L["no_doc"]
                f.write(doc + "\n\n")
                try:
                    cli = _cli_example(name, fn)
                    f.write(L["cli_label"] + "\n\n")
                    f.write(f"```bash\n{cli}\n```\n\n")
                except (ValueError, TypeError):
                    pass
                f.write("---\n\n")

        expected = sum(len(v) for v in by_section.values())
        if expected != len(tools):
            missing = sorted(set(tools) - {n for ns in by_section.values() for n in ns})
            f.write(
                "\n\n> ⚠️ **Categoriser mismatch** — these tools weren't placed: "
                + ", ".join(f"`{n}`" for n in missing)
                + ". Update `_categorize()` in `scripts/gen_api_docs.py`.\n"
            )


_write_api_page()
