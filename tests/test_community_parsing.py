"""Issue #76 part 2: defensive parsing for Community + CommunityMember
+ community-related Client methods.

Failure modes seen in live-smoke (PR #75 cascade):

1. `Community.__init__` strict-indexed `data["rest_id"]` (and 5+
   other fields) → `KeyError: 'rest_id'` on burner-gated responses.
2. `CommunityMember.__init__` similarly strict on rest_id + 9
   bool/string fields + nested `legacy.*`.
3. `Client._get_community_users` does `find_dict(...)[0]` →
   `IndexError` when X returns no `items_results`.
4. `Client.get_community_tweets` does `find_dict(...)[0]` and
   `entries[-1]`/`entries[-2]` → `IndexError` on empty timelines.
5. `Client.search_community_tweet` same `find_dict(...)[0]` and
   `items[-1]`/`items[-2]` patterns.

Tests are mock-only (canned response dicts), no network.
"""

from typing import Any

import pytest

from twitter_mcp._vendor.twikit.client.client import Client
from twitter_mcp._vendor.twikit.community import Community, CommunityMember
from twitter_mcp._vendor.twikit.utils import Result

# ── Fixture builders ─────────────────────────────────


def _full_community_data() -> dict[str, Any]:
    """Happy-path data dict for Community.__init__."""
    return {
        "rest_id": "1487102351550775303",
        "name": "Build in Public",
        "member_count": 50000,
        "is_nsfw": False,
        "members_facepile_results": [
            {"result": {"legacy": {"profile_image_url_https": "https://x/u1.jpg"}}}
        ],
        "default_banner_media": {
            "media_info": {"original_img_url": "https://x/banner.jpg"}
        },
        "is_member": False,
        "role": None,
        "description": "A community",
        "join_policy": "Open",
        "created_at": 1700000000000,
        "invites_policy": "MemberInvitesAllowed",
        "is_pinned": False,
    }


def _full_community_member_data() -> dict[str, Any]:
    """Happy-path data dict for CommunityMember.__init__."""
    return {
        "rest_id": "44196397",
        "community_role": "Member",
        "super_following": False,
        "super_follow_eligible": False,
        "super_followed_by": False,
        "smart_blocking": False,
        "is_blue_verified": True,
        "legacy": {
            "screen_name": "elonmusk",
            "name": "Elon Musk",
            "follow_request_sent": False,
            "protected": False,
            "following": False,
            "followed_by": False,
            "blocking": False,
            "profile_image_url_https": "https://x/elon.jpg",
            "verified": True,
        },
    }


def _missing(d: dict, field: str) -> dict:
    out = dict(d)
    out.pop(field)
    return out


# ── Community.__init__ defensive parsing ─────────────


def test_community_full_data_parses():
    """Sanity: happy path works (regression guard)."""
    c = Community(client=None, data=_full_community_data())
    assert c.id == "1487102351550775303"
    assert c.name == "Build in Public"
    assert c.member_count == 50000


def test_community_rest_id_remains_strict():
    """`rest_id` stays strict — core ID."""
    with pytest.raises(KeyError, match="rest_id"):
        Community(client=None, data=_missing(_full_community_data(), "rest_id"))


@pytest.mark.parametrize(
    ("field", "default"),
    [
        ("name", ""),
        ("member_count", 0),
        ("is_nsfw", False),
        ("description", None),
        ("is_member", None),
        ("role", None),
        ("join_policy", None),
        ("created_at", None),
        ("invites_policy", None),
        ("is_pinned", None),
    ],
)
def test_community_optional_fields_default_when_missing(field, default):
    """Each optional field defaults rather than KeyError. Issue #76."""
    c = Community(client=None, data=_missing(_full_community_data(), field))
    assert getattr(c, field) == default


def test_community_handles_missing_facepile():
    """`members_facepile_results` missing → empty list."""
    d = _missing(_full_community_data(), "members_facepile_results")
    c = Community(client=None, data=d)
    assert c.members_facepile_results == []


def test_community_handles_missing_banner():
    """`default_banner_media` missing → `{}` banner."""
    d = _missing(_full_community_data(), "default_banner_media")
    c = Community(client=None, data=d)
    assert c.banner == {}


def test_community_handles_partial_facepile_entry():
    """Facepile entry with broken nested shape → skipped (no crash)."""
    d = _full_community_data()
    d["members_facepile_results"] = [
        {"result": {"legacy": {"profile_image_url_https": "https://x/ok.jpg"}}},
        {"result": {}},  # missing legacy
        {},  # missing result
    ]
    c = Community(client=None, data=d)
    assert c.members_facepile_results == ["https://x/ok.jpg"]


# ── CommunityMember.__init__ defensive parsing ───────


def test_community_member_full_data_parses():
    m = CommunityMember(client=None, data=_full_community_member_data())
    assert m.id == "44196397"
    assert m.screen_name == "elonmusk"
    assert m.name == "Elon Musk"


def test_community_member_rest_id_remains_strict():
    with pytest.raises(KeyError, match="rest_id"):
        CommunityMember(
            client=None, data=_missing(_full_community_member_data(), "rest_id")
        )


@pytest.mark.parametrize(
    ("field", "default"),
    [
        ("community_role", ""),
        ("super_following", False),
        ("super_follow_eligible", False),
        ("super_followed_by", False),
        ("smart_blocking", False),
        ("is_blue_verified", False),
    ],
)
def test_community_member_top_level_optional_defaults(field, default):
    m = CommunityMember(
        client=None, data=_missing(_full_community_member_data(), field)
    )
    assert getattr(m, field) == default


def test_community_member_legacy_missing_entirely():
    """No `legacy` key at all → all legacy-derived fields default."""
    d = _missing(_full_community_member_data(), "legacy")
    m = CommunityMember(client=None, data=d)
    assert m.screen_name == ""
    assert m.name == ""
    assert m.profile_image_url_https == ""
    assert m.verified is False
    assert m.protected is False


def test_community_member_legacy_partial():
    """`legacy` present but missing some fields → those default, others
    populate."""
    d = _full_community_member_data()
    d["legacy"] = {"screen_name": "alice"}  # only screen_name
    m = CommunityMember(client=None, data=d)
    assert m.screen_name == "alice"
    assert m.name == ""
    assert m.profile_image_url_https == ""


# ── _get_community_users empty handling ──────────────


def _empty_community_users_response() -> dict[str, Any]:
    """Response with NO `items_results` key (X gates burner)."""
    return {"data": {"community_results": {"result": {}}}}


async def test_get_community_users_returns_empty_when_no_items():
    """`find_dict(response, 'items_results')` returns [] → empty Result,
    NOT IndexError."""
    client = object.__new__(Client)

    async def fake_f(community_id, count, cursor):
        return _empty_community_users_response(), None

    result = await Client._get_community_users(client, fake_f, "C", 5, None)
    assert isinstance(result, Result)
    assert list(result) == []


# ── get_community_tweets empty handling ──────────────


def _empty_community_tweets_response() -> dict[str, Any]:
    """Response with NO `entries` key — X gated the timeline entirely."""
    return {"data": {"communityResults": {"result": {}}}}


def _empty_entries_response() -> dict[str, Any]:
    """Response with `entries` present but empty array."""
    return {
        "data": {
            "communityResults": {
                "result": {
                    "ranked_community_timeline": {
                        "timeline": {
                            "instructions": [
                                {"type": "TimelineAddEntries", "entries": []}
                            ]
                        }
                    }
                }
            }
        }
    }


async def test_get_community_tweets_top_returns_empty_when_no_entries():
    """No `entries` key (find_dict empty) → empty Result, no IndexError."""
    client = object.__new__(Client)

    async def fake_community_tweets_timeline(community_id, sort, count, cursor):
        return _empty_community_tweets_response(), None

    client.gql = type("FakeGQL", (), {})()
    client.gql.community_tweets_timeline = fake_community_tweets_timeline

    result = await Client.get_community_tweets(client, "C", "Top", count=5, cursor=None)
    assert isinstance(result, Result)
    assert list(result) == []


async def test_get_community_tweets_top_returns_empty_when_entries_empty():
    """`entries` present but `[]` → empty Result, no IndexError on items[-1]."""
    client = object.__new__(Client)

    async def fake_community_tweets_timeline(community_id, sort, count, cursor):
        return _empty_entries_response(), None

    client.gql = type("FakeGQL", (), {})()
    client.gql.community_tweets_timeline = fake_community_tweets_timeline

    result = await Client.get_community_tweets(
        client, "C", "Latest", count=5, cursor=None
    )
    assert list(result) == []


# ── search_community_tweet empty handling ────────────


async def test_search_community_tweet_returns_empty_when_no_entries():
    client = object.__new__(Client)

    async def fake_search_module(community_id, query, count, cursor):
        return _empty_community_tweets_response(), None

    client.gql = type("FakeGQL", (), {})()
    client.gql.community_tweet_search_module_query = fake_search_module
    result = await Client.search_community_tweet(
        client, "C", "ai", count=5, cursor=None
    )
    assert isinstance(result, Result)
    assert list(result) == []


async def test_search_community_tweet_returns_empty_when_entries_empty():
    client = object.__new__(Client)

    async def fake_search_module(community_id, query, count, cursor):
        return _empty_entries_response(), None

    client.gql = type("FakeGQL", (), {})()
    client.gql.community_tweet_search_module_query = fake_search_module
    result = await Client.search_community_tweet(
        client, "C", "ai", count=5, cursor=None
    )
    assert list(result) == []
