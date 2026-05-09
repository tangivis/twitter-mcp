"""Issue #94: get_tweet_replies tool.

Mock-only — never invokes real X. The vendored
`Client.get_tweet_by_id` populates `tweet.replies` as a `Result[Tweet]`;
server's `get_tweet_replies` wraps that into the standard JSON shape.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from twitter_mcp import server


def _fake_user(screen_name="alice", name="Alice"):
    return SimpleNamespace(screen_name=screen_name, name=name)


def _fake_reply_tweet(
    tid="100",
    text="reply text",
    full_text=None,
    user=None,
    favorite_count=1,
    retweet_count=0,
    created_at="Mon Jan 01 00:00:00 +0000 2026",
):
    """Mirrors twikit Tweet — `full_text` falls back to `text` if not given."""
    return SimpleNamespace(
        id=tid,
        text=text,
        full_text=full_text if full_text is not None else text,
        user=user or _fake_user(),
        favorite_count=favorite_count,
        retweet_count=retweet_count,
        created_at=created_at,
    )


def _fake_tweet_with_replies(parent_id, replies, next_cursor=None):
    """Mirror the shape `Client.get_tweet_by_id` returns: a parent tweet
    with `.replies` set to a Result-like (iterable + .next_cursor)."""

    class _FakeResult(list):
        pass

    result = _FakeResult(replies)
    result.next_cursor = next_cursor
    return SimpleNamespace(id=parent_id, replies=result)


@pytest.fixture
def fake_client(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(server, "_get_client", AsyncMock(return_value=client))
    return client


# ── happy path ───────────────────────────────────────


async def test_get_tweet_replies_returns_full_shape(fake_client):
    parent = _fake_tweet_with_replies(
        parent_id="20",
        replies=[
            _fake_reply_tweet(
                tid="101",
                text="first reply",
                user=_fake_user("bob", "Bob"),
                favorite_count=5,
                retweet_count=1,
                created_at="Tue Jan 02 00:00:00 +0000 2026",
            ),
            _fake_reply_tweet(
                tid="102",
                text="second reply",
                user=_fake_user("carol", "Carol"),
            ),
        ],
        next_cursor="cursor-abc",
    )
    fake_client.get_tweet_by_id = AsyncMock(return_value=parent)
    out = json.loads(await server.get_tweet_replies("20"))
    assert out == {
        "tweet_id": "20",
        "replies": [
            {
                "id": "101",
                "author": "bob",
                "text": "first reply",
                "created_at": "Tue Jan 02 00:00:00 +0000 2026",
                "likes": 5,
                "retweets": 1,
            },
            {
                "id": "102",
                "author": "carol",
                "text": "second reply",
                "created_at": "Mon Jan 01 00:00:00 +0000 2026",
                "likes": 1,
                "retweets": 0,
            },
        ],
        "next_cursor": "cursor-abc",
        "count": 2,
    }


async def test_get_tweet_replies_handles_empty(fake_client):
    """Tweet with no replies → shape-stable empty list."""
    parent = _fake_tweet_with_replies(parent_id="20", replies=[], next_cursor=None)
    fake_client.get_tweet_by_id = AsyncMock(return_value=parent)
    out = json.loads(await server.get_tweet_replies("20"))
    assert out["replies"] == []
    assert out["next_cursor"] is None
    assert out["count"] == 0


# ── pagination ───────────────────────────────────────


async def test_get_tweet_replies_passes_cursor_through(fake_client):
    """`cursor` arg flows to `client.get_tweet_by_id` for pagination."""
    parent = _fake_tweet_with_replies(parent_id="20", replies=[], next_cursor="next-2")
    fake_client.get_tweet_by_id = AsyncMock(return_value=parent)

    await server.get_tweet_replies("20", cursor="page-1")
    fake_client.get_tweet_by_id.assert_awaited_once_with("20", cursor="page-1")


async def test_get_tweet_replies_default_cursor_is_none(fake_client):
    parent = _fake_tweet_with_replies(parent_id="20", replies=[])
    fake_client.get_tweet_by_id = AsyncMock(return_value=parent)

    await server.get_tweet_replies("20")
    fake_client.get_tweet_by_id.assert_awaited_once_with("20", cursor=None)


# ── URL extraction ──────────────────────────────────


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("12345", "12345"),
        ("https://x.com/user/status/12345", "12345"),
        ("https://twitter.com/user/status/67890", "67890"),
    ],
)
async def test_get_tweet_replies_extracts_id_from_url(fake_client, url, expected_id):
    parent = _fake_tweet_with_replies(parent_id=expected_id, replies=[])
    fake_client.get_tweet_by_id = AsyncMock(return_value=parent)

    out = json.loads(await server.get_tweet_replies(url))
    assert out["tweet_id"] == expected_id
    fake_client.get_tweet_by_id.assert_awaited_once_with(expected_id, cursor=None)


# ── reply with quoted/in_reply_to fields propagates ──


async def test_get_tweet_by_id_handles_cursor_entry_without_itemcontent():
    """live-smoke regression on `5a1cd35`: X gated burner-side, returned
    a cursor entry whose `content.itemContent` was absent → KeyError.

    Patched `Client.get_tweet_by_id` defensifies both `entries[-1]
    .content.itemContent.value` and the inner `reply.item.itemContent
    .value` reads. Truncated cursor → no next-page partial, no crash.
    """
    from twitter_mcp._vendor.twikit.client.client import Client

    # Response shape: tweet entry + cursor entry that has `content` but
    # no `itemContent` inside. Pre-patch this raised KeyError on the
    # `entries[-1]["content"]["itemContent"]["value"]` access.
    fake_response = {
        "data": {
            "threaded_conversation_with_injections_v2": {
                "instructions": [
                    {
                        "type": "TimelineAddEntries",
                        "entries": [
                            {"entryId": "tweet-20", "content": {}},
                            # Cursor entry truncated — no itemContent
                            {
                                "entryId": "cursor-bottom-0",
                                "content": {"some_other_key": "x"},
                            },
                        ],
                    }
                ]
            }
        }
    }

    client = Client.__new__(Client)
    from unittest.mock import AsyncMock as _AM

    client.gql = SimpleNamespace(tweet_detail=_AM(return_value=(fake_response, None)))

    # Prevent tweet_from_data from constructing a real Tweet for the
    # `tweet-20` entry — return None so we exercise just the post-loop
    # cursor-handling code path.
    from unittest.mock import patch as _patch

    import twitter_mcp._vendor.twikit.client.client as _clientmod

    with _patch.object(_clientmod, "tweet_from_data", return_value=None):
        # tweet=None after the loop → can still raise on cursor reading
        # if the patch is wrong. With the fix, we hit the
        # `tweet.replies = ...` line where tweet is None, that line
        # would AttributeError. So we expect AttributeError, not
        # KeyError — proves the cursor read path is safe.
        with pytest.raises((AttributeError, TypeError)):
            await Client.get_tweet_by_id(client, "20")


async def test_get_tweet_replies_reply_shape_does_not_carry_quoted_or_inreplyto(
    fake_client,
):
    """Reply items use the compact shape (id/author/text/created/likes/
    retweets only) — same shape as `get_user_tweets`/`get_timeline`.
    Nested quote/reply-to would explode JSON; agent can call get_tweet
    on a reply id for deeper introspection."""
    reply = _fake_reply_tweet(tid="101")
    parent = _fake_tweet_with_replies(parent_id="20", replies=[reply])
    fake_client.get_tweet_by_id = AsyncMock(return_value=parent)

    out = json.loads(await server.get_tweet_replies("20"))
    item = out["replies"][0]
    assert set(item.keys()) == {
        "id",
        "author",
        "text",
        "created_at",
        "likes",
        "retweets",
    }
