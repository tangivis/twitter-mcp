"""Regression tests for resilient User parsing.

X's GraphQL responses intermittently omit `legacy.entities.description.urls`
and `legacy.withheld_in_countries`. The vendored twikit `User.__init__`
previously accessed both via strict indexing, raising KeyError and breaking
every tool that resolves a user (get_user_tweets, user(), etc.).
"""

from typing import Any

import pytest

from twitter_mcp._vendor.twikit.user import User


def _minimal_user_data(
    *,
    entities: dict[str, Any] | None = None,
    include_withheld: bool = True,
) -> dict[str, Any]:
    """Build the smallest `data` dict that satisfies User.__init__.

    Callers override the two fragile fields to exercise the missing-key paths.
    """
    legacy: dict[str, Any] = {
        "created_at": "Mon Jan 01 00:00:00 +0000 2024",
        "name": "Test User",
        "screen_name": "test_user",
        "profile_image_url_https": "https://example.com/avatar.jpg",
        "location": "",
        "description": "",
        "entities": entities if entities is not None else {"description": {"urls": []}},
        "pinned_tweet_ids_str": [],
        "verified": False,
        "possibly_sensitive": False,
        "can_dm": True,
        "can_media_tag": True,
        "want_retweets": False,
        "default_profile": True,
        "default_profile_image": False,
        "has_custom_timelines": False,
        "followers_count": 0,
        "fast_followers_count": 0,
        "normal_followers_count": 0,
        "friends_count": 0,
        "favourites_count": 0,
        "listed_count": 0,
        "media_count": 0,
        "statuses_count": 0,
        "is_translator": False,
        "translator_type": "none",
    }
    if include_withheld:
        legacy["withheld_in_countries"] = []

    return {
        "rest_id": "1234567890",
        "is_blue_verified": False,
        "legacy": legacy,
    }


def test_user_parses_when_description_urls_missing():
    """legacy.entities.description may omit `urls` — must default to []."""
    data = _minimal_user_data(entities={"description": {}})
    user = User(client=None, data=data)
    assert user.description_urls == []


def test_user_parses_when_description_entity_missing():
    """legacy.entities may omit `description` entirely — must default to []."""
    data = _minimal_user_data(entities={})
    user = User(client=None, data=data)
    assert user.description_urls == []


def test_user_parses_when_withheld_in_countries_missing():
    """legacy may omit `withheld_in_countries` — must default to []."""
    data = _minimal_user_data(include_withheld=False)
    user = User(client=None, data=data)
    assert user.withheld_in_countries == []


@pytest.mark.parametrize(
    "entities,include_withheld",
    [
        ({"description": {}}, False),
        ({}, False),
    ],
)
def test_user_parses_when_both_missing(entities, include_withheld):
    """Both fragile fields absent simultaneously — the common real-world case."""
    data = _minimal_user_data(entities=entities, include_withheld=include_withheld)
    user = User(client=None, data=data)
    assert user.description_urls == []
    assert user.withheld_in_countries == []


# ── Phase 2: full defensive parsing ───────────────────
#
# X's GraphQL may omit almost any legacy.* field depending on the account's
# state (no pinned tweet → no pinned_tweet_ids_str; fresh/suspended accounts
# may drop counts, flags, etc.). User.__init__ must not raise KeyError when
# any of these are absent — parse what's present, default the rest.


def test_user_parses_when_legacy_is_empty():
    """legacy = {} must not raise — every non-essential field defaults."""
    data = {
        "rest_id": "1",
        "is_blue_verified": False,
        "legacy": {},
    }
    user = User(client=None, data=data)
    # Counts default to 0
    assert user.followers_count == 0
    assert user.statuses_count == 0
    assert user.media_count == 0
    # Flags default to False
    assert user.verified is False
    assert user.can_dm is False
    # Lists default to []
    assert user.pinned_tweet_ids == []
    assert user.description_urls == []
    assert user.withheld_in_countries == []


@pytest.mark.parametrize(
    "drop_field",
    [
        "pinned_tweet_ids_str",
        "verified",
        "followers_count",
        "friends_count",
        "favourites_count",
        "listed_count",
        "media_count",
        "statuses_count",
        "fast_followers_count",
        "normal_followers_count",
        "can_dm",
        "can_media_tag",
        "want_retweets",
        "default_profile",
        "default_profile_image",
        "has_custom_timelines",
        "possibly_sensitive",
        "is_translator",
        "translator_type",
        "location",
        "description",
        "created_at",
        "profile_image_url_https",
    ],
)
def test_user_parses_when_single_legacy_field_missing(drop_field):
    """Any individual legacy.* field may be absent — User must still construct."""
    data = _minimal_user_data()
    del data["legacy"][drop_field]
    # Must not raise
    User(client=None, data=data)
