"""Issue #73 sentinel: live-smoke must exercise every idempotent read tool.

Scans `_registered_tools()` at import time to discover the full
tool registry. Buckets tools as mutating (explicit allowlist) vs
idempotent. For every idempotent tool, asserts a `check("<tool>", …)`
invocation exists in `.github/workflows/live-smoke.yml`.

This is the gate that prevents future drift: when someone adds a new
read tool, this test forces them to either add it to live-smoke OR mark
it mutating in `_MUTATING` (and document why).

Mutating tools are deliberately mock-only — running them against a real
burner cookie would create state (likes / follows / blocks / DMs) and
quickly run afoul of X's anti-abuse rate limits.
"""

import re
from pathlib import Path

# Tools that mutate state — never tested against real X. If you add a
# new mutating tool, append it here with a one-line rationale comment.
_MUTATING = {
    # Tweet content
    "send_tweet",
    "delete_tweet",
    # Engagement
    "like_tweet",
    "unfavorite_tweet",
    "retweet",
    "delete_retweet",
    # Social graph
    "follow_user",
    "unfollow_user",
    # Moderation
    "block_user",
    "unblock_user",
    "mute_user",
    "unmute_user",
    # Bookmarks
    "bookmark_tweet",
    "delete_bookmark",
    # DMs
    "send_dm",
    "send_dm_to_group",
    "delete_dm",
    # Lists
    "create_list",
    "edit_list",
    "add_list_member",
    "remove_list_member",
    # Scheduling
    "create_scheduled_tweet",
    "delete_scheduled_tweet",
    # Polls
    "create_poll",
    "vote",
    # Communities
    "join_community",
    "leave_community",
    "request_to_join_community",
    # Side-effecting (writes to disk via yt-dlp subprocess)
    "download_tweet_video",
}

# Idempotent reads that have no live-smoke surface because they never
# call X. Marking these `_MUTATING` would be a lie — they mutate nothing.
# They read a SQLite file the user's own browser wrote, so a burner
# cookie and a network round-trip prove nothing about them, and CI has no
# such file to read. They are covered instead by tests/test_xchat_local.py,
# which drives the real code against a real database — stronger evidence
# than live-smoke gives any tool on the list above.
#
# Add here ONLY if the tool genuinely makes no request to X. If it talks
# to X at all, it belongs in live-smoke.
_NO_LIVE_SURFACE = {
    "xchat_status",  # reads local XChat SQLite (issue #118)
    "xchat_list_conversations",
    "xchat_get_history",
}


def test_live_smoke_covers_all_idempotent_reads():
    """Issue #73 acceptance criterion 1: all 25 idempotent reads are
    invoked from `live-smoke.yml` against real X."""
    from twitter_mcp import server

    all_tools = set(server._registered_tools().keys())

    # Sanity: every name in _MUTATING actually exists. Catches typos.
    unknown_mutating = _MUTATING - all_tools
    assert not unknown_mutating, (
        f"_MUTATING references unregistered tools: {unknown_mutating!r}. "
        f"Update this test's allowlist to match server.py's registry."
    )
    unknown_local = _NO_LIVE_SURFACE - all_tools
    assert not unknown_local, (
        f"_NO_LIVE_SURFACE references unregistered tools: {unknown_local!r}."
    )
    overlap = _MUTATING & _NO_LIVE_SURFACE
    assert not overlap, f"a tool cannot be both mutating and X-free: {overlap!r}"

    idempotent = all_tools - _MUTATING - _NO_LIVE_SURFACE

    smoke_yaml = Path(__file__).parent.parent / ".github/workflows/live-smoke.yml"
    # Windows default encoding is cp1252; pin utf-8 since the workflow
    # contains ✓/✗/—/📍 etc. (same fix pattern as scripts/gen_api_docs.py
    # for issue #58 — see commit 4d2f997).
    src = smoke_yaml.read_text(encoding="utf-8")

    missing = []
    for name in sorted(idempotent):
        # `check("<tool>", …)` — tolerate whitespace/newlines between
        # the open paren and the name (multi-line `check()` calls are
        # used when args wrap, see `get_user_followers` since #70).
        if not re.search(rf"""check\(\s*['"]{re.escape(name)}['"]""", src):
            missing.append(name)

    assert not missing, (
        f"live-smoke.yml does NOT exercise these idempotent read tools "
        f"against real X (issue #73): {missing!r}.\n\n"
        f"Either:\n"
        f'  (a) add `await check("<tool>", <tool>(...), v_<tool>, '
        f"tolerate_substr=…)` to the smoke harness, OR\n"
        f"  (b) if it's actually a mutation, add it to the _MUTATING "
        f"allowlist in this test file with a comment explaining why."
    )


def test_no_live_surface_tools_really_do_not_call_x():
    """Enforce the exemption above — an unchecked allowlist is a hole.

    A tool earns a live-smoke exemption only by making no request to X.
    Verified structurally: the local XChat package must not import any
    HTTP client, must not reach for the authenticated twikit client, and
    must not name an x.com endpoint.
    """
    package = Path(__file__).parent.parent / "twitter_mcp" / "xchat"
    sources = sorted(package.glob("*.py"))
    assert sources, "the xchat package should exist while it holds exemptions"

    banned = ("httpx", "requests", "urllib.request", "socket", "_get_client", "x.com")
    for path in sources:
        src = path.read_text(encoding="utf-8")
        # Strip the module docstring: prose may legitimately mention X.
        body = src.split('"""', 2)[-1] if src.lstrip().startswith('"""') else src
        for token in banned:
            assert token not in body, (
                f"{path.name} references {token!r}, so it may reach the network. "
                f"Tools backed by it must not sit in _NO_LIVE_SURFACE."
            )
