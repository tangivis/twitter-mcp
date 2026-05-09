"""Issue #97: text truncation + full_text + quote-tweet error message bugs.

Three claims to verify and fix:

1. **9 list endpoints hardcode `t.text[:200]`** — silently truncates
   tweets >200 chars. Decision (option A): drop the cap entirely;
   `count` already controls response size.

2. **`Tweet.full_text` is unused** — note tweets (X long-form, up to
   4000 chars) get truncated to legacy 280-char `text`. Switch all
   tweet renderings to `t.full_text`, which falls back to `text` for
   non-note tweets so non-note behavior is unchanged.

3. **`get_article_preview` misleading on quote tweets** — current
   error "Tweet X does not embed an article" doesn't help the user
   when the tweet is actually a quote retweet. Detect the
   `quoted_tweet` key in the syndication response and raise a
   targeted error pointing at `get_tweet`.

All tests are mock-only (no live X / no network).
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from twitter_mcp import server


def _fake_user(screen_name="alice", name="Alice"):
    return SimpleNamespace(screen_name=screen_name, name=name)


def _fake_tweet(
    tid="100",
    text="hello",
    full_text=None,
    user=None,
    favorite_count=1,
    retweet_count=0,
    created_at="Mon Jan 01 00:00:00 +0000 2026",
):
    """Mock Tweet with text + full_text + the other accessors get_tweet
    reads (quote / in_reply_to / conversation_id / is_quote_status).

    Real twikit `Tweet.full_text` falls back to `text` if no
    note-tweet result; we mirror that — if `full_text` arg is None,
    `.full_text` returns `.text`."""
    return SimpleNamespace(
        id=tid,
        text=text,
        full_text=full_text if full_text is not None else text,
        user=user or _fake_user(),
        favorite_count=favorite_count,
        retweet_count=retweet_count,
        created_at=created_at,
        in_reply_to=None,
        conversation_id=None,
        is_quote_status=False,
        quote=None,
    )


def _result_with_cursor(items, next_cursor=None):
    """Mimic twikit's `Result[Tweet]` — iterable + `.next_cursor` attr.
    Subclass list (its __iter__ is a class method, so iteration works
    inside list comprehensions; SimpleNamespace + lambda doesn't)."""

    class _R(list):
        pass

    r = _R(items)
    r.next_cursor = next_cursor
    return r


@pytest.fixture
def fake_client(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))
    return client


# ── Bug 1: 200-char truncation in list endpoints ─────


_LONG_TEXT = "x" * 1000  # 5x the old 200 cap


async def test_get_timeline_returns_full_text(fake_client):
    fake_client.get_timeline = AsyncMock(
        return_value=[_fake_tweet(tid="1", text=_LONG_TEXT)]
    )
    out = json.loads(await server.get_timeline(count=5))
    assert out[0]["text"] == _LONG_TEXT, "get_timeline still truncates"


async def test_search_tweets_returns_full_text(fake_client):
    fake_client.search_tweet = AsyncMock(
        return_value=[_fake_tweet(tid="1", text=_LONG_TEXT)]
    )
    out = json.loads(await server.search_tweets(query="hi", count=5))
    assert out[0]["text"] == _LONG_TEXT, "search_tweets still truncates"


async def test_get_user_tweets_returns_full_text(fake_client):
    fake_client.get_user_by_screen_name = AsyncMock(
        return_value=SimpleNamespace(id="123")
    )
    fake_client.get_user_tweets = AsyncMock(
        return_value=[_fake_tweet(tid="1", text=_LONG_TEXT)]
    )
    out = json.loads(await server.get_user_tweets(screen_name="alice", count=5))
    assert out[0]["text"] == _LONG_TEXT, "get_user_tweets still truncates"


async def test_get_bookmarks_returns_full_text(fake_client):
    fake_client.get_bookmarks = AsyncMock(
        return_value=_result_with_cursor([_fake_tweet(tid="1", text=_LONG_TEXT)])
    )
    out = json.loads(await server.get_bookmarks(count=5))
    assert out["tweets"][0]["text"] == _LONG_TEXT, "get_bookmarks still truncates"


async def test_get_list_tweets_returns_full_text(fake_client):
    fake_client.get_list_tweets = AsyncMock(
        return_value=_result_with_cursor([_fake_tweet(tid="1", text=_LONG_TEXT)])
    )
    out = json.loads(await server.get_list_tweets(list_id="L", count=5))
    assert out["tweets"][0]["text"] == _LONG_TEXT, "get_list_tweets still truncates"


async def test_get_community_tweets_returns_full_text(fake_client):
    fake_client.get_community_tweets = AsyncMock(
        return_value=_result_with_cursor([_fake_tweet(tid="1", text=_LONG_TEXT)])
    )
    out = json.loads(
        await server.get_community_tweets(community_id="C", tweet_type="Top", count=5)
    )
    assert out["tweets"][0]["text"] == _LONG_TEXT, (
        "get_community_tweets still truncates"
    )


async def test_get_communities_timeline_returns_full_text(fake_client):
    fake_client.get_communities_timeline = AsyncMock(
        return_value=_result_with_cursor([_fake_tweet(tid="1", text=_LONG_TEXT)])
    )
    out = json.loads(await server.get_communities_timeline(count=5))
    assert out["tweets"][0]["text"] == _LONG_TEXT, (
        "get_communities_timeline still truncates"
    )


async def test_search_community_tweet_returns_full_text(fake_client):
    fake_client.search_community_tweet = AsyncMock(
        return_value=_result_with_cursor([_fake_tweet(tid="1", text=_LONG_TEXT)])
    )
    out = json.loads(
        await server.search_community_tweet(community_id="C", query="hi", count=5)
    )
    assert out["tweets"][0]["text"] == _LONG_TEXT, (
        "search_community_tweet still truncates"
    )


# ── Bug 2: full_text used everywhere (note tweets) ───


_NOTE_TWEET_TEXT = "n" * 3000  # >280, exercises note-tweet fallback


async def test_get_tweet_uses_full_text(fake_client):
    """Note tweets (X long-form): get_tweet should pick `full_text`,
    not legacy `text`."""
    t = _fake_tweet(
        tid="20", text="legacy 280 truncated...", full_text=_NOTE_TWEET_TEXT
    )
    fake_client.get_tweets_by_ids = AsyncMock(return_value=[t])
    out = json.loads(await server.get_tweet("20"))
    assert out["text"] == _NOTE_TWEET_TEXT, (
        "get_tweet returned legacy text instead of full_text — note tweets get cut at 280"
    )


async def test_get_tweet_replies_uses_full_text(fake_client):
    """Replies in get_tweet_replies should also use full_text."""
    reply = _fake_tweet(tid="101", text="legacy short", full_text=_NOTE_TWEET_TEXT)

    class _R(list):
        pass

    res = _R([reply])
    res.next_cursor = None
    parent = SimpleNamespace(id="20", replies=res)
    fake_client.get_tweet_by_id = AsyncMock(return_value=parent)
    out = json.loads(await server.get_tweet_replies("20"))
    assert out["replies"][0]["text"] == _NOTE_TWEET_TEXT, (
        "replies got legacy text not full_text"
    )


async def test_get_timeline_uses_full_text(fake_client):
    t = _fake_tweet(tid="1", text="short legacy", full_text=_NOTE_TWEET_TEXT)
    fake_client.get_timeline = AsyncMock(return_value=[t])
    out = json.loads(await server.get_timeline(count=5))
    assert out[0]["text"] == _NOTE_TWEET_TEXT


# ── Bug 3: get_article_preview quote tweet detection ─


def _stub_syndication(monkeypatch, payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=payload)
    response.raise_for_status = MagicMock()
    instance = MagicMock()
    instance.get = AsyncMock(return_value=response)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(server.httpx, "AsyncClient", MagicMock(return_value=instance))


async def test_get_article_preview_quote_tweet_gets_targeted_error(monkeypatch):
    """Quote tweets have `quoted_tweet` in syndication response. The
    error should point users at `get_tweet` instead of the generic
    'does not embed an article'."""
    payload = {
        "id_str": "999",
        "user": {"screen_name": "elonmusk"},
        "quoted_tweet": {
            "id_str": "888",
            "text": "the quoted content",
            "user": {"screen_name": "jack"},
        },
        # no "article" key
    }
    _stub_syndication(monkeypatch, payload)

    with pytest.raises(ToolError) as exc:
        await server.get_article_preview("999")
    msg = str(exc.value).lower()
    assert "quote" in msg or "quoted" in msg, (
        f"error should mention 'quote'; got: {exc.value!r}"
    )
    assert "get_tweet" in str(exc.value), (
        f"error should suggest get_tweet; got: {exc.value!r}"
    )


async def test_get_article_preview_non_quote_non_article_keeps_existing_error(
    monkeypatch,
):
    """Backward compat: a tweet that's neither quote nor article
    still raises the generic error (no quote-tweet hint)."""
    payload = {"id_str": "111", "user": {"screen_name": "alice"}}
    _stub_syndication(monkeypatch, payload)

    with pytest.raises(ToolError) as exc:
        await server.get_article_preview("111")
    assert "does not embed an article" in str(exc.value)
