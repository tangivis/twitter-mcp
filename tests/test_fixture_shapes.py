"""Guard against mock-shape vs real-shape drift.

If a test fake claims to mock a vendored twikit model, every attribute
the fake defines MUST exist on the real model. Otherwise tests pass
under mocks while production hits `AttributeError` on the real thing.

Worked example: issue #37 — `_fake_user_full` defined
`profile_image_url_https` (the JSON key shape), real `User` exposes
`profile_image_url` (the normalized attribute name). All `get_user_info`
mock tests passed; the first real X call from live-smoke crashed with
``AttributeError: 'User' object has no attribute 'profile_image_url_https'``.

This test would have caught that at PR time, before the bug shipped.
"""

import inspect
import re

import pytest

from tests.test_tools import (
    _fake_community,
    _fake_community_member,
    _fake_list,
    _fake_tweet,
    _fake_user,
    _fake_user_full,
)
from twitter_mcp._vendor.twikit.community import Community, CommunityMember
from twitter_mcp._vendor.twikit.list import List
from twitter_mcp._vendor.twikit.tweet import Tweet
from twitter_mcp._vendor.twikit.user import User


def _accessible_attrs(cls) -> set[str]:
    """All names a caller could read on an instance of `cls`.

    Aggregates three sources (any one is enough to make the attribute
    real and avoid AttributeError at runtime):

      1. `self.X` assignments in `__init__` (direct fields).
      2. `@property` decorated method names (computed accessors —
         this is how `Tweet.text` / `Tweet.favorite_count` / etc. live).
      3. Plain method names on the class (also accessible).

    A regex on `inspect.getsource(cls)` covers all three; full AST
    isn't worth the extra surface area for these flat, parse-style
    twikit models.
    """
    src = inspect.getsource(cls)
    fields = set(re.findall(r"self\.(\w+)\s*[:=]", src))
    properties = set(re.findall(r"@property\s+def\s+(\w+)\s*\(", src))
    methods = set(re.findall(r"^\s+def\s+(\w+)\s*\(", src, flags=re.MULTILINE))
    return fields | properties | methods


def _fake_attrs(factory) -> set[str]:
    """Default-construct the fake and read back its SimpleNamespace fields."""
    return set(vars(factory()))


# (test_fake_factory, real_vendor_class) pairs.
_PAIRS = [
    ("_fake_user", _fake_user, User),
    ("_fake_user_full", _fake_user_full, User),
    ("_fake_tweet", _fake_tweet, Tweet),
    ("_fake_list", _fake_list, List),
    ("_fake_community", _fake_community, Community),
    ("_fake_community_member", _fake_community_member, CommunityMember),
]


@pytest.mark.parametrize(
    ("name", "factory", "real"),
    [(n, f, r) for n, f, r in _PAIRS],
    ids=[n for n, _, _ in _PAIRS],
)
def test_fake_attrs_are_subset_of_real(name, factory, real):
    fake = _fake_attrs(factory)
    real_set = _accessible_attrs(real)
    extra = fake - real_set
    assert not extra, (
        f"Fake `{name}` defines attribute(s) {sorted(extra)} that don't exist on "
        f"real `{real.__name__}`. This is the mock-vs-reality drift that bit issue #37 "
        f"(`profile_image_url_https` vs `profile_image_url`). Either rename the field "
        f"on the fake to match the real model, or remove it. Real model attributes:\n"
        f"  {sorted(real_set)}"
    )
