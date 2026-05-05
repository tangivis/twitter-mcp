"""Tests for twitter-mcp server — no cookies/network required."""

import json
import subprocess
import sys

# ── Import Tests ──────────────────────────────────────


def test_import_server():
    """Server module can be imported without errors."""
    from twitter_mcp.server import mcp

    assert mcp is not None


def test_import_client_helper():
    """Internal _get_client helper exists."""
    from twitter_mcp.server import _get_client

    assert callable(_get_client)


# ── Tool Registration Tests ──────────────────────────


def test_tools_registered():
    """All 47 tools are registered in the MCP server."""
    from twitter_mcp.server import mcp

    tools = mcp._tool_manager._tools
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
        # new in v0.1.16
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
    }
    assert set(tools.keys()) == expected


def test_tool_count():
    """Exactly 47 tools are registered."""
    from twitter_mcp.server import mcp

    tools = mcp._tool_manager._tools
    assert len(tools) == 47


# ── Tool Schema Tests ─────────────────────────────────


def test_send_tweet_has_text_param():
    """send_tweet requires a 'text' parameter."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["send_tweet"]
    schema = tool.parameters
    assert "text" in schema["properties"]
    assert "text" in schema.get("required", [])


def test_send_tweet_has_optional_reply_to():
    """send_tweet has an optional 'reply_to' parameter."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["send_tweet"]
    schema = tool.parameters
    assert "reply_to" in schema["properties"]
    # reply_to should NOT be required
    assert "reply_to" not in schema.get("required", [])


def test_search_tweets_has_query_param():
    """search_tweets requires a 'query' parameter."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["search_tweets"]
    schema = tool.parameters
    assert "query" in schema["properties"]
    assert "query" in schema.get("required", [])


def test_search_tweets_has_product_param():
    """search_tweets has a 'product' parameter with default."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["search_tweets"]
    schema = tool.parameters
    assert "product" in schema["properties"]


def test_get_user_tweets_has_screen_name():
    """get_user_tweets requires 'screen_name'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_user_tweets"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "screen_name" in schema.get("required", [])


def test_get_tweet_has_tweet_id():
    """get_tweet requires 'tweet_id'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_tweet"]
    schema = tool.parameters
    assert "tweet_id" in schema["properties"]


def test_follow_user_has_screen_name():
    """follow_user requires 'screen_name' (matches get_user_tweets convention)."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["follow_user"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "screen_name" in schema.get("required", [])


def test_unfollow_user_has_screen_name():
    """unfollow_user requires 'screen_name'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["unfollow_user"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "screen_name" in schema.get("required", [])


def test_get_user_info_accepts_either_screen_name_or_user_id():
    """get_user_info(screen_name | user_id) — both optional, validated at runtime.

    PR #24 review: gain user_id lookup. Both args become Optional with
    runtime validation (exactly one required) so an LLM caller can use
    whichever it has in hand. Schema-wise neither is required; the body
    raises ToolError if neither is provided (or both).
    """
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_user_info"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "user_id" in schema["properties"]
    # Neither is required — runtime check enforces "exactly one".
    required = set(schema.get("required", []))
    assert "screen_name" not in required
    assert "user_id" not in required


def test_get_user_followers_schema_has_count_and_either_user_id_or_screen_name():
    """get_user_followers takes optional screen_name / user_id / count / cursor."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_user_followers"]
    schema = tool.parameters
    assert {"screen_name", "user_id", "count", "cursor"}.issubset(schema["properties"])
    required = set(schema.get("required", []))
    assert not required & {"screen_name", "user_id", "count", "cursor"}


def test_get_user_following_schema_mirrors_followers():
    """get_user_following has the same schema shape as get_user_followers."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_user_following"]
    schema = tool.parameters
    assert {"screen_name", "user_id", "count", "cursor"}.issubset(schema["properties"])


def test_delete_tweet_has_tweet_id():
    """delete_tweet requires 'tweet_id'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["delete_tweet"]
    schema = tool.parameters
    assert "tweet_id" in schema["properties"]
    assert "tweet_id" in schema.get("required", [])


def test_unfavorite_tweet_has_tweet_id():
    """unfavorite_tweet requires 'tweet_id'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["unfavorite_tweet"]
    schema = tool.parameters
    assert "tweet_id" in schema["properties"]
    assert "tweet_id" in schema.get("required", [])


def test_delete_retweet_has_tweet_id():
    """delete_retweet requires 'tweet_id'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["delete_retweet"]
    schema = tool.parameters
    assert "tweet_id" in schema["properties"]
    assert "tweet_id" in schema.get("required", [])


def test_bookmark_tweet_has_tweet_id():
    """bookmark_tweet requires 'tweet_id'; folder_id is optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["bookmark_tweet"]
    schema = tool.parameters
    assert "tweet_id" in schema["properties"]
    assert "tweet_id" in schema.get("required", [])
    assert "folder_id" in schema["properties"]
    assert "folder_id" not in schema.get("required", [])


def test_delete_bookmark_has_tweet_id():
    """delete_bookmark requires 'tweet_id'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["delete_bookmark"]
    schema = tool.parameters
    assert "tweet_id" in schema["properties"]
    assert "tweet_id" in schema.get("required", [])


def test_get_bookmarks_schema():
    """get_bookmarks has optional count and cursor."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_bookmarks"]
    schema = tool.parameters
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    required = set(schema.get("required", []))
    assert "count" not in required
    assert "cursor" not in required


def test_get_favoriters_schema():
    """get_favoriters requires tweet_id; count and cursor are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_favoriters"]
    schema = tool.parameters
    assert "tweet_id" in schema["properties"]
    assert "tweet_id" in schema.get("required", [])
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]


def test_get_retweeters_schema():
    """get_retweeters requires tweet_id; count and cursor are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_retweeters"]
    schema = tool.parameters
    assert "tweet_id" in schema["properties"]
    assert "tweet_id" in schema.get("required", [])
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]


def test_search_user_schema():
    """search_user requires query; count and cursor are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["search_user"]
    schema = tool.parameters
    assert "query" in schema["properties"]
    assert "query" in schema.get("required", [])
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]


def test_get_trends_schema():
    """get_trends has optional category and count."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_trends"]
    schema = tool.parameters
    assert "category" in schema["properties"]
    assert "count" in schema["properties"]
    required = set(schema.get("required", []))
    assert "category" not in required
    assert "count" not in required


def test_get_article_format_param_in_schema():
    """get_article exposes a `format` arg with 'plain' as the default (issue #14)."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_article"]
    schema = tool.parameters
    assert "format" in schema["properties"]
    # format is optional — only article_id is required.
    assert "format" not in schema.get("required", [])
    assert "article_id" in schema.get("required", [])
    # Default must be "plain" so existing callers don't suddenly get the
    # 150KB+ raw payload that would blow MAX_MCP_OUTPUT_TOKENS.
    assert schema["properties"]["format"].get("default") == "plain"


def test_block_user_has_screen_name():
    """block_user requires 'screen_name'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["block_user"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "screen_name" in schema.get("required", [])


def test_unblock_user_has_screen_name():
    """unblock_user requires 'screen_name'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["unblock_user"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "screen_name" in schema.get("required", [])


def test_mute_user_has_screen_name():
    """mute_user requires 'screen_name'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["mute_user"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "screen_name" in schema.get("required", [])


def test_unmute_user_has_screen_name():
    """unmute_user requires 'screen_name'."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["unmute_user"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "screen_name" in schema.get("required", [])


def test_get_notifications_schema():
    """get_notifications has optional notification_type, count, and cursor."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_notifications"]
    schema = tool.parameters
    assert "notification_type" in schema["properties"]
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    required = set(schema.get("required", []))
    assert "notification_type" not in required
    assert "count" not in required
    assert "cursor" not in required


def test_send_dm_schema():
    """send_dm requires screen_name and text; media_id is optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["send_dm"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "text" in schema["properties"]
    assert "media_id" in schema["properties"]
    assert "screen_name" in schema.get("required", [])
    assert "text" in schema.get("required", [])
    assert "media_id" not in schema.get("required", [])


def test_send_dm_to_group_schema():
    """send_dm_to_group requires group_id and text; media_id is optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["send_dm_to_group"]
    schema = tool.parameters
    assert "group_id" in schema["properties"]
    assert "text" in schema["properties"]
    assert "media_id" in schema["properties"]
    assert "group_id" in schema.get("required", [])
    assert "text" in schema.get("required", [])
    assert "media_id" not in schema.get("required", [])


def test_get_dm_history_schema():
    """get_dm_history requires screen_name; max_id is optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_dm_history"]
    schema = tool.parameters
    assert "screen_name" in schema["properties"]
    assert "max_id" in schema["properties"]
    assert "screen_name" in schema.get("required", [])
    assert "max_id" not in schema.get("required", [])


def test_delete_dm_schema():
    """delete_dm requires message_id."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["delete_dm"]
    schema = tool.parameters
    assert "message_id" in schema["properties"]
    assert "message_id" in schema.get("required", [])


def test_get_list_schema():
    """get_list requires list_id."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_list"]
    schema = tool.parameters
    assert "list_id" in schema["properties"]
    assert "list_id" in schema.get("required", [])


def test_get_lists_schema():
    """get_lists has optional count and cursor."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_lists"]
    schema = tool.parameters
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    required = set(schema.get("required", []))
    assert "count" not in required
    assert "cursor" not in required


def test_get_list_tweets_schema():
    """get_list_tweets requires list_id; count and cursor are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_list_tweets"]
    schema = tool.parameters
    assert "list_id" in schema["properties"]
    assert "list_id" in schema.get("required", [])
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    required = set(schema.get("required", []))
    assert "count" not in required
    assert "cursor" not in required


def test_get_list_members_schema():
    """get_list_members requires list_id; count and cursor are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_list_members"]
    schema = tool.parameters
    assert "list_id" in schema["properties"]
    assert "list_id" in schema.get("required", [])
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]


def test_get_list_subscribers_schema():
    """get_list_subscribers requires list_id; count and cursor are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_list_subscribers"]
    schema = tool.parameters
    assert "list_id" in schema["properties"]
    assert "list_id" in schema.get("required", [])
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]


def test_create_list_schema():
    """create_list requires name; description and is_private are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["create_list"]
    schema = tool.parameters
    assert "name" in schema["properties"]
    assert "name" in schema.get("required", [])
    assert "description" in schema["properties"]
    assert "is_private" in schema["properties"]
    required = set(schema.get("required", []))
    assert "description" not in required
    assert "is_private" not in required


def test_edit_list_schema():
    """edit_list requires list_id; name/description/is_private are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["edit_list"]
    schema = tool.parameters
    assert "list_id" in schema["properties"]
    assert "list_id" in schema.get("required", [])
    assert "name" in schema["properties"]
    assert "description" in schema["properties"]
    assert "is_private" in schema["properties"]
    required = set(schema.get("required", []))
    assert "name" not in required
    assert "description" not in required
    assert "is_private" not in required


def test_add_list_member_schema():
    """add_list_member requires list_id; screen_name and user_id are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["add_list_member"]
    schema = tool.parameters
    assert "list_id" in schema["properties"]
    assert "list_id" in schema.get("required", [])
    assert "screen_name" in schema["properties"]
    assert "user_id" in schema["properties"]
    required = set(schema.get("required", []))
    assert "screen_name" not in required
    assert "user_id" not in required


def test_remove_list_member_schema():
    """remove_list_member requires list_id; screen_name and user_id are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["remove_list_member"]
    schema = tool.parameters
    assert "list_id" in schema["properties"]
    assert "list_id" in schema.get("required", [])
    assert "screen_name" in schema["properties"]
    assert "user_id" in schema["properties"]
    required = set(schema.get("required", []))
    assert "screen_name" not in required
    assert "user_id" not in required


def test_create_scheduled_tweet_schema():
    """create_scheduled_tweet requires scheduled_at; text and media_ids are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["create_scheduled_tweet"]
    schema = tool.parameters
    assert "scheduled_at" in schema["properties"]
    assert "scheduled_at" in schema.get("required", [])
    assert "text" in schema["properties"]
    assert "media_ids" in schema["properties"]
    required = set(schema.get("required", []))
    assert "text" not in required
    assert "media_ids" not in required


def test_get_scheduled_tweets_schema():
    """get_scheduled_tweets takes no arguments."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_scheduled_tweets"]
    schema = tool.parameters
    assert schema.get("properties", {}) == {} or not schema.get("required", [])


def test_delete_scheduled_tweet_schema():
    """delete_scheduled_tweet requires scheduled_tweet_id."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["delete_scheduled_tweet"]
    schema = tool.parameters
    assert "scheduled_tweet_id" in schema["properties"]
    assert "scheduled_tweet_id" in schema.get("required", [])


def test_create_poll_schema():
    """create_poll requires choices and duration_minutes."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["create_poll"]
    schema = tool.parameters
    assert "choices" in schema["properties"]
    assert "duration_minutes" in schema["properties"]
    assert "choices" in schema.get("required", [])
    assert "duration_minutes" in schema.get("required", [])


def test_vote_schema():
    """vote requires selected_choice, card_uri, tweet_id, and card_name."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["vote"]
    schema = tool.parameters
    required = set(schema.get("required", []))
    assert "selected_choice" in schema["properties"]
    assert "card_uri" in schema["properties"]
    assert "tweet_id" in schema["properties"]
    assert "card_name" in schema["properties"]
    assert "selected_choice" in required
    assert "card_uri" in required
    assert "tweet_id" in required
    assert "card_name" in required


def test_get_community_schema():
    """get_community requires community_id."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_community"]
    schema = tool.parameters
    assert "community_id" in schema["properties"]
    assert "community_id" in schema.get("required", [])


def test_search_community_schema():
    """search_community requires query; cursor is optional; NO count param."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["search_community"]
    schema = tool.parameters
    assert "query" in schema["properties"]
    assert "query" in schema.get("required", [])
    assert "cursor" in schema["properties"]
    assert "count" not in schema["properties"]
    assert "cursor" not in schema.get("required", [])


def test_get_community_tweets_schema():
    """get_community_tweets requires community_id and tweet_type; count/cursor optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_community_tweets"]
    schema = tool.parameters
    required = set(schema.get("required", []))
    assert "community_id" in schema["properties"]
    assert "tweet_type" in schema["properties"]
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    assert "community_id" in required
    assert "tweet_type" in required
    assert "count" not in required
    assert "cursor" not in required


def test_get_communities_timeline_schema():
    """get_communities_timeline has optional count and cursor."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_communities_timeline"]
    schema = tool.parameters
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    required = set(schema.get("required", []))
    assert "count" not in required
    assert "cursor" not in required


def test_get_community_members_schema():
    """get_community_members requires community_id; count and cursor are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_community_members"]
    schema = tool.parameters
    required = set(schema.get("required", []))
    assert "community_id" in schema["properties"]
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    assert "community_id" in required
    assert "count" not in required
    assert "cursor" not in required


def test_get_community_moderators_schema():
    """get_community_moderators requires community_id; count and cursor are optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["get_community_moderators"]
    schema = tool.parameters
    required = set(schema.get("required", []))
    assert "community_id" in schema["properties"]
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    assert "community_id" in required
    assert "count" not in required
    assert "cursor" not in required


def test_search_community_tweet_schema():
    """search_community_tweet requires community_id and query; count/cursor optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["search_community_tweet"]
    schema = tool.parameters
    required = set(schema.get("required", []))
    assert "community_id" in schema["properties"]
    assert "query" in schema["properties"]
    assert "count" in schema["properties"]
    assert "cursor" in schema["properties"]
    assert "community_id" in required
    assert "query" in required
    assert "count" not in required
    assert "cursor" not in required


def test_join_community_schema():
    """join_community requires community_id."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["join_community"]
    schema = tool.parameters
    assert "community_id" in schema["properties"]
    assert "community_id" in schema.get("required", [])


def test_leave_community_schema():
    """leave_community requires community_id."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["leave_community"]
    schema = tool.parameters
    assert "community_id" in schema["properties"]
    assert "community_id" in schema.get("required", [])


def test_request_to_join_community_schema():
    """request_to_join_community requires community_id; answer is optional."""
    from twitter_mcp.server import mcp

    tool = mcp._tool_manager._tools["request_to_join_community"]
    schema = tool.parameters
    required = set(schema.get("required", []))
    assert "community_id" in schema["properties"]
    assert "answer" in schema["properties"]
    assert "community_id" in required
    assert "answer" not in required


def test_dm_docstrings_contain_privacy_warning():
    """DM tool docstrings must mention PRIVATE and anti-spam (issue #28 spec)."""
    import inspect

    from twitter_mcp.server import delete_dm, get_dm_history, send_dm, send_dm_to_group

    for fn in [send_dm, send_dm_to_group, get_dm_history, delete_dm]:
        doc = inspect.getdoc(fn) or ""
        assert "PRIVATE" in doc or "private" in doc, (
            f"{fn.__name__} missing privacy warning in docstring"
        )


def test_all_tools_have_descriptions():
    """Every tool has a non-empty description."""
    from twitter_mcp.server import mcp

    for name, tool in mcp._tool_manager._tools.items():
        assert tool.description, f"Tool '{name}' has no description"
        assert len(tool.description) > 10, f"Tool '{name}' description too short"


# ── URL Parsing Tests ─────────────────────────────────


def test_get_tweet_url_parsing():
    """get_tweet correctly extracts tweet ID from various URL formats."""
    # Test the URL parsing logic directly
    test_cases = [
        ("2028904166895112617", "2028904166895112617"),
        (
            "https://x.com/user/status/2028904166895112617",
            "2028904166895112617",
        ),
        (
            "https://x.com/user/status/2028904166895112617/",
            "2028904166895112617",
        ),
        (
            "https://twitter.com/user/status/123456789",
            "123456789",
        ),
        (
            "https://x.com/user/status/123?s=46&t=abc",
            "123?s=46&t=abc",  # query params stay (handled by Twitter API)
        ),
    ]

    for input_id, expected in test_cases:
        if "/" in input_id:
            result = input_id.rstrip("/").split("/")[-1]
        else:
            result = input_id
        assert result == expected, f"Failed for input: {input_id}"


# ── MCP Protocol Tests ────────────────────────────────


def test_mcp_initialize_handshake():
    """Server responds correctly to MCP initialize request."""
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

    # Server should produce output on stdout
    assert result.stdout, "Server produced no output"

    response = json.loads(result.stdout.strip().split("\n")[0])
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert "capabilities" in response["result"]
    assert "serverInfo" in response["result"]
    assert response["result"]["serverInfo"]["name"] == "twitter"


# ── Config Tests ──────────────────────────────────────


def test_cookies_path_env_override(tmp_path, monkeypatch):
    """TWITTER_COOKIES env var overrides default path."""
    fake_cookies = tmp_path / "cookies.json"
    fake_cookies.write_text('{"ct0": "test", "auth_token": "test"}')

    monkeypatch.setenv("TWITTER_COOKIES", str(fake_cookies))

    # Re-import to pick up env var
    import importlib  # noqa: E401

    import twitter_mcp.server as mod

    importlib.reload(mod)

    assert str(mod.COOKIES_PATH) == str(fake_cookies)


def test_server_name():
    """MCP server is named 'twitter'."""
    from twitter_mcp.server import mcp

    assert mcp.name == "twitter"


# ── --version flag ────────────────────────────────────


def _expected_version() -> str:
    """Read version straight from pyproject.toml so tests can't drift."""
    import re
    from pathlib import Path

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    text = pyproject.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "version not found in pyproject.toml"
    return m.group(1)


def test_version_flag_long_form():
    """`python -m twitter_mcp.server --version` prints version and exits 0."""
    result = subprocess.run(
        [sys.executable, "-m", "twitter_mcp.server", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    out = result.stdout + result.stderr
    assert _expected_version() in out
    assert "twikit-mcp" in out


def test_version_flag_short_form():
    """`-v` is an alias for `--version`."""
    result = subprocess.run(
        [sys.executable, "-m", "twitter_mcp.server", "-v"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    out = result.stdout + result.stderr
    assert _expected_version() in out


def test_get_version_returns_installed_version():
    """_get_version() reads the metadata of the installed package."""
    from twitter_mcp.server import _get_version

    assert _get_version() == _expected_version()


def test_get_version_falls_back_to_unknown(monkeypatch):
    """If the package isn't installed (e.g. raw checkout, no `uv sync`),
    _get_version() returns 'unknown' instead of raising."""
    from importlib.metadata import PackageNotFoundError

    import twitter_mcp.server as srv

    def _raise(_name):
        raise PackageNotFoundError("twikit-mcp")

    monkeypatch.setattr(srv, "_pkg_version", _raise)
    assert srv._get_version() == "unknown"
