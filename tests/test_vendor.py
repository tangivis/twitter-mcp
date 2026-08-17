"""Tests for vendored twikit — verify import, patches, and packaging."""

import re
import subprocess
import sys
from pathlib import Path

# ── Phase 1: Vendor directory structure ───────────────


def test_vendor_twikit_importable():
    """Vendored twikit package can be imported."""
    from twitter_mcp._vendor import twikit

    assert twikit is not None


def test_vendor_client_importable():
    """Vendored twikit Client class can be imported."""
    from twitter_mcp._vendor.twikit import Client

    assert Client is not None


def test_vendor_transaction_importable():
    """Vendored x_client_transaction module can be imported."""
    from twitter_mcp._vendor.twikit.x_client_transaction import transaction

    assert transaction is not None


def test_vendor_gql_importable():
    """Vendored gql module can be imported."""
    from twitter_mcp._vendor.twikit.client import gql

    assert gql is not None


def test_vendor_license_exists():
    """Vendored twikit includes its MIT LICENSE file."""
    vendor_dir = Path(__file__).parent.parent / "twitter_mcp" / "_vendor" / "twikit"
    license_file = vendor_dir / "LICENSE"
    assert license_file.exists(), "Vendored twikit must include LICENSE"
    content = license_file.read_text()
    assert "MIT" in content


# ── Phase 2: PR#412 patches applied ──────────────────


def test_on_demand_regex_new_format():
    """ON_DEMAND_FILE_REGEX uses the new pattern from PR#412."""
    from twitter_mcp._vendor.twikit.x_client_transaction.transaction import (
        ON_DEMAND_FILE_REGEX,
    )

    # New regex should match: ,123:"ondemand.s"
    test_str = ',456:"ondemand.s"'
    match = ON_DEMAND_FILE_REGEX.search(test_str)
    assert match is not None, "New regex should match the new Twitter format"
    assert match.group(1) == "456"


def test_on_demand_regex_not_old_format():
    """ON_DEMAND_FILE_REGEX no longer uses the old broken pattern."""
    from twitter_mcp._vendor.twikit.x_client_transaction.transaction import (
        ON_DEMAND_FILE_REGEX,
    )

    # Old regex pattern contained this distinctive fragment
    assert "ondemand\\.s" not in ON_DEMAND_FILE_REGEX.pattern or (
        '["' in ON_DEMAND_FILE_REGEX.pattern
    ), "Should use the new regex pattern, not the old one"


def test_on_demand_hash_pattern_exists():
    """ON_DEMAND_HASH_PATTERN variable exists (added by PR#412)."""
    from twitter_mcp._vendor.twikit.x_client_transaction import transaction

    assert hasattr(transaction, "ON_DEMAND_HASH_PATTERN")
    pattern = transaction.ON_DEMAND_HASH_PATTERN
    assert "{}" in pattern, "Pattern should have a format placeholder"


def test_on_demand_hash_pattern_matches():
    """ON_DEMAND_HASH_PATTERN correctly extracts hex hash."""
    from twitter_mcp._vendor.twikit.x_client_transaction.transaction import (
        ON_DEMAND_HASH_PATTERN,
    )

    test_index = "456"
    regex = re.compile(ON_DEMAND_HASH_PATTERN.format(test_index))
    test_str = ',456:"abcdef1234567890"'
    match = regex.search(test_str)
    assert match is not None
    assert match.group(1) == "abcdef1234567890"


def test_search_uses_gql_post():
    """search_timeline method uses gql_post, not gql_get (PR#412 fix)."""
    import inspect

    from twitter_mcp._vendor.twikit.client.gql import GQLClient

    source = inspect.getsource(GQLClient.search_timeline)
    assert "gql_post" in source, "search_timeline should use gql_post"
    assert "gql_get" not in source, "search_timeline should NOT use gql_get"


def test_get_lists_skips_non_list_entries():
    """twitter-mcp patch (issue #37): get_lists must defend against
    items[1] entries that don't carry an `itemContent.list` payload —
    upstream raised KeyError, our patched version skips them.

    Source-level check (cheap regression for the patch marker)."""
    import inspect

    from twitter_mcp._vendor.twikit.client.client import Client

    source = inspect.getsource(Client.get_lists)
    assert "issue #37" in source, "patch marker for issue #37 missing"
    assert ".get(" in source, "patch should use .get() chain for safety"
    # Upstream's brittle bracket-access form must NOT come back on a vendor
    # refresh; if a future twikit sync drops this patch we want CI to fail.
    assert 'list["item"]["itemContent"]["list"]' not in source, (
        "raw bracket access still present; #37 patch was dropped"
    )


def test_get_dm_history_skips_non_message_entries_marker():
    """twitter-mcp patch (issue #104): source must keep the non-message
    skip + timeline_events attachment. Upstream used item["message"] and
    KeyError'd on trust_conversation entries."""
    import inspect

    from twitter_mcp._vendor.twikit.client.client import Client

    source = inspect.getsource(Client.get_dm_history)
    assert "issue #104" in source, "patch marker for issue #104 missing"
    assert "timeline_events" in source
    assert 'item["message"]["message_data"]' not in source, (
        "raw bracket access still present; #104 patch was dropped"
    )


async def test_get_dm_history_runtime_skips_trust_conversation():
    """issue #104 behavioral: mixed timeline with trust_conversation +
    message must yield the message and record the system event — never
    KeyError.
    """
    from unittest.mock import AsyncMock

    from twitter_mcp._vendor.twikit.client.client import Client

    fake_response = {
        "conversation_timeline": {
            "entries": [
                {
                    "trust_conversation": {
                        "id": "ev-trust",
                        "time": "1784798662892",
                        "conversation_id": "me-them",
                        "reason": "follow",
                    }
                },
                {
                    "message": {
                        "message_data": {
                            "id": "m-1",
                            "time": "1784798444000",
                            "text": "yoo man! thanks for liking the post",
                            "sender_id": "them",
                            "recipient_id": "me",
                        }
                    }
                },
            ]
        }
    }

    client = Client("en-US")
    client._get_dm_history = AsyncMock(return_value=fake_response)
    client.user_id = AsyncMock(return_value="me")

    result = await client.get_dm_history("them")

    assert len(result) == 1
    assert result[0].id == "m-1"
    assert result[0].text.startswith("yoo man")
    assert result.timeline_events == [
        {
            "type": "trust_conversation",
            "id": "ev-trust",
            "time": "1784798662892",
            "reason": "follow",
            "conversation_id": "me-them",
        }
    ]
    assert result.next_cursor == "m-1"


async def test_get_dm_history_runtime_trust_only_returns_empty():
    """issue #104: trust_conversation-only timeline must not IndexError
    on messages[-1]; empty Result + timeline_events."""
    from unittest.mock import AsyncMock

    from twitter_mcp._vendor.twikit.client.client import Client

    fake_response = {
        "conversation_timeline": {
            "entries": [
                {
                    "trust_conversation": {
                        "id": "ev-only",
                        "time": "1",
                        "conversation_id": "c",
                        "reason": "follow",
                    }
                }
            ]
        }
    }

    client = Client("en-US")
    client._get_dm_history = AsyncMock(return_value=fake_response)
    client.user_id = AsyncMock(return_value="me")

    result = await client.get_dm_history("them")

    assert list(result) == []
    assert result.next_cursor is None
    assert result.timeline_events[0]["type"] == "trust_conversation"


async def test_get_group_dm_history_runtime_empty_after_skip():
    """issue #104: group path with only non-message entries must return
    empty Result (no messages[-1] IndexError)."""
    from unittest.mock import AsyncMock

    from twitter_mcp._vendor.twikit.client.client import Client

    fake_response = {
        "conversation_timeline": {"entries": [{"trust_conversation": {"id": "g-ev"}}]}
    }

    client = Client("en-US")
    client._get_dm_history = AsyncMock(return_value=fake_response)

    result = await client.get_group_dm_history("group-1")
    assert list(result) == []
    assert result.next_cursor is None


async def test_get_lists_runtime_handles_nonlist_entries():
    """Issue #37 behavioral regression: when X returns a list-management
    timeline whose items[1] holds only non-list entries (the burner-with-0-lists
    case), get_lists must yield an empty Result without raising KeyError.

    Pre-patch this raised `KeyError: 'list'` at the second hop of
    `list["item"]["itemContent"]["list"]`.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from twitter_mcp._vendor.twikit.client.client import Client

    # response shape: top-level "entries" — first entry's "items" is a stub
    # (items[0] in the vendor code), second entry's "items" is the lists slot
    # (items[1]) and contains only entries that lack the `list` key. Last
    # entry carries the cursor (`entries[-1]["content"]["value"]`).
    fake_response = {
        "entries": [
            {"items": ["sentinel-items[0]"]},
            {
                "items": [
                    {"item": {"itemContent": {}}},  # no list key
                    {
                        "item": {"itemContent": {"some_other_key": "promo"}}
                    },  # no list key
                ]
            },
            {"content": {"value": "next-cursor"}},
        ]
    }

    # Skip Client.__init__ — we don't need cookies/HTTP; only the patched
    # `get_lists` body runs.
    client = Client.__new__(Client)
    client.gql = SimpleNamespace(
        list_management_pace_timeline=AsyncMock(return_value=(fake_response, None))
    )

    result = await client.get_lists()
    assert list(result) == []


# ── Phase 3: server.py uses vendored twikit ───────────


def test_server_imports_from_vendor():
    """server.py imports Client from _vendor, not from twikit directly."""
    import inspect

    from twitter_mcp import server

    source = inspect.getsource(server)
    assert "_vendor.twikit" in source or "_vendor" in source, (
        "server.py should import from _vendor"
    )


def test_server_still_works():
    """Server still loads and registers all 62 tools after vendoring."""
    from twitter_mcp.server import _registered_tools

    tools = _registered_tools()
    assert len(tools) == 62
    expected = {
        "send_tweet",
        "get_tweet",
        "get_timeline",
        "search_tweets",
        "like_tweet",
        "retweet",
        "get_user_tweets",
        "get_user_info",
        "get_user_followers",
        "get_user_following",
        "get_article_preview",
        "get_article",
        "follow_user",
        "unfollow_user",
        "delete_tweet",
        "unfavorite_tweet",
        "delete_retweet",
        "bookmark_tweet",
        "delete_bookmark",
        "get_bookmarks",
        "get_favoriters",
        "get_retweeters",
        "search_user",
        "get_trends",
        # new in v0.1.17
        "block_user",
        "unblock_user",
        "mute_user",
        "unmute_user",
        "get_notifications",
        "send_dm",
        "send_dm_to_group",
        "get_dm_history",
        "delete_dm",
        # new in v0.1.18
        "get_list",
        "get_lists",
        "get_list_tweets",
        "get_list_members",
        "get_list_subscribers",
        "create_list",
        "edit_list",
        "add_list_member",
        "remove_list_member",
        # new in v0.1.19
        "create_scheduled_tweet",
        "get_scheduled_tweets",
        "delete_scheduled_tweet",
        "create_poll",
        "vote",
        # new in v0.1.20
        "get_community",
        "search_community",
        "get_community_tweets",
        "get_communities_timeline",
        "get_community_members",
        "get_community_moderators",
        "search_community_tweet",
        "join_community",
        "leave_community",
        "request_to_join_community",
        # new in v0.1.27 (issue #84)
        "download_tweet_video",
        # new in v0.1.32 (issue #94)
        "get_tweet_replies",
        # new in v0.1.41 (issue #118) — local read-only XChat
        "xchat_status",
        "xchat_list_conversations",
        "xchat_get_history",
    }
    assert set(tools.keys()) == expected


def test_mcp_handshake_with_vendor():
    """MCP protocol handshake still works with vendored twikit."""
    import json

    init_request = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1"},
            },
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "twitter_mcp.server"],
        input=init_request,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.stdout, "Server produced no output"
    response = json.loads(result.stdout.strip().split("\n")[0])
    assert response["result"]["serverInfo"]["name"] == "twitter"


# ── Phase 4: Packaging ───────────────────────────────


def test_no_git_dependencies():
    """pyproject.toml has no git+ URL dependencies."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject.read_text()
    assert "git+" not in content, "pyproject.toml should not contain git+ URLs"


def test_twikit_not_in_dependencies():
    """twikit is not listed as an external dependency."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject.read_text()
    # Should not have a line like: "twikit..." in dependencies
    # But might mention twikit in comments or description — that's fine
    lines = content.split("\n")
    in_deps = False
    for line in lines:
        if line.strip() == "dependencies = [":
            in_deps = True
            continue
        if in_deps and line.strip() == "]":
            break
        if in_deps and "twikit" in line.lower():
            assert False, f"twikit should not be in dependencies: {line}"


def test_package_builds():
    """Package can be built without errors."""
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        ["uv", "build"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"Build failed: {output}"
    assert "Successfully built" in output


# ── issue #37 drift: engagement lists carry non-User results ─


def _engagement_response(entries):
    """Wrap timeline entries in the shape `find_dict(response, 'entries')` sees."""
    return {
        "data": {
            "retweeters_timeline": {
                "timeline": {
                    "instructions": [{"type": "TimelineAddEntries", "entries": entries}]
                }
            }
        }
    }


def _user_entry(entry_id, rest_id, screen_name):
    return {
        "entryId": entry_id,
        "content": {
            "itemContent": {
                "user_results": {
                    "result": {
                        "__typename": "User",
                        "rest_id": rest_id,
                        "legacy": {"screen_name": screen_name, "name": screen_name},
                    }
                }
            }
        },
    }


def _unavailable_entry(entry_id, reason="Suspended"):
    """X's shape for a retweeter whose account is gone.

    `UserUnavailable` carries no `rest_id`, and `User.__init__` reads that
    key unconditionally (user.py:94) — this is the live-smoke failure
    `get_retweeters: KeyError: 'rest_id'` on 2026-08-17.
    """
    return {
        "entryId": entry_id,
        "content": {
            "itemContent": {
                "user_results": {
                    "result": {"__typename": "UserUnavailable", "reason": reason}
                }
            }
        },
    }


def _cursors():
    return [
        {"entryId": "cursor-top-1", "content": {"value": "CURSOR_PREV"}},
        {"entryId": "cursor-bottom-1", "content": {"value": "CURSOR_NEXT"}},
    ]


async def test_get_retweeters_skips_unavailable_accounts():
    """issue #37 behavioral: a suspended/deleted retweeter must be skipped,
    not crash the whole call with KeyError: 'rest_id'."""
    from unittest.mock import AsyncMock

    from twitter_mcp._vendor.twikit.client.client import Client

    client = Client("en-US")
    client.gql.retweeters = AsyncMock(
        return_value=(
            _engagement_response(
                [
                    _user_entry("user-1", "111", "alice"),
                    _unavailable_entry("user-2"),
                    _user_entry("user-3", "333", "bob"),
                    *_cursors(),
                ]
            ),
            None,
        )
    )

    result = await client.get_retweeters("20")

    assert [u.id for u in result] == ["111", "333"]
    assert [u.screen_name for u in result] == ["alice", "bob"]
    assert result.next_cursor == "CURSOR_NEXT"
    assert result.previous_cursor == "CURSOR_PREV"


async def test_get_favoriters_shares_the_same_protection():
    """Both engagement lists go through `_get_tweet_engagements`, so the
    fix must cover favoriters too — X gates them identically."""
    from unittest.mock import AsyncMock

    from twitter_mcp._vendor.twikit.client.client import Client

    client = Client("en-US")
    client.gql.favoriters = AsyncMock(
        return_value=(
            _engagement_response([_unavailable_entry("user-1"), *_cursors()]),
            None,
        )
    )

    result = await client.get_favoriters("20")
    assert list(result) == []


async def test_engagements_survive_a_timeline_without_cursor_entries():
    """Adjacent fragility in the same function: `items[-1]['content']['value']`
    assumes the last two entries are cursors. A gated response that returns
    only user entries used to KeyError one line away from the rest_id crash."""
    from unittest.mock import AsyncMock

    from twitter_mcp._vendor.twikit.client.client import Client

    client = Client("en-US")
    client.gql.retweeters = AsyncMock(
        return_value=(
            _engagement_response([_user_entry("user-1", "111", "alice")]),
            None,
        )
    )

    result = await client.get_retweeters("20")
    assert [u.id for u in result] == ["111"]
    assert result.next_cursor is None


async def test_engagements_empty_timeline_is_empty_result():
    from unittest.mock import AsyncMock

    from twitter_mcp._vendor.twikit.client.client import Client

    client = Client("en-US")
    client.gql.retweeters = AsyncMock(return_value=(_engagement_response([]), None))
    assert list(await client.get_retweeters("20")) == []


def test_get_tweet_engagements_patch_marker():
    """Source marker so a future vendor refresh can't silently drop this."""
    import inspect

    from twitter_mcp._vendor.twikit.client.client import Client

    source = inspect.getsource(Client._get_tweet_engagements)
    assert "issue #37" in source, "patch marker for issue #37 missing"
    assert "rest_id" in source, "the rest_id guard was dropped"
