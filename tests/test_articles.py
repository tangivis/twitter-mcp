"""Tests for X Article support (issues #4, #7, #10).

Covers:
- _parse_article_url_or_id: URL/ID parsing for article links
- get_tweet article-aware error path + None-guard
- get_article_preview: syndication endpoint, no auth
- get_article: two-hop reader flow (issue #10) — ArticleRedirectScreenQuery
  resolves article_id → tweet_id, then TweetResultByRestId returns the body.
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


# ── get_article: two-hop reader flow (issue #10) ─────


# twikit's gql_get / tweet_result_by_rest_id return `tuple[dict, Response]`,
# not a bare dict (issue #12). Fixtures wrap mocked payloads accordingly so
# tests exercise the actual transport contract.
def _as_twikit_return(payload):
    """Wrap a mocked dict in the (response_json, raw_response) tuple twikit returns."""
    return (payload, MagicMock(name="raw_response"))


def _redirect_response(tweet_id="2048697545527009367"):
    """Hop-1 response: ArticleRedirectScreenQuery resolves article → tweet."""
    return _as_twikit_return(
        {
            "data": {
                "article_result_by_rest_id": {
                    "result": {
                        "__typename": "ArticleEntity",
                        "metadata": {
                            "author_results": {
                                "result": {"core": {"screen_name": "Jaden_riku"}}
                            },
                            "tweet_results": {"rest_id": tweet_id},
                        },
                    }
                }
            }
        }
    )


def _redirect_response_empty():
    """Hop-1 response when the article isn't visible (deleted / private / wrong namespace)."""
    return _as_twikit_return({"data": {"article_result_by_rest_id": {"result": {}}}})


def _tweet_response_with_article(plain_text="full body 13984 chars goes here"):
    """Hop-2 response: TweetResultByRestId with the article payload nested."""
    return _as_twikit_return(
        {
            "data": {
                "tweetResult": {
                    "result": {
                        "__typename": "Tweet",
                        "rest_id": "2048697545527009367",
                        "article": {
                            "article_results": {
                                "result": {
                                    "title": "2026年，日本国运的分水岭",
                                    "preview_text": "preview…",
                                    "plain_text": plain_text,
                                    "content_state": {"blocks": []},
                                    "cover_media": {
                                        "media_info": {
                                            "original_img_url": (
                                                "https://pbs.twimg.com/media/HG13LzYbkAAI7Ro.jpg"
                                            )
                                        }
                                    },
                                    "media_entities": [{} for _ in range(10)],
                                }
                            }
                        },
                    }
                }
            }
        }
    )


def _tweet_response_no_article():
    """Hop-2 response where the tweet exists but has no article payload."""
    return _as_twikit_return(
        {
            "data": {
                "tweetResult": {
                    "result": {"__typename": "Tweet", "rest_id": "2048697545527009367"}
                }
            }
        }
    )


@pytest.fixture
def fake_two_hop_client(monkeypatch):
    """A fake twikit client mocking both hops of the article reader.

    Returns a SimpleNamespace exposing:
      - .client       : the AsyncMock client itself
      - .gql_get      : Hop 1 mock (ArticleRedirectScreenQuery)
      - .tweet_result : Hop 2 mock (TweetResultByRestId)
    By default both return successful responses.
    """
    client = AsyncMock()
    client.gql = SimpleNamespace(
        gql_get=AsyncMock(return_value=_redirect_response()),
        tweet_result_by_rest_id=AsyncMock(return_value=_tweet_response_with_article()),
    )
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))
    return SimpleNamespace(
        client=client,
        gql_get=client.gql.gql_get,
        tweet_result=client.gql.tweet_result_by_rest_id,
    )


async def test_get_article_returns_article_payload(monkeypatch, fake_two_hop_client):
    """Happy path: returns the inner article_results.result JSON-encoded."""
    out = await server.get_article("2048420352397864960")
    payload = json.loads(out)
    assert payload["title"] == "2026年，日本国运的分水岭"
    assert payload["plain_text"] == "full body 13984 chars goes here"
    assert len(payload["media_entities"]) == 10
    assert payload["cover_media"]["media_info"]["original_img_url"].startswith(
        "https://pbs.twimg.com/"
    )


async def test_get_article_hop1_uses_redirect_op_and_hardcoded_query_id(
    monkeypatch, fake_two_hop_client
):
    """Hop 1 must call ArticleRedirectScreenQuery with the captured queryId.

    The dead `ArticleEntityResultByRestId` (the editor op from issue #7) must
    NOT appear in the request URL — that's the bug 0.1.8 had.
    """
    await server.get_article("2048420352397864960")
    args, _ = fake_two_hop_client.gql_get.call_args
    url = args[0]
    assert url == (
        "https://x.com/i/api/graphql/zrSRXJmE1vj37AUmkh2oGg/ArticleRedirectScreenQuery"
    )
    assert "ArticleEntityResultByRestId" not in url


async def test_get_article_hop1_uses_articleEntityId_variable(
    monkeypatch, fake_two_hop_client
):
    """Hop 1's variable is `articleEntityId` (per the issue's curl trace)."""
    await server.get_article("2048420352397864960")
    args, kwargs = fake_two_hop_client.gql_get.call_args
    # variables is the 2nd positional or `variables=` kwarg
    variables = args[1] if len(args) > 1 else kwargs.get("variables", {})
    assert variables == {"articleEntityId": "2048420352397864960"}


async def test_get_article_hop1_passes_empty_features(monkeypatch, fake_two_hop_client):
    """ArticleRedirectScreenQuery is called with `features={}` — confirmed live."""
    await server.get_article("2048420352397864960")
    args, kwargs = fake_two_hop_client.gql_get.call_args
    features = args[2] if len(args) > 2 else kwargs.get("features", {})
    assert features == {}


async def test_get_article_hop2_calls_tweet_result_by_rest_id(
    monkeypatch, fake_two_hop_client
):
    """Hop 2 reuses twikit's existing `tweet_result_by_rest_id` helper."""
    await server.get_article("2048420352397864960")
    fake_two_hop_client.tweet_result.assert_awaited_once_with("2048697545527009367")


async def test_get_article_accepts_url(monkeypatch, fake_two_hop_client):
    """A full /i/article/<id> URL is accepted, normalized to the rest_id."""
    await server.get_article("https://x.com/i/article/2048420352397864960")
    args, kwargs = fake_two_hop_client.gql_get.call_args
    variables = args[1] if len(args) > 1 else kwargs.get("variables", {})
    assert variables["articleEntityId"] == "2048420352397864960"


async def test_get_article_accepts_bare_numeric_id(monkeypatch, fake_two_hop_client):
    """Bare rest_id is also accepted (caller may pass either form)."""
    await server.get_article("2048420352397864960")
    fake_two_hop_client.gql_get.assert_awaited_once()


async def test_get_article_no_env_var_required(monkeypatch, fake_two_hop_client):
    """Issue #7→#10: TWITTER_ARTICLE_QUERY_ID is gone, never read."""
    monkeypatch.delenv("TWITTER_ARTICLE_QUERY_ID", raising=False)
    out = await server.get_article("2048420352397864960")
    assert json.loads(out)["title"] == "2026年，日本国运的分水岭"


async def test_get_article_raises_when_redirect_empty(monkeypatch, fake_two_hop_client):
    """If hop 1 returns `result: {}` (deleted/private/wrong-id), raise a clean error.

    Don't fall through to hop 2 with a None tweet_id.
    """
    fake_two_hop_client.gql_get.return_value = _redirect_response_empty()
    with pytest.raises(ToolError) as exc:
        await server.get_article("9999999999999999")
    msg = str(exc.value).lower()
    assert "9999999999999999" in str(exc.value)
    assert "not found" in msg or "not visible" in msg or "private" in msg
    fake_two_hop_client.tweet_result.assert_not_called()


async def test_get_article_raises_when_redirect_missing_tweet_id(
    monkeypatch, fake_two_hop_client
):
    """Hop 1 returns metadata without tweet_results — also a clean ToolError."""
    fake_two_hop_client.gql_get.return_value = _as_twikit_return(
        {
            "data": {
                "article_result_by_rest_id": {
                    "result": {"__typename": "ArticleEntity", "metadata": {}}
                }
            }
        }
    )
    with pytest.raises(ToolError):
        await server.get_article("2048420352397864960")
    fake_two_hop_client.tweet_result.assert_not_called()


async def test_get_article_raises_when_hop2_has_no_article(
    monkeypatch, fake_two_hop_client
):
    """Hop 2 returns a tweet without the .article subtree — clean ToolError."""
    fake_two_hop_client.tweet_result.return_value = _tweet_response_no_article()
    with pytest.raises(ToolError) as exc:
        await server.get_article("2048420352397864960")
    msg = str(exc.value).lower()
    assert "article" in msg


# ── extra coverage: ordering, alt URL forms, malformed responses ────


async def test_get_article_hop1_runs_before_hop2(monkeypatch, fake_two_hop_client):
    """Hop 2 must not be called before hop 1 completes (would race on tweet_id)."""
    call_order = []

    async def hop1(*a, **kw):
        call_order.append("hop1")
        return _redirect_response()

    async def hop2(*a, **kw):
        call_order.append("hop2")
        return _tweet_response_with_article()

    fake_two_hop_client.client.gql.gql_get = AsyncMock(side_effect=hop1)
    fake_two_hop_client.client.gql.tweet_result_by_rest_id = AsyncMock(side_effect=hop2)

    await server.get_article("2048420352397864960")
    assert call_order == ["hop1", "hop2"]


async def test_get_article_hop2_receives_resolved_tweet_id(
    monkeypatch, fake_two_hop_client
):
    """The tweet_id passed to hop 2 must come from hop 1's response, verbatim."""
    fake_two_hop_client.gql_get.return_value = _redirect_response(tweet_id="9988776655")
    await server.get_article("2048420352397864960")
    fake_two_hop_client.tweet_result.assert_awaited_once_with("9988776655")


async def test_get_article_accepts_twitter_com_url(monkeypatch, fake_two_hop_client):
    """`twitter.com` URLs (legacy) are accepted alongside `x.com`."""
    await server.get_article("https://twitter.com/i/article/2048420352397864960")
    args, kwargs = fake_two_hop_client.gql_get.call_args
    variables = args[1] if len(args) > 1 else kwargs.get("variables", {})
    assert variables["articleEntityId"] == "2048420352397864960"


async def test_get_article_ignores_stale_env_var(monkeypatch, fake_two_hop_client):
    """Even if a stale TWITTER_ARTICLE_QUERY_ID is set, the new flow ignores it."""
    monkeypatch.setenv("TWITTER_ARTICLE_QUERY_ID", "STALE_HASH_FROM_USER_ENV")
    await server.get_article("2048420352397864960")
    args, _ = fake_two_hop_client.gql_get.call_args
    assert "STALE_HASH_FROM_USER_ENV" not in args[0]


async def test_get_article_raises_when_redirect_body_is_none(
    monkeypatch, fake_two_hop_client
):
    """A None redirect body (network glitch / malformed) → ToolError, no crash."""
    fake_two_hop_client.gql_get.return_value = _as_twikit_return(None)
    with pytest.raises(ToolError):
        await server.get_article("2048420352397864960")
    fake_two_hop_client.tweet_result.assert_not_called()


async def test_get_article_raises_when_redirect_missing_data_key(
    monkeypatch, fake_two_hop_client
):
    """Redirect response without a `data` key → ToolError, no traceback."""
    fake_two_hop_client.gql_get.return_value = _as_twikit_return(
        {"errors": [{"message": "rate limit"}]}
    )
    with pytest.raises(ToolError):
        await server.get_article("2048420352397864960")
    fake_two_hop_client.tweet_result.assert_not_called()


async def test_get_article_raises_when_hop2_body_is_none(
    monkeypatch, fake_two_hop_client
):
    """A None tweet body (twikit transient failure) → ToolError, not crash."""
    fake_two_hop_client.tweet_result.return_value = _as_twikit_return(None)
    with pytest.raises(ToolError):
        await server.get_article("2048420352397864960")


async def test_get_article_unpacks_tuple_returned_by_twikit(
    monkeypatch, fake_two_hop_client
):
    """Issue #12 regression: gql_get / tweet_result_by_rest_id return
    `tuple[dict, Response]`, not a dict.

    The fix in 0.1.10 unpacks both with `body, _ = await ...`. If a
    future refactor removes the unpack, the production code would call
    `.get()` on a tuple and crash with the exact bug from issue #12:
    `'tuple' object has no attribute 'get'`. This test pins the contract.
    """
    # Both fixtures already return tuples (per the issue).
    out = await server.get_article("2048420352397864960")
    payload = json.loads(out)
    # The article body must have flowed through both unpacks correctly.
    assert payload["title"] == "2026年，日本国运的分水岭"
    assert payload["plain_text"] == "full body 13984 chars goes here"


async def test_get_article_preserves_full_article_payload(
    monkeypatch, fake_two_hop_client
):
    """Tool output preserves every field of `article_results.result` verbatim.

    Important for downstream callers that want plain_text, content_state
    (rich blocks for layout), cover_media URL, media_entities, etc.
    """
    out = await server.get_article("2048420352397864960")
    payload = json.loads(out)
    # All fields the issue's verification curl pulled out:
    assert "title" in payload
    assert "preview_text" in payload
    assert "plain_text" in payload
    assert "content_state" in payload
    assert "cover_media" in payload
    assert "media_entities" in payload


# ── vendor patch: withArticlePlainText flipped to True (issue #10) ────


def test_vendor_tweet_result_passes_article_plain_text_true():
    """The vendored twikit `tweet_result_by_rest_id` must request plain_text.

    Issue #10: with `withArticlePlainText: False` the tweet response carries
    only metadata; flipping it to True is what makes the article body
    (`.article.article_results.result.plain_text`) actually populated. This
    is the smallest possible vendor patch.
    """
    import inspect

    from twitter_mcp._vendor.twikit.client.gql import GQLClient

    src = inspect.getsource(GQLClient.tweet_result_by_rest_id)
    # The toggle must be present and set to True.
    assert "withArticlePlainText" in src
    # Disallow the False form anywhere in this method.
    assert "'withArticlePlainText': False" not in src
    assert '"withArticlePlainText": False' not in src
    # And confirm the True form is what we ship.
    assert (
        "'withArticlePlainText': True" in src or '"withArticlePlainText": True' in src
    )


# ── tool registration ────────────────────────────────


def test_new_tools_registered():
    tools = server.mcp._tool_manager._tools
    assert "get_article_preview" in tools
    assert "get_article" in tools
