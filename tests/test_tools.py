"""Behavior tests for the 12 MCP tools.

Uses mocks to exercise each tool's body without network or real cookies.
Covers: args passed through to twikit, output JSON shape, text truncation,
URL parsing in get_tweet, and action-only tools (like/retweet) that return
confirmation JSON.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from twitter_mcp import server


def _fake_user(screen_name="alice", name="Alice", user_id="42"):
    return SimpleNamespace(id=user_id, screen_name=screen_name, name=name)


def _fake_tweet(
    tid="100",
    text="hello world",
    user=None,
    favorite_count=5,
    retweet_count=2,
    created_at="Mon Jan 01 00:00:00 +0000 2026",
):
    return SimpleNamespace(
        id=tid,
        text=text,
        user=user or _fake_user(),
        favorite_count=favorite_count,
        retweet_count=retweet_count,
        created_at=created_at,
    )


@pytest.fixture
def fake_client(monkeypatch):
    """Inject an AsyncMock client returned from server._get_client."""
    client = AsyncMock()
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))
    return client


# ── send_tweet ───────────────────────────────────────


async def test_send_tweet_returns_sent_status(fake_client):
    fake_client.create_tweet = AsyncMock(return_value=_fake_tweet(tid="999"))
    out = json.loads(await server.send_tweet("hi there"))
    assert out == {"id": "999", "text": "hi there", "status": "sent"}


async def test_send_tweet_passes_text_and_reply_to(fake_client):
    fake_client.create_tweet = AsyncMock(return_value=_fake_tweet())
    await server.send_tweet("reply body", reply_to="42")
    fake_client.create_tweet.assert_awaited_once_with(text="reply body", reply_to="42")


async def test_send_tweet_default_reply_to_is_none(fake_client):
    fake_client.create_tweet = AsyncMock(return_value=_fake_tweet())
    await server.send_tweet("standalone")
    fake_client.create_tweet.assert_awaited_once_with(text="standalone", reply_to=None)


# ── get_tweet ────────────────────────────────────────


async def test_get_tweet_returns_full_shape(fake_client):
    t = _fake_tweet(
        tid="12345",
        text="a tweet",
        user=_fake_user(screen_name="bob", name="Bob B."),
        favorite_count=10,
        retweet_count=3,
        created_at="Sat Apr 18 10:00:00 +0000 2026",
    )
    fake_client.get_tweets_by_ids = AsyncMock(return_value=[t])
    out = json.loads(await server.get_tweet("12345"))
    assert out == {
        "id": "12345",
        "author": "bob",
        "author_name": "Bob B.",
        "text": "a tweet",
        "created_at": "Sat Apr 18 10:00:00 +0000 2026",
        "likes": 10,
        "retweets": 3,
    }


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("12345", "12345"),
        ("https://x.com/user/status/12345", "12345"),
        ("https://x.com/user/status/12345/", "12345"),
        ("https://twitter.com/user/status/67890", "67890"),
    ],
)
async def test_get_tweet_parses_urls(fake_client, url, expected_id):
    fake_client.get_tweets_by_ids = AsyncMock(
        return_value=[_fake_tweet(tid=expected_id)]
    )
    await server.get_tweet(url)
    fake_client.get_tweets_by_ids.assert_awaited_once_with([expected_id])


# ── get_timeline ─────────────────────────────────────


async def test_get_timeline_returns_list_with_truncated_text(fake_client):
    long_text = "x" * 500
    fake_client.get_timeline = AsyncMock(
        return_value=[_fake_tweet(tid="1", text=long_text)]
    )
    out = json.loads(await server.get_timeline(count=5))
    assert len(out) == 1
    assert out[0]["id"] == "1"
    assert len(out[0]["text"]) == 200  # truncated to 200 chars


async def test_get_timeline_default_count(fake_client):
    fake_client.get_timeline = AsyncMock(return_value=[])
    await server.get_timeline()
    fake_client.get_timeline.assert_awaited_once_with(count=20)


async def test_get_timeline_passes_count(fake_client):
    fake_client.get_timeline = AsyncMock(return_value=[])
    await server.get_timeline(count=7)
    fake_client.get_timeline.assert_awaited_once_with(count=7)


async def test_get_timeline_empty_returns_empty_array(fake_client):
    fake_client.get_timeline = AsyncMock(return_value=[])
    assert json.loads(await server.get_timeline()) == []


# ── search_tweets ────────────────────────────────────


async def test_search_tweets_passes_query_product_count(fake_client):
    fake_client.search_tweet = AsyncMock(return_value=[])
    await server.search_tweets("opus 4.7", count=3, product="Top")
    fake_client.search_tweet.assert_awaited_once_with(
        "opus 4.7", product="Top", count=3
    )


async def test_search_tweets_defaults_to_latest(fake_client):
    fake_client.search_tweet = AsyncMock(return_value=[])
    await server.search_tweets("q")
    fake_client.search_tweet.assert_awaited_once_with("q", product="Latest", count=20)


async def test_search_tweets_formats_results(fake_client):
    fake_client.search_tweet = AsyncMock(
        return_value=[
            _fake_tweet(tid="a", text="short", favorite_count=1, retweet_count=0),
            _fake_tweet(tid="b", text="y" * 300, favorite_count=2, retweet_count=1),
        ]
    )
    out = json.loads(await server.search_tweets("q"))
    assert len(out) == 2
    assert out[0]["id"] == "a"
    assert out[0]["text"] == "short"
    assert len(out[1]["text"]) == 200  # truncated


# ── like_tweet ───────────────────────────────────────


async def test_like_tweet_calls_favorite_and_returns_status(fake_client):
    fake_client.favorite_tweet = AsyncMock()
    out = json.loads(await server.like_tweet("555"))
    assert out == {"tweet_id": "555", "status": "liked"}
    fake_client.favorite_tweet.assert_awaited_once_with("555")


# ── retweet ──────────────────────────────────────────


async def test_retweet_calls_retweet_and_returns_status(fake_client):
    fake_client.retweet = AsyncMock()
    out = json.loads(await server.retweet("777"))
    assert out == {"tweet_id": "777", "status": "retweeted"}
    fake_client.retweet.assert_awaited_once_with("777")


# ── get_user_tweets ──────────────────────────────────


async def test_get_user_tweets_resolves_screen_name_then_fetches(fake_client):
    user = _fake_user(user_id="u-1", screen_name="alice")
    fake_client.get_user_by_screen_name = AsyncMock(return_value=user)
    fake_client.get_user_tweets = AsyncMock(
        return_value=[_fake_tweet(tid="t1", text="tweet one")]
    )

    out = json.loads(await server.get_user_tweets("alice", count=4))

    fake_client.get_user_by_screen_name.assert_awaited_once_with("alice")
    fake_client.get_user_tweets.assert_awaited_once_with(
        "u-1", tweet_type="Tweets", count=4
    )
    assert len(out) == 1
    assert out[0]["id"] == "t1"
    assert out[0]["text"] == "tweet one"


async def test_get_user_tweets_truncates_long_text(fake_client):
    fake_client.get_user_by_screen_name = AsyncMock(return_value=_fake_user())
    fake_client.get_user_tweets = AsyncMock(
        return_value=[_fake_tweet(tid="t", text="z" * 1000)]
    )
    out = json.loads(await server.get_user_tweets("alice"))
    assert len(out[0]["text"]) == 200


async def test_get_user_tweets_empty(fake_client):
    fake_client.get_user_by_screen_name = AsyncMock(return_value=_fake_user())
    fake_client.get_user_tweets = AsyncMock(return_value=[])
    assert json.loads(await server.get_user_tweets("alice")) == []


# ── follow_user / unfollow_user (issue #18) ──────────


async def test_follow_user_resolves_screen_name_then_calls_follow(fake_client):
    """follow_user takes a screen_name (matches get_user_tweets convention),
    resolves to a numeric user_id, then calls twikit's follow_user(user_id)."""
    user = _fake_user(user_id="u-42", screen_name="ClaudeDevs")
    fake_client.get_user_by_screen_name = AsyncMock(return_value=user)
    fake_client.follow_user = AsyncMock()

    out = json.loads(await server.follow_user("ClaudeDevs"))

    fake_client.get_user_by_screen_name.assert_awaited_once_with("ClaudeDevs")
    fake_client.follow_user.assert_awaited_once_with("u-42")
    assert out == {
        "user_id": "u-42",
        "screen_name": "ClaudeDevs",
        "status": "followed",
    }


async def test_unfollow_user_resolves_screen_name_then_calls_unfollow(fake_client):
    """Same shape as follow_user, mirrored verb."""
    user = _fake_user(user_id="u-99", screen_name="ClaudeDevs")
    fake_client.get_user_by_screen_name = AsyncMock(return_value=user)
    fake_client.unfollow_user = AsyncMock()

    out = json.loads(await server.unfollow_user("ClaudeDevs"))

    fake_client.get_user_by_screen_name.assert_awaited_once_with("ClaudeDevs")
    fake_client.unfollow_user.assert_awaited_once_with("u-99")
    assert out == {
        "user_id": "u-99",
        "screen_name": "ClaudeDevs",
        "status": "unfollowed",
    }


async def test_follow_user_does_not_call_follow_if_resolve_fails(monkeypatch):
    """If get_user_by_screen_name raises, follow_user must propagate (no
    silent swallow) and must not have invoked follow_user with a bad id."""
    client = AsyncMock()
    client.get_user_by_screen_name = AsyncMock(side_effect=RuntimeError("no such user"))
    client.follow_user = AsyncMock()
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))

    with pytest.raises(RuntimeError):
        await server.follow_user("ghost")
    client.follow_user.assert_not_called()


async def test_unfollow_user_does_not_call_unfollow_if_resolve_fails(monkeypatch):
    client = AsyncMock()
    client.get_user_by_screen_name = AsyncMock(side_effect=RuntimeError("no such user"))
    client.unfollow_user = AsyncMock()
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))

    with pytest.raises(RuntimeError):
        await server.unfollow_user("ghost")
    client.unfollow_user.assert_not_called()


# ── get_user_info (issue #22) ────────────────────────


def _fake_user_full(
    user_id="2024518793679294464",
    screen_name="ClaudeDevs",
    name="Claude Devs",
    description="bio text",
    created_at="Mon Jan 01 00:00:00 +0000 2026",
    followers_count=1234,
    following_count=42,
    statuses_count=99,
    verified=True,
    is_blue_verified=True,
    location="The Cloud",
    url="https://claude.com",
):
    return SimpleNamespace(
        id=user_id,
        screen_name=screen_name,
        name=name,
        description=description,
        created_at=created_at,
        followers_count=followers_count,
        following_count=following_count,
        statuses_count=statuses_count,
        verified=verified,
        is_blue_verified=is_blue_verified,
        location=location,
        url=url,
    )


async def test_get_user_info_returns_full_metadata_shape(fake_client):
    """Happy path: returns the documented JSON shape, no missing keys."""
    fake_client.get_user_by_screen_name = AsyncMock(return_value=_fake_user_full())
    out = json.loads(await server.get_user_info("ClaudeDevs"))
    assert out == {
        "id": "2024518793679294464",
        "screen_name": "ClaudeDevs",
        "name": "Claude Devs",
        "description": "bio text",
        "created_at": "Mon Jan 01 00:00:00 +0000 2026",
        "followers_count": 1234,
        "following_count": 42,
        "tweets_count": 99,
        "verified": True,
        "is_blue_verified": True,
        "location": "The Cloud",
        "url": "https://claude.com",
    }
    fake_client.get_user_by_screen_name.assert_awaited_once_with("ClaudeDevs")


async def test_get_user_info_passes_screen_name_through(fake_client):
    """The screen_name arg is forwarded verbatim to twikit's resolver."""
    fake_client.get_user_by_screen_name = AsyncMock(return_value=_fake_user_full())
    await server.get_user_info("elonmusk")
    fake_client.get_user_by_screen_name.assert_awaited_once_with("elonmusk")


async def test_get_user_info_propagates_resolve_failure(monkeypatch):
    """If twikit raises (unknown user / network), the tool propagates — no swallow."""
    client = AsyncMock()
    client.get_user_by_screen_name = AsyncMock(side_effect=RuntimeError("no such user"))
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))

    with pytest.raises(RuntimeError):
        await server.get_user_info("ghost")


async def test_get_user_info_uses_statuses_count_for_tweets_count(fake_client):
    """twikit's User.statuses_count maps to our `tweets_count` key (issue #22 spec)."""
    fake_client.get_user_by_screen_name = AsyncMock(
        return_value=_fake_user_full(statuses_count=12345)
    )
    out = json.loads(await server.get_user_info("anyone"))
    assert out["tweets_count"] == 12345
    # And the upstream key name does NOT leak into the output.
    assert "statuses_count" not in out


async def test_get_user_info_exposes_both_verified_fields(fake_client):
    """PR #23 review: u.verified is the legacy gold/grey badge (almost
    always False on modern X); u.is_blue_verified is the X Premium blue
    badge that most users actually have. Expose BOTH so callers don't
    silently get misleading false negatives.
    """
    fake_client.get_user_by_screen_name = AsyncMock(
        return_value=_fake_user_full(verified=False, is_blue_verified=True)
    )
    out = json.loads(await server.get_user_info("modern_user"))
    assert out["verified"] is False
    assert out["is_blue_verified"] is True


async def test_get_user_info_handles_none_optional_fields(fake_client):
    """PR #23 review gap: description / location / url can be None (twikit's
    User defaults missing legacy.* fields to None). Output must round-trip
    them as JSON null, not the string "None".
    """
    fake_client.get_user_by_screen_name = AsyncMock(
        return_value=_fake_user_full(description=None, location=None, url=None)
    )
    out = json.loads(await server.get_user_info("sparse_user"))
    assert out["description"] is None
    assert out["location"] is None
    assert out["url"] is None
