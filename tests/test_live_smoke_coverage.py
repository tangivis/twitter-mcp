"""Issue #73 sentinel: live-smoke must exercise every idempotent read tool.

Scans `mcp._tool_manager._tools` at import time to discover the full
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
}


def test_live_smoke_covers_all_idempotent_reads():
    """Issue #73 acceptance criterion 1: all 25 idempotent reads are
    invoked from `live-smoke.yml` against real X."""
    from twitter_mcp import server

    all_tools = set(server.mcp._tool_manager._tools.keys())

    # Sanity: every name in _MUTATING actually exists. Catches typos.
    unknown_mutating = _MUTATING - all_tools
    assert not unknown_mutating, (
        f"_MUTATING references unregistered tools: {unknown_mutating!r}. "
        f"Update this test's allowlist to match server.py's registry."
    )

    idempotent = all_tools - _MUTATING

    smoke_yaml = Path(__file__).parent.parent / ".github/workflows/live-smoke.yml"
    src = smoke_yaml.read_text()

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
