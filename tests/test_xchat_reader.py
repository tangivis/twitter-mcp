"""Selector loading + DOM-payload normalisation.

These cover the two things that break in practice: X changing the DOM (handled
via selector overrides) and the browser handing back partial/skeleton rows.
No browser is launched — `reader.py` is deliberately Playwright-free.
"""

import json

import pytest

from twitter_mcp.xchat.reader import (
    DEFAULT_SELECTORS,
    load_selectors,
    normalize_conversations,
    normalize_messages,
)


def test_defaults_are_lists_and_not_shared_between_calls():
    first = load_selectors()
    first["message"].append("injected")
    assert "injected" not in load_selectors()["message"]
    assert "injected" not in DEFAULT_SELECTORS["message"]


def test_override_replaces_rather_than_appends(tmp_path):
    path = tmp_path / "sel.json"
    path.write_text(json.dumps({"message": '[data-testid="newThing"]'}))
    selectors = load_selectors(path)
    # A stale default kept as a fallback would just re-match the wrong element.
    assert selectors["message"] == ['[data-testid="newThing"]']
    assert selectors["conversation"] == DEFAULT_SELECTORS["conversation"]


def test_override_accepts_a_list_and_ignores_unknown_keys(tmp_path):
    path = tmp_path / "sel.json"
    path.write_text(json.dumps({"message": ["a", "b"], "not_a_real_key": "x"}))
    selectors = load_selectors(path)
    assert selectors["message"] == ["a", "b"]
    assert "not_a_real_key" not in selectors


@pytest.mark.parametrize("payload", ['{"message": 5}', "[]", "not json"])
def test_malformed_overrides_raise(tmp_path, payload):
    path = tmp_path / "sel.json"
    path.write_text(payload)
    with pytest.raises(ValueError):
        load_selectors(path)


def test_conversations_drop_skeletons_and_deduplicate():
    rows = normalize_conversations(
        [
            {"id": "111", "text": "Alice\nsee you then", "timestamp": "2026-07-01"},
            {"id": None, "text": ""},  # skeleton row rendered while loading
            {"id": "111", "text": "Alice\nduplicate"},
            {"id": "222", "text": "Bob", "encrypted": True},
        ]
    )
    assert [c["conversation_id"] for c in rows] == ["111", "222"]
    assert rows[0]["name"] == "Alice"
    assert rows[0]["preview"] == "see you then"
    # Single-line rows have a name but no preview — not a duplicated name.
    assert rows[1]["preview"] == ""
    assert rows[1]["encrypted"] is True


def test_messages_limit_keeps_the_newest():
    raw = [{"text": f"m{i}", "direction": "incoming"} for i in range(5)]
    # X renders oldest-first, so a limit must slice from the end.
    assert [m["text"] for m in normalize_messages(raw, limit=2)] == ["m3", "m4"]


def test_messages_drop_empties_and_flag_unknown_direction():
    rows = normalize_messages(
        [
            {"text": "  ", "direction": "incoming"},
            {"text": "hi", "direction": "sideways"},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["direction"] == "unknown"
    assert rows[0]["direction_source"] == "layout-heuristic"


def test_messages_tolerate_empty_payload():
    assert normalize_messages(None) == []
    assert normalize_conversations(None) == []
