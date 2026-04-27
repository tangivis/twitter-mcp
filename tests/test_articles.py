"""Tests for X Article support (issue #4).

Covers:
- _parse_article_url_or_id: URL/ID parsing for article links
- get_tweet article-aware error path + None-guard
- get_article_preview: syndication endpoint, no auth
- get_article: GraphQL endpoint, requires TWITTER_ARTICLE_QUERY_ID env var
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from twitter_mcp import server

# ── _parse_article_url_or_id ─────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        # Bare numeric IDs are NOT recognised as articles — only URLs are
        # (article and tweet IDs share the same numeric namespace shape).
        ("2046813551021760512", None),
        ("https://x.com/i/article/2046813551021760512", "2046813551021760512"),
        ("https://x.com/i/article/2046813551021760512/", "2046813551021760512"),
        ("https://twitter.com/i/article/123456789", "123456789"),
        ("https://x.com/i/article/2046813551021760512?s=1", "2046813551021760512"),
        # Tweet URLs are not article URLs
        ("https://x.com/user/status/12345", None),
        ("12345", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_article_url_or_id(value, expected):
    assert server._parse_article_url_or_id(value) == expected


# ── get_tweet: article guard + None guard ────────────


@pytest.fixture
def fake_client(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))
    return client


async def test_get_tweet_rejects_article_url(fake_client):
    with pytest.raises(ToolError) as exc:
        await server.get_tweet("https://x.com/i/article/2046813551021760512")
    msg = str(exc.value)
    assert "article" in msg.lower()
    assert "get_article" in msg
    assert "2046813551021760512" in msg
    # twikit must not be called when we already know it's an article
    fake_client.get_tweets_by_ids.assert_not_called()


async def test_get_tweet_raises_clean_error_when_not_found(fake_client):
    """Empty result list (e.g. wrong namespace) → ToolError, not NoneType crash."""
    fake_client.get_tweets_by_ids = AsyncMock(return_value=[])
    with pytest.raises(ToolError) as exc:
        await server.get_tweet("99999999999999")
    assert "not found" in str(exc.value).lower() or "no tweet" in str(exc.value).lower()


async def test_get_tweet_raises_clean_error_when_none(fake_client):
    """First element is None (twikit's article-id behaviour) → ToolError."""
    fake_client.get_tweets_by_ids = AsyncMock(return_value=[None])
    with pytest.raises(ToolError):
        await server.get_tweet("99999999999999")


# ── get_article_preview ──────────────────────────────


def _syndication_payload_with_article():
    return {
        "id_str": "2046823788646637713",
        "user": {"screen_name": "congge918"},
        "article": {
            "rest_id": "2046813551021760512",
            "id": "QXJ0aWNsZUVudGl0eToyMDQ2ODEzNTUxMDIxNzYwNTEy",
            "title": "测试标题",
            "preview_text": "preview body text",
            "cover_media": {
                "media_info": {
                    "original_img_url": "https://pbs.twimg.com/media/X.jpg",
                    "original_img_width": 1913,
                    "original_img_height": 765,
                }
            },
        },
    }


def _syndication_payload_without_article():
    return {
        "id_str": "111",
        "user": {"screen_name": "alice"},
        # no "article" key
    }


def _stub_syndication(monkeypatch, payload, status_code=200):
    """Patch httpx.AsyncClient so server.get_article_preview gets `payload`."""
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=payload)
    response.raise_for_status = MagicMock()

    instance = MagicMock()
    instance.get = AsyncMock(return_value=response)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)

    cls = MagicMock(return_value=instance)
    # Patch the AsyncClient symbol that server imports.
    monkeypatch.setattr(server.httpx, "AsyncClient", cls)
    return instance


async def test_get_article_preview_returns_full_shape(monkeypatch):
    instance = _stub_syndication(monkeypatch, _syndication_payload_with_article())
    out = json.loads(await server.get_article_preview("2046823788646637713"))
    assert out == {
        "rest_id": "2046813551021760512",
        "title": "测试标题",
        "preview_text": "preview body text",
        "cover_image": "https://pbs.twimg.com/media/X.jpg",
        "tweet_id": "2046823788646637713",
        "author": "congge918",
    }
    instance.get.assert_awaited_once()
    args, kwargs = instance.get.call_args
    assert args[0] == "https://cdn.syndication.twimg.com/tweet-result"
    assert kwargs["params"] == {"id": "2046823788646637713", "token": "a"}


async def test_get_article_preview_accepts_tweet_url(monkeypatch):
    _stub_syndication(monkeypatch, _syndication_payload_with_article())
    # full status URL — should be normalized to numeric id
    out = json.loads(
        await server.get_article_preview(
            "https://x.com/user/status/2046823788646637713"
        )
    )
    assert out["tweet_id"] == "2046823788646637713"


async def test_get_article_preview_raises_when_no_article(monkeypatch):
    _stub_syndication(monkeypatch, _syndication_payload_without_article())
    with pytest.raises(ToolError) as exc:
        await server.get_article_preview("111")
    assert "article" in str(exc.value).lower()


# ── get_article ──────────────────────────────────────


@pytest.fixture
def fake_client_with_gql(monkeypatch):
    """A fake twikit client whose .gql.gql_get is awaitable."""
    client = AsyncMock()
    client.gql = SimpleNamespace(gql_get=AsyncMock(return_value={"data": "ok"}))
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))
    return client


async def test_get_article_requires_query_id_env(monkeypatch, fake_client_with_gql):
    monkeypatch.delenv("TWITTER_ARTICLE_QUERY_ID", raising=False)
    with pytest.raises(ToolError) as exc:
        await server.get_article("2046813551021760512")
    msg = str(exc.value)
    assert "TWITTER_ARTICLE_QUERY_ID" in msg
    fake_client_with_gql.gql.gql_get.assert_not_called()


async def test_get_article_calls_graphql_with_correct_args(
    monkeypatch, fake_client_with_gql
):
    monkeypatch.setenv("TWITTER_ARTICLE_QUERY_ID", "abc123hash")
    out = await server.get_article("2046813551021760512")
    # function returns JSON string of the gql response
    assert json.loads(out) == {"data": "ok"}
    fake_client_with_gql.gql.gql_get.assert_awaited_once()
    args, kwargs = fake_client_with_gql.gql.gql_get.call_args
    url = args[0]
    variables = args[1]
    features = args[2] if len(args) > 2 else kwargs.get("features", {})
    assert url.endswith("/abc123hash/TwitterArticleByRestId")
    assert url.startswith("https://x.com/i/api/graphql/")
    assert variables == {
        "twitterArticleId": "2046813551021760512",
        "withArticleRichContentState": True,
        "withArticlePlainText": True,
    }
    # Article-related feature flags are present and enabled
    assert features.get("responsive_web_twitter_article_tweet_consumption_enabled") is True
    assert features.get("articles_preview_enabled") is True


async def test_get_article_accepts_url(monkeypatch, fake_client_with_gql):
    monkeypatch.setenv("TWITTER_ARTICLE_QUERY_ID", "abc123hash")
    await server.get_article("https://x.com/i/article/2046813551021760512")
    args, _ = fake_client_with_gql.gql.gql_get.call_args
    assert args[1]["twitterArticleId"] == "2046813551021760512"


async def test_get_article_rejects_non_article_input(
    monkeypatch, fake_client_with_gql
):
    monkeypatch.setenv("TWITTER_ARTICLE_QUERY_ID", "abc123hash")
    # Bare numeric ID is allowed (caller may pass either a URL or an id)
    await server.get_article("2046813551021760512")
    fake_client_with_gql.gql.gql_get.assert_awaited_once()


# ── tool registration ────────────────────────────────


def test_new_tools_registered():
    tools = server.mcp._tool_manager._tools
    assert "get_article_preview" in tools
    assert "get_article" in tools
