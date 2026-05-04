"""Behavior tests for the 24 MCP tools.

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
    profile_image_url_https="https://pbs.twimg.com/avatar/x.jpg",
    protected=False,
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
        profile_image_url_https=profile_image_url_https,
        protected=protected,
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
        "profile_image_url": "https://pbs.twimg.com/avatar/x.jpg",
        "protected": False,
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


# ── get_user_info: user_id overload + typed exception handling (PR #24 review) ─


async def test_get_user_info_accepts_user_id_kwarg(fake_client):
    """`user_id=` resolves via twikit's get_user_by_id, NOT screen_name path."""
    fake_client.get_user_by_id = AsyncMock(return_value=_fake_user_full())
    fake_client.get_user_by_screen_name = AsyncMock()  # must NOT be called
    out = json.loads(await server.get_user_info(user_id="2024518793679294464"))
    assert out["id"] == "2024518793679294464"
    fake_client.get_user_by_id.assert_awaited_once_with("2024518793679294464")
    fake_client.get_user_by_screen_name.assert_not_called()


async def test_get_user_info_raises_when_neither_provided(fake_client):
    """Strict contract: caller must give exactly one of screen_name / user_id."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.get_user_info()
    msg = str(exc.value)
    assert "screen_name" in msg and "user_id" in msg


async def test_get_user_info_raises_when_both_provided(fake_client):
    """Both at once is also a contract violation — pick one."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.get_user_info(screen_name="alice", user_id="42")
    msg = str(exc.value)
    assert "screen_name" in msg and "user_id" in msg


async def test_get_user_info_raises_clean_error_on_too_many_requests(fake_client):
    """twikit's TooManyRequests → ToolError with a friendly rate-limit message."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.get_user_by_screen_name = AsyncMock(
        side_effect=TooManyRequests("rate limited")
    )
    with pytest.raises(ToolError) as exc:
        await server.get_user_info("alice")
    assert "rate limit" in str(exc.value).lower()


async def test_get_user_info_raises_clean_error_on_not_found(fake_client):
    """twikit's NotFound → ToolError with a 'user not found' message."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.get_user_by_id = AsyncMock(side_effect=NotFound("no user"))
    with pytest.raises(ToolError) as exc:
        await server.get_user_info(user_id="9999999999999")
    assert "not found" in str(exc.value).lower()
    # The id we asked about appears in the message so callers know what failed.
    assert "9999999999999" in str(exc.value)


# ── get_user_followers / get_user_following ──────────


class _FakeResult(list):
    """Stand-in for twikit's Result[User] — list-like + .next_cursor attr."""

    def __init__(self, users, next_cursor=None):
        super().__init__(users)
        self.next_cursor = next_cursor


def _fake_followers_result(users=None, next_cursor="cursor-page-2"):
    if users is None:
        users = [
            _fake_user_full(
                user_id=f"u-{i}",
                screen_name=f"follower_{i}",
                name=f"Follower {i}",
                description="b" * 250,  # long bio to verify truncation
            )
            for i in range(3)
        ]
    return _FakeResult(users, next_cursor=next_cursor)


async def test_get_user_followers_resolves_screen_name_then_fetches(fake_client):
    """screen_name → get_user_by_screen_name → get_user_followers(user.id)."""
    fake_client.get_user_by_screen_name = AsyncMock(
        return_value=_fake_user_full(user_id="u-42", screen_name="alice")
    )
    fake_client.get_user_followers = AsyncMock(return_value=_fake_followers_result())
    out = json.loads(await server.get_user_followers(screen_name="alice", count=5))
    fake_client.get_user_by_screen_name.assert_awaited_once_with("alice")
    fake_client.get_user_followers.assert_awaited_once_with(
        "u-42", count=5, cursor=None
    )
    assert "users" in out
    assert len(out["users"]) == 3
    assert out["next_cursor"] == "cursor-page-2"


async def test_get_user_followers_uses_user_id_directly_no_resolve(fake_client):
    """When user_id is given, skip the screen_name resolution roundtrip."""
    fake_client.get_user_by_screen_name = AsyncMock()  # must NOT be called
    fake_client.get_user_followers = AsyncMock(return_value=_fake_followers_result())
    await server.get_user_followers(user_id="u-99", count=10)
    fake_client.get_user_by_screen_name.assert_not_called()
    fake_client.get_user_followers.assert_awaited_once_with(
        "u-99", count=10, cursor=None
    )


async def test_get_user_followers_truncates_bio_in_compact_user(fake_client):
    """Bio in the followers list is truncated (long lists otherwise blow the
    MCP_OUTPUT cap). Match get_user_tweets/get_timeline truncation pattern."""
    fake_client.get_user_by_screen_name = AsyncMock(return_value=_fake_user_full())
    long_bio_user = _fake_user_full(description="X" * 500)
    fake_client.get_user_followers = AsyncMock(
        return_value=_fake_followers_result(users=[long_bio_user])
    )
    out = json.loads(await server.get_user_followers(screen_name="alice"))
    assert len(out["users"][0]["description"]) <= 200  # truncated


async def test_get_user_followers_passes_cursor_through(fake_client):
    """Caller can paginate via cursor — pass through verbatim."""
    fake_client.get_user_followers = AsyncMock(return_value=_fake_followers_result())
    await server.get_user_followers(user_id="u-1", count=20, cursor="abc-cursor")
    fake_client.get_user_followers.assert_awaited_once_with(
        "u-1", count=20, cursor="abc-cursor"
    )


async def test_get_user_followers_raises_on_count_over_100(fake_client):
    """Don't silently clamp — raise so callers know about the cap."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.get_user_followers(user_id="u-1", count=500)
    assert "100" in str(exc.value)


async def test_get_user_followers_raises_when_neither_provided(fake_client):
    """Same exactly-one contract as get_user_info."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.get_user_followers()


async def test_get_user_following_mirrors_followers_shape(fake_client):
    """Symmetrical to get_user_followers, just calls get_user_following."""
    fake_client.get_user_following = AsyncMock(return_value=_fake_followers_result())
    out = json.loads(await server.get_user_following(user_id="u-42", count=5))
    fake_client.get_user_following.assert_awaited_once_with(
        "u-42", count=5, cursor=None
    )
    assert "users" in out
    assert "next_cursor" in out


async def test_get_user_following_resolves_screen_name(fake_client):
    fake_client.get_user_by_screen_name = AsyncMock(
        return_value=_fake_user_full(user_id="u-7", screen_name="alice")
    )
    fake_client.get_user_following = AsyncMock(return_value=_fake_followers_result())
    await server.get_user_following(screen_name="alice", count=15)
    fake_client.get_user_by_screen_name.assert_awaited_once_with("alice")
    fake_client.get_user_following.assert_awaited_once_with(
        "u-7", count=15, cursor=None
    )


async def test_get_user_following_raises_on_count_over_100(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.get_user_following(user_id="u-1", count=200)


async def test_get_user_followers_raises_clean_on_rate_limit(fake_client):
    """TooManyRequests during followers fetch → ToolError, not raw twikit error."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.get_user_followers = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.get_user_followers(user_id="u-1")
    assert "rate limit" in str(exc.value).lower()


async def test_get_user_followers_raises_clean_on_not_found(fake_client):
    """NotFound during followers fetch → ToolError naming the missing user."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.get_user_followers = AsyncMock(side_effect=NotFound("nope"))
    with pytest.raises(ToolError) as exc:
        await server.get_user_followers(user_id="ghost")
    assert "ghost" in str(exc.value)


async def test_get_user_following_raises_clean_on_rate_limit(fake_client):
    """Same TooManyRequests pattern for get_user_following."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.get_user_following = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError):
        await server.get_user_following(user_id="u-1")


async def test_get_user_following_raises_clean_on_not_found(fake_client):
    """Same NotFound pattern for get_user_following."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.get_user_following = AsyncMock(side_effect=NotFound("nope"))
    with pytest.raises(ToolError) as exc:
        await server.get_user_following(user_id="ghost")
    assert "ghost" in str(exc.value)


# ── PR #25 Claude review followups ────────────────────


async def test_get_user_followers_raises_clean_on_not_found_during_resolve(fake_client):
    """If screen_name resolution itself raises NotFound, that path is also
    caught — not just the followers-fetch path."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.get_user_by_screen_name = AsyncMock(side_effect=NotFound("no user"))
    with pytest.raises(ToolError) as exc:
        await server.get_user_followers(screen_name="ghost")
    assert "ghost" in str(exc.value)


async def test_get_user_following_raises_clean_on_not_found_during_resolve(fake_client):
    """Same NotFound-during-resolve path on get_user_following."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.get_user_by_screen_name = AsyncMock(side_effect=NotFound("no user"))
    with pytest.raises(ToolError) as exc:
        await server.get_user_following(screen_name="ghost")
    assert "ghost" in str(exc.value)


async def test_get_user_followers_raises_on_count_below_1(fake_client):
    """count=0 / -1 must raise — don't silently forward to twikit."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.get_user_followers(user_id="u-1", count=0)
    with pytest.raises(ToolError):
        await server.get_user_followers(user_id="u-1", count=-5)


async def test_get_user_following_raises_on_count_below_1(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.get_user_following(user_id="u-1", count=0)


# ── delete_tweet ─────────────────────────────────────


async def test_delete_tweet_calls_client_and_returns_deleted(fake_client):
    fake_client.delete_tweet = AsyncMock()
    out = json.loads(await server.delete_tweet("123"))
    assert out == {"tweet_id": "123", "status": "deleted"}
    fake_client.delete_tweet.assert_awaited_once_with("123")


async def test_delete_tweet_raises_clean_on_not_found(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.delete_tweet = AsyncMock(side_effect=NotFound("gone"))
    with pytest.raises(ToolError) as exc:
        await server.delete_tweet("999")
    assert "not found" in str(exc.value).lower()


async def test_delete_tweet_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.delete_tweet = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.delete_tweet("123")
    assert "rate limit" in str(exc.value).lower()


# ── unfavorite_tweet ──────────────────────────────────


async def test_unfavorite_tweet_calls_client_and_returns_unliked(fake_client):
    fake_client.unfavorite_tweet = AsyncMock()
    out = json.loads(await server.unfavorite_tweet("555"))
    assert out == {"tweet_id": "555", "status": "unliked"}
    fake_client.unfavorite_tweet.assert_awaited_once_with("555")


async def test_unfavorite_tweet_raises_clean_on_not_found(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.unfavorite_tweet = AsyncMock(side_effect=NotFound("gone"))
    with pytest.raises(ToolError) as exc:
        await server.unfavorite_tweet("999")
    assert "not found" in str(exc.value).lower()


# ── delete_retweet ────────────────────────────────────


async def test_delete_retweet_calls_client_and_returns_un_retweeted(fake_client):
    fake_client.delete_retweet = AsyncMock()
    out = json.loads(await server.delete_retweet("777"))
    assert out == {"tweet_id": "777", "status": "un-retweeted"}
    fake_client.delete_retweet.assert_awaited_once_with("777")


async def test_delete_retweet_raises_clean_on_not_found(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.delete_retweet = AsyncMock(side_effect=NotFound("gone"))
    with pytest.raises(ToolError) as exc:
        await server.delete_retweet("888")
    assert "not found" in str(exc.value).lower()


# ── bookmark_tweet ────────────────────────────────────


async def test_bookmark_tweet_calls_client_and_returns_bookmarked(fake_client):
    fake_client.bookmark_tweet = AsyncMock()
    out = json.loads(await server.bookmark_tweet("100"))
    assert out == {"tweet_id": "100", "status": "bookmarked"}
    fake_client.bookmark_tweet.assert_awaited_once_with("100", None)


async def test_bookmark_tweet_passes_folder_id(fake_client):
    fake_client.bookmark_tweet = AsyncMock()
    out = json.loads(await server.bookmark_tweet("100", folder_id="folder42"))
    assert out["folder_id"] == "folder42"
    fake_client.bookmark_tweet.assert_awaited_once_with("100", "folder42")


async def test_bookmark_tweet_raises_clean_on_not_found(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.bookmark_tweet = AsyncMock(side_effect=NotFound("gone"))
    with pytest.raises(ToolError) as exc:
        await server.bookmark_tweet("999")
    assert "not found" in str(exc.value).lower()


# ── delete_bookmark ───────────────────────────────────


async def test_delete_bookmark_calls_client_and_returns_un_bookmarked(fake_client):
    fake_client.delete_bookmark = AsyncMock()
    out = json.loads(await server.delete_bookmark("200"))
    assert out == {"tweet_id": "200", "status": "un-bookmarked"}
    fake_client.delete_bookmark.assert_awaited_once_with("200")


async def test_delete_bookmark_raises_clean_on_not_found(fake_client):
    """Error message says 'bookmark not found' (not 'tweet not found') because
    the tweet typically still exists — only the bookmark is missing."""
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.delete_bookmark = AsyncMock(side_effect=NotFound("gone"))
    with pytest.raises(ToolError) as exc:
        await server.delete_bookmark("999")
    msg = str(exc.value).lower()
    assert "bookmark" in msg
    assert "999" in str(exc.value)


# ── get_bookmarks ─────────────────────────────────────


class _FakeTweetResult(list):
    """Stand-in for twikit's Result[Tweet] — list-like + .next_cursor attr."""

    def __init__(self, tweets, next_cursor=None):
        super().__init__(tweets)
        self.next_cursor = next_cursor


def _fake_bookmark_tweet(tid="bk1", text="bookmark text", screen_name="bob"):
    return _fake_tweet(tid=tid, text=text, user=_fake_user(screen_name=screen_name))


async def test_get_bookmarks_returns_compact_tweet_list(fake_client):
    fake_client.get_bookmarks = AsyncMock(
        return_value=_FakeTweetResult(
            [_fake_bookmark_tweet("bk1"), _fake_bookmark_tweet("bk2")],
            next_cursor="cur-2",
        )
    )
    out = json.loads(await server.get_bookmarks(count=20))
    assert out["count"] == 2
    assert out["next_cursor"] == "cur-2"
    assert out["tweets"][0]["id"] == "bk1"
    assert "author" in out["tweets"][0]
    assert "text" in out["tweets"][0]
    assert "likes" in out["tweets"][0]
    assert "retweets" in out["tweets"][0]


async def test_get_bookmarks_truncates_text_to_200(fake_client):
    long_text = "z" * 500
    fake_client.get_bookmarks = AsyncMock(
        return_value=_FakeTweetResult([_fake_bookmark_tweet(text=long_text)])
    )
    out = json.loads(await server.get_bookmarks())
    assert len(out["tweets"][0]["text"]) == 200


async def test_get_bookmarks_passes_count_and_cursor(fake_client):
    fake_client.get_bookmarks = AsyncMock(return_value=_FakeTweetResult([]))
    await server.get_bookmarks(count=10, cursor="abc")
    fake_client.get_bookmarks.assert_awaited_once_with(count=10, cursor="abc")


async def test_get_bookmarks_raises_on_count_too_high(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.get_bookmarks(count=101)
    assert "100" in str(exc.value)


async def test_get_bookmarks_raises_on_count_too_low(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.get_bookmarks(count=0)


async def test_get_bookmarks_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.get_bookmarks = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.get_bookmarks()
    assert "rate limit" in str(exc.value).lower()


# ── get_favoriters ────────────────────────────────────


async def test_get_favoriters_returns_user_list(fake_client):
    fake_client.get_favoriters = AsyncMock(
        return_value=_fake_followers_result(next_cursor="cur-f")
    )
    out = json.loads(await server.get_favoriters("tw-1", count=3))
    fake_client.get_favoriters.assert_awaited_once_with("tw-1", count=3, cursor=None)
    assert "users" in out
    assert out["next_cursor"] == "cur-f"
    assert out["count"] == len(out["users"])


async def test_get_favoriters_passes_cursor(fake_client):
    fake_client.get_favoriters = AsyncMock(return_value=_fake_followers_result())
    await server.get_favoriters("tw-1", count=5, cursor="xyz")
    fake_client.get_favoriters.assert_awaited_once_with("tw-1", count=5, cursor="xyz")


async def test_get_favoriters_raises_on_count_too_high(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.get_favoriters("tw-1", count=200)
    assert "100" in str(exc.value)


async def test_get_favoriters_raises_on_count_too_low(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.get_favoriters("tw-1", count=0)


async def test_get_favoriters_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.get_favoriters = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.get_favoriters("tw-1")
    assert "rate limit" in str(exc.value).lower()


async def test_get_favoriters_raises_clean_on_not_found(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.get_favoriters = AsyncMock(side_effect=NotFound("nope"))
    with pytest.raises(ToolError) as exc:
        await server.get_favoriters("tw-ghost")
    assert "not found" in str(exc.value).lower()


# ── get_retweeters ────────────────────────────────────


async def test_get_retweeters_returns_user_list(fake_client):
    fake_client.get_retweeters = AsyncMock(
        return_value=_fake_followers_result(next_cursor="cur-r")
    )
    out = json.loads(await server.get_retweeters("tw-2", count=5))
    fake_client.get_retweeters.assert_awaited_once_with("tw-2", count=5, cursor=None)
    assert "users" in out
    assert out["next_cursor"] == "cur-r"


async def test_get_retweeters_passes_cursor(fake_client):
    fake_client.get_retweeters = AsyncMock(return_value=_fake_followers_result())
    await server.get_retweeters("tw-2", count=10, cursor="pgcur")
    fake_client.get_retweeters.assert_awaited_once_with(
        "tw-2", count=10, cursor="pgcur"
    )


async def test_get_retweeters_raises_on_count_too_high(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.get_retweeters("tw-2", count=500)
    assert "100" in str(exc.value)


async def test_get_retweeters_raises_on_count_too_low(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.get_retweeters("tw-2", count=-1)


async def test_get_retweeters_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.get_retweeters = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.get_retweeters("tw-2")
    assert "rate limit" in str(exc.value).lower()


async def test_get_retweeters_raises_clean_on_not_found(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import NotFound

    fake_client.get_retweeters = AsyncMock(side_effect=NotFound("nope"))
    with pytest.raises(ToolError) as exc:
        await server.get_retweeters("tw-ghost")
    assert "not found" in str(exc.value).lower()


# ── search_user ───────────────────────────────────────


async def test_search_user_returns_user_list(fake_client):
    fake_client.search_user = AsyncMock(
        return_value=_fake_followers_result(next_cursor="cur-s")
    )
    out = json.loads(await server.search_user("alice", count=5))
    fake_client.search_user.assert_awaited_once_with("alice", count=5, cursor=None)
    assert "users" in out
    assert out["next_cursor"] == "cur-s"
    assert out["count"] == len(out["users"])


async def test_search_user_passes_cursor(fake_client):
    fake_client.search_user = AsyncMock(return_value=_fake_followers_result())
    await server.search_user("bob", count=10, cursor="pg2")
    fake_client.search_user.assert_awaited_once_with("bob", count=10, cursor="pg2")


async def test_search_user_raises_on_count_too_high(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.search_user("query", count=101)
    assert "100" in str(exc.value)


async def test_search_user_raises_on_count_too_low(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.search_user("query", count=0)


async def test_search_user_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.search_user = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.search_user("alice")
    assert "rate limit" in str(exc.value).lower()


# ── get_trends ────────────────────────────────────────


def _fake_trend(name="AI", tweets_count=50000, domain_context="Technology"):
    from types import SimpleNamespace

    return SimpleNamespace(
        name=name, tweets_count=tweets_count, domain_context=domain_context
    )


async def test_get_trends_returns_trend_list(fake_client):
    fake_client.get_trends = AsyncMock(
        return_value=[_fake_trend("AI"), _fake_trend("#Python")]
    )
    out = json.loads(await server.get_trends())
    fake_client.get_trends.assert_awaited_once_with("trending", count=20)
    assert out["category"] == "trending"
    assert len(out["trends"]) == 2
    assert out["trends"][0]["name"] == "AI"
    assert "tweets_count" in out["trends"][0]
    assert "domain_context" in out["trends"][0]


async def test_get_trends_passes_category_and_count(fake_client):
    fake_client.get_trends = AsyncMock(return_value=[])
    await server.get_trends(category="news", count=10)
    fake_client.get_trends.assert_awaited_once_with("news", count=10)


async def test_get_trends_raises_on_invalid_category(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.get_trends(category="invalid")
    assert "category" in str(exc.value).lower()


async def test_get_trends_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.get_trends = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.get_trends()
    assert "rate limit" in str(exc.value).lower()


# ── PR #26 followup: TooManyRequests coverage on action tools ─
# (delete_tweet's rate-limit test already exists; covering the other 4)


async def test_unfavorite_tweet_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.unfavorite_tweet = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.unfavorite_tweet("123")
    assert "rate limit" in str(exc.value).lower()


async def test_delete_retweet_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.delete_retweet = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.delete_retweet("123")
    assert "rate limit" in str(exc.value).lower()


async def test_bookmark_tweet_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.bookmark_tweet = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.bookmark_tweet("123")
    assert "rate limit" in str(exc.value).lower()


async def test_delete_bookmark_raises_clean_on_rate_limit(fake_client):
    from mcp.server.fastmcp.exceptions import ToolError

    from twitter_mcp._vendor.twikit.errors import TooManyRequests

    fake_client.delete_bookmark = AsyncMock(side_effect=TooManyRequests("rate"))
    with pytest.raises(ToolError) as exc:
        await server.delete_bookmark("123")
    assert "rate limit" in str(exc.value).lower()


# ── PR #27 Claude review followups ────────────────────


async def test_get_trends_raises_on_count_too_low(fake_client):
    """Claude PR #27 review: get_trends was missing the count<1 guard."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await server.get_trends(count=0)
    with pytest.raises(ToolError):
        await server.get_trends(count=-3)


async def test_search_user_raises_on_empty_query(fake_client):
    """Claude PR #27 review: empty / whitespace query → clean ToolError."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await server.search_user("")
    assert "empty" in str(exc.value).lower()
    with pytest.raises(ToolError):
        await server.search_user("   ")  # whitespace-only also empty
