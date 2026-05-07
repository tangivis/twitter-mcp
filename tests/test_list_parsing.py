"""Issue #76 part 1: defensive parsing for List + list-related Client methods.

Three failure modes seen in live-smoke (PR #75 cascade):

1. `List.__init__` strict-indexed `data["created_at"]` and other
   optional fields. When X drops a field for the burner identity,
   `KeyError` propagates and `get_list` crashes.

2. `Client.get_list_tweets` does `items[-1]["content"]["value"]`
   when the response's `entries` is empty → `IndexError`.

3. `Client._get_list_users` does `find_dict(...)[0]` in two places;
   when X returns no `entries` key (or an entry without `result`),
   `find_dict` returns `[]` and indexing crashes.

Tests are mock-only (canned response dicts), no network.
"""

from typing import Any

import pytest

from twitter_mcp._vendor.twikit.client.client import Client
from twitter_mcp._vendor.twikit.list import List
from twitter_mcp._vendor.twikit.utils import Result

# ── Fixture builders ─────────────────────────────────


def _full_list_data() -> dict[str, Any]:
    """Happy-path data dict for List.__init__ — every documented field present."""
    return {
        "id_str": "1234567890",
        "created_at": 1700000000000,
        "default_banner_media": {"media_info": {"original_img_url": "..."}},
        "custom_banner_media": {"media_info": {"original_img_url": "...custom"}},
        "description": "A test list",
        "following": False,
        "is_member": False,
        "member_count": 5,
        "mode": "Public",
        "muting": False,
        "name": "Test List",
        "pinning": False,
        "subscriber_count": 2,
    }


def _missing(field: str) -> dict[str, Any]:
    """Like `_full_list_data` but with `field` removed."""
    d = _full_list_data()
    d.pop(field)
    return d


# ── List.__init__ defensive parsing ──────────────────


def test_list_full_data_parses():
    """Sanity: happy path works (regression guard)."""
    lst = List(client=None, data=_full_list_data())
    assert lst.id == "1234567890"
    assert lst.name == "Test List"
    assert lst.member_count == 5


def test_list_id_remains_strict():
    """`id_str` is the core identifier — missing it IS a real bug."""
    d = _full_list_data()
    d.pop("id_str")
    with pytest.raises(KeyError, match="id_str"):
        List(client=None, data=d)


@pytest.mark.parametrize(
    ("field", "default"),
    [
        ("created_at", None),
        ("description", ""),
        ("name", ""),
        ("mode", "Public"),
        ("member_count", 0),
        ("subscriber_count", 0),
        ("following", False),
        ("is_member", False),
        ("muting", False),
        ("pinning", False),
    ],
)
def test_list_optional_fields_default_when_missing(field, default):
    """Each optional field, when X drops it, gets a stable default —
    no KeyError. Issue #76 path (c) defensive parse."""
    lst = List(client=None, data=_missing(field))
    assert getattr(lst, field) == default


def test_list_default_banner_missing():
    """Banner media isn't always present (e.g., new lists). Both default
    and custom default to `{}`."""
    d = _full_list_data()
    d.pop("default_banner_media")
    d.pop("custom_banner_media")
    lst = List(client=None, data=d)
    assert lst.default_banner == {}
    assert lst.banner == {}


def test_list_uses_custom_banner_when_present():
    """Custom banner takes precedence over default — original behavior."""
    d = _full_list_data()
    lst = List(client=None, data=d)
    assert lst.banner == {"original_img_url": "...custom"}


def test_list_falls_back_to_default_when_no_custom():
    """Without `custom_banner_media`, `banner` == `default_banner` (original)."""
    d = _full_list_data()
    d.pop("custom_banner_media")
    lst = List(client=None, data=d)
    assert lst.banner == lst.default_banner


# ── _get_list_users empty-entries handling ───────────


def _empty_users_response() -> dict[str, Any]:
    """A GraphQL response shape with NO `entries` key anywhere — what X
    returns when the list has no members visible to the burner."""
    return {"data": {"list": {"members_timeline": {"timeline": {}}}}}


def _entries_no_user_result() -> dict[str, Any]:
    """An `entries` array with one user entry whose `result` is missing
    (truncated payload). Currently crashes on `find_dict(item, 'result')[0]`."""
    return {
        "data": {
            "list": {
                "members_timeline": {
                    "timeline": {
                        "entries": [
                            {
                                "entryId": "user-123",
                                "content": {"itemContent": {}},
                            },
                            {
                                "entryId": "cursor-bottom-0",
                                "content": {"value": "next"},
                            },
                        ]
                    }
                }
            }
        }
    }


async def test_get_list_users_returns_empty_when_no_entries(monkeypatch):
    """`find_dict(response, 'entries')` returns [] → empty Result, NOT
    IndexError. Issue #76 (live-smoke saw this on `get_list_members`)."""
    client = object.__new__(Client)
    client.gql = type("FakeGQL", (), {})()

    async def fake_f(*args):
        return _empty_users_response(), None

    result = await Client._get_list_users(
        client, fake_f, "1093659386737872897", 5, None
    )
    assert isinstance(result, Result)
    assert list(result) == []


async def test_get_list_users_skips_user_entries_without_result():
    """User entry without `result` key → skipped, not IndexError."""
    client = object.__new__(Client)
    client.gql = type("FakeGQL", (), {})()

    async def fake_f(*args):
        return _entries_no_user_result(), None

    result = await Client._get_list_users(client, fake_f, "L", 5, None)
    assert list(result) == []


# ── get_list_tweets empty-entries handling ───────────


def _list_tweets_empty_entries() -> dict[str, Any]:
    """`entries` present but empty array (list with 0 tweets visible)."""
    return {
        "data": {
            "list": {
                "tweets_timeline": {
                    "timeline": {
                        "instructions": [{"type": "TimelineAddEntries", "entries": []}]
                    }
                }
            }
        }
    }


async def test_get_list_tweets_returns_empty_when_entries_empty():
    """Empty entries → empty Result, NOT IndexError on items[-1]."""
    client = object.__new__(Client)

    async def fake_list_latest_tweets_timeline(list_id, count, cursor):
        return _list_tweets_empty_entries(), None

    client.gql = type("FakeGQL", (), {})()
    client.gql.list_latest_tweets_timeline = fake_list_latest_tweets_timeline
    result = await Client.get_list_tweets(client, "L", count=5, cursor=None)
    assert isinstance(result, Result)
    assert list(result) == []
