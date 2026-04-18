"""Regression tests for resilient Tweet parsing.

Tweet properties lazy-read `_legacy` on access, so the crash surface is
different from User's: constructing the object is fine, but touching
`tweet.text` / `tweet.favorite_count` / etc. on a tweet whose legacy is
incomplete raises KeyError.

We exercise the handful of properties that server.py actually reads
(`text`, `created_at`, `favorite_count`, `retweet_count`) plus the other
common ones (`lang`, `reply_count`, `favorited`, `is_quote_status`, and
the `entities.*` properties) to prevent the next crash in line.
"""

import pytest

from twitter_mcp._vendor.twikit.tweet import Tweet


def _tweet(legacy=None, **extra):
    data = {"rest_id": "1"}
    if legacy is not None:
        data["legacy"] = legacy
    data.update(extra)
    return Tweet(client=None, data=data)


def test_tweet_constructs_without_legacy_key():
    """data with no legacy should not raise — legacy defaults to {}."""
    t = _tweet()
    assert t.id == "1"


def test_tweet_constructs_with_empty_legacy():
    assert _tweet({}).id == "1"


# ── Properties server.py reads ──


def test_text_defaults_to_empty_string_when_missing():
    assert _tweet({}).text == ""


def test_created_at_defaults_to_empty_string_when_missing():
    assert _tweet({}).created_at == ""


def test_favorite_count_defaults_to_zero_when_missing():
    assert _tweet({}).favorite_count == 0


def test_retweet_count_defaults_to_zero_when_missing():
    assert _tweet({}).retweet_count == 0


# ── Other commonly-accessed properties ──


def test_lang_defaults_to_empty_string_when_missing():
    assert _tweet({}).lang == ""


def test_reply_count_defaults_to_zero_when_missing():
    assert _tweet({}).reply_count == 0


def test_favorited_defaults_to_false_when_missing():
    assert _tweet({}).favorited is False


def test_is_quote_status_defaults_to_false_when_missing():
    assert _tweet({}).is_quote_status is False


# ── Entities sub-tree ──


def test_hashtags_when_entities_absent():
    """legacy.entities may be absent — hashtags must default to []."""
    assert _tweet({}).hashtags == []


def test_urls_when_entities_absent():
    """legacy.entities may be absent — urls must not raise."""
    t = _tweet({})
    # Don't assert exact value; just that it doesn't raise and is falsy.
    assert not t.urls


def test_media_when_entities_absent():
    """legacy.entities may be absent — media must default to []."""
    assert _tweet({}).media == []


# ── Populated legacy still returns real values ──


def test_populated_legacy_returns_real_values():
    t = _tweet(
        {
            "full_text": "hello",
            "created_at": "Mon Jan 01 00:00:00 +0000 2026",
            "favorite_count": 42,
            "retweet_count": 7,
            "reply_count": 3,
            "favorited": True,
            "is_quote_status": True,
            "lang": "en",
        }
    )
    assert t.text == "hello"
    assert t.created_at == "Mon Jan 01 00:00:00 +0000 2026"
    assert t.favorite_count == 42
    assert t.retweet_count == 7
    assert t.reply_count == 3
    assert t.favorited is True
    assert t.is_quote_status is True
    assert t.lang == "en"


@pytest.mark.parametrize(
    "drop_field",
    [
        "full_text",
        "created_at",
        "favorite_count",
        "retweet_count",
        "reply_count",
        "favorited",
        "is_quote_status",
        "lang",
    ],
)
def test_any_single_legacy_field_can_be_dropped(drop_field):
    """Dropping any individual legacy.* field must not raise on access."""
    full = {
        "full_text": "hello",
        "created_at": "ts",
        "favorite_count": 1,
        "retweet_count": 2,
        "reply_count": 3,
        "favorited": True,
        "is_quote_status": False,
        "lang": "en",
    }
    del full[drop_field]
    t = _tweet(full)
    # Touch every property; defaults kick in for the dropped one.
    t.text, t.created_at, t.favorite_count, t.retweet_count
    t.reply_count, t.favorited, t.is_quote_status, t.lang
