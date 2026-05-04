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
    """Server still loads and registers all 42 tools after vendoring."""
    from twitter_mcp.server import mcp

    tools = mcp._tool_manager._tools
    assert len(tools) == 42
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
