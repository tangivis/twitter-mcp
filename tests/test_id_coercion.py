"""Issue #111: integer snowflake IDs must be accepted at the tool boundary.

X serializes tweet/user/list/community IDs as JSON **numbers** (`"id":
2087887408440164663` alongside `"id_str": "..."`). Any client that takes
the `id` field from a previous response and passes it back — the Hermes
Agent client in the report, or plain `{"tweet_id": id}` without `str()` —
used to die at pydantic validation before any server code ran:

    Input should be a valid string [type=string_type,
    input_value=2087887408440164663, input_type=int]

Fix under test: every snowflake-shaped parameter is annotated `IdStr`
(an `Annotated[str, BeforeValidator]` that losslessly coerces int→str
and advertises `anyOf: [integer, string]` in the JSON Schema), and the
URL helpers tolerate int defensively for paths that bypass pydantic.

Floats are deliberately NOT coerced: these IDs exceed 2^53, so a float
is already precision-corrupted — accepting it would silently fetch the
wrong tweet. See the design comment on issue #111.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from twitter_mcp import server

_BIG_ID = 2087887408440164663  # > 2^53 — the ID from the bug report


@pytest.fixture
def fake_client(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))
    return client


# ── helpers tolerate int (paths that bypass pydantic) ─


def test_extract_tweet_id_accepts_int():
    assert server._extract_tweet_id(_BIG_ID) == str(_BIG_ID)


def test_extract_tweet_id_str_forms_unchanged():
    """Regression: string IDs and URLs behave exactly as before."""
    assert server._extract_tweet_id("20") == "20"
    assert server._extract_tweet_id("https://x.com/jack/status/20") == "20"
    assert server._extract_tweet_id("https://x.com/jack/status/20/") == "20"


def test_parse_article_url_or_id_accepts_int():
    """A bare numeric int is not an article URL → None, not TypeError."""
    assert server._parse_article_url_or_id(_BIG_ID) is None


def test_parse_article_url_or_id_str_forms_unchanged():
    assert server._parse_article_url_or_id(None) is None
    assert (
        server._parse_article_url_or_id("https://x.com/i/article/123456789")
        == "123456789"
    )


# ── the reported repro, through real pydantic validation ─
#
# Calling `server.get_tweet(...)` directly would bypass the framework
# boundary where the bug lives. `Tool.run(arguments)` goes through the
# same fn_metadata/pydantic validation the MCP server applies to a
# tools/call request.


def _fake_tweet(tid):
    return SimpleNamespace(
        id=tid,
        text="hi",
        full_text="hi",
        user=SimpleNamespace(screen_name="jack", name="jack"),
        favorite_count=1,
        retweet_count=0,
        created_at="Mon Jan 01 00:00:00 +0000 2026",
        in_reply_to=None,
        conversation_id=None,
        is_quote_status=False,
        quote=None,
    )


async def test_get_tweet_accepts_int_id_through_validation(fake_client):
    fake_client.get_tweets_by_ids = AsyncMock(return_value=[_fake_tweet(str(_BIG_ID))])
    tool = server._registered_tools()["get_tweet"]
    out = json.loads(await tool.run({"tweet_id": _BIG_ID}))
    assert out["id"] == str(_BIG_ID)
    # The coercion must happen BEFORE twikit: the client sees the string.
    fake_client.get_tweets_by_ids.assert_awaited_once_with([str(_BIG_ID)])


async def test_like_tweet_accepts_int_id_through_validation(fake_client):
    fake_client.favorite_tweet = AsyncMock()
    tool = server._registered_tools()["like_tweet"]
    out = json.loads(await tool.run({"tweet_id": _BIG_ID}))
    assert out == {"tweet_id": str(_BIG_ID), "status": "liked"}
    fake_client.favorite_tweet.assert_awaited_once_with(str(_BIG_ID))


async def test_optional_id_param_accepts_int_through_validation(fake_client):
    """`folder_id: IdStr | None` — optional ID params coerce too."""
    fake_client.bookmark_tweet = AsyncMock()
    tool = server._registered_tools()["bookmark_tweet"]
    out = json.loads(await tool.run({"tweet_id": _BIG_ID, "folder_id": 42}))
    assert out["folder_id"] == "42"
    fake_client.bookmark_tweet.assert_awaited_once_with(str(_BIG_ID), "42")


async def test_string_ids_still_accepted_through_validation(fake_client):
    """Regression: the historical str form keeps working identically."""
    fake_client.favorite_tweet = AsyncMock()
    tool = server._registered_tools()["like_tweet"]
    out = json.loads(await tool.run({"tweet_id": "20"}))
    assert out == {"tweet_id": "20", "status": "liked"}


async def test_float_ids_still_rejected(fake_client):
    """Floats are precision-corrupted for >2^53 snowflakes — accepting
    one would silently fetch the WRONG tweet. Must keep failing loudly."""
    tool = server._registered_tools()["like_tweet"]
    with pytest.raises(Exception):
        await tool.run({"tweet_id": float(_BIG_ID)})


# ── breadth sentinel: every snowflake param on every tool ─
#
# Forget-proofing: a future tool that declares `tweet_id: str` instead of
# `tweet_id: IdStr` reintroduces the bug for that tool. The JSON Schema
# of an IdStr param admits "integer"; a plain str param does not.

_ID_PARAM_NAMES = {
    "tweet_id",
    "article_id",
    "user_id",
    "list_id",
    "community_id",
    "message_id",
    "scheduled_tweet_id",
    "media_id",
    "media_ids",
    "folder_id",
    "max_id",
    "group_id",
}


def _id_params_by_tool():
    for tool_name, tool in sorted(server._registered_tools().items()):
        for prop_name, prop in tool.parameters.get("properties", {}).items():
            if prop_name in _ID_PARAM_NAMES:
                yield tool_name, prop_name, prop


def test_id_param_inventory_is_nonempty():
    """Meta-guard: if the walk yields nothing, the sentinel below is
    vacuously green — fail loudly instead."""
    inventory = list(_id_params_by_tool())
    assert len(inventory) >= 30, (
        f"expected 30+ snowflake-ID parameter sites across the registry, "
        f"found {len(inventory)} — did the property walk break?"
    )


@pytest.mark.parametrize(
    ("tool_name", "prop_name", "prop"),
    list(_id_params_by_tool()),
    ids=[f"{t}.{p}" for t, p, _ in _id_params_by_tool()],
)
def test_every_id_param_schema_admits_integer(tool_name, prop_name, prop):
    """X returns these IDs as JSON numbers; the advertised schema must
    accept them. `IdStr` renders as anyOf[integer, string] (issue #111)."""
    dumped = json.dumps(prop)
    assert '"integer"' in dumped, (
        f"{tool_name}.{prop_name} schema is {dumped} — rejects JSON-number "
        f"IDs. Annotate it `IdStr` (or `IdStr | None` / `list[IdStr]`), "
        f"not plain `str`; see issue #111."
    )
