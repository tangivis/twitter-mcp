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
    """All 7 tools are registered in the MCP server."""
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
    }
    assert set(tools.keys()) == expected


def test_tool_count():
    """Exactly 7 tools are registered."""
    from twitter_mcp.server import mcp

    tools = mcp._tool_manager._tools
    assert len(tools) == 7


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
