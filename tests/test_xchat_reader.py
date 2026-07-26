"""Selector loading + DOM-payload normalisation.

These cover the two things that break in practice: X changing the DOM (handled
via selector overrides) and the browser handing back partial/skeleton rows.
No browser is launched — `reader.py` is deliberately Playwright-free.
"""

import json

import pytest

from twitter_mcp.xchat.reader import (
    DEFAULT_SELECTORS,
    capture_accessibility_tree,
    extract_conversations_from_ax,
    extract_messages_from_ax,
    load_selectors,
    normalize_conversations,
    normalize_messages,
    semantic_diagnostics,
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


def _ax(node_id, role, name="", children=(), url=None, parent=None, bounds=None):
    properties = []
    if url:
        properties.append({"name": "url", "value": {"value": url}})
    node = {
        "nodeId": node_id,
        "role": {"value": role},
        "name": {"value": name},
        "childIds": list(children),
        "properties": properties,
    }
    if parent is not None:
        node["parentId"] = parent
    if bounds is not None:
        node["_bounds"] = bounds
    return node


def test_ax_conversations_use_semantic_links_and_modern_chat_routes():
    nodes = [
        _ax("root", "RootWebArea", "X", ("nav", "row"), "https://x.com/i/chat"),
        _ax("nav", "link", "Direct Messages", url="https://x.com/i/chat"),
        _ax(
            "row",
            "link",
            "Alice @alice See you Tuesday",
            ("name", "handle", "preview"),
            "https://x.com/i/chat/123-456",
        ),
        _ax("name", "StaticText", "Alice"),
        _ax("handle", "StaticText", "@alice"),
        _ax("preview", "StaticText", "See you Tuesday"),
    ]

    assert extract_conversations_from_ax(nodes) == [
        {
            "conversation_id": "123-456",
            "name": "Alice",
            "screen_name": "alice",
            "preview": "See you Tuesday",
            "timestamp": None,
            "encrypted": True,
            "unread": False,
        }
    ]


def test_ax_messages_use_semantic_item_boundaries_not_css_test_ids():
    nodes = [
        _ax("root", "RootWebArea", "X", ("timeline",)),
        _ax("timeline", "list", "Conversation timeline", ("m1", "m2")),
        _ax("m1", "listitem", "Message from Alice", ("m1-text", "m1-time")),
        _ax("m1-text", "StaticText", "Hello there"),
        _ax("m1-time", "time", "10:31"),
        _ax("m2", "listitem", "You sent a message", ("m2-text", "m2-time")),
        _ax("m2-text", "StaticText", "Hi Alice"),
        _ax("m2-time", "time", "10:32"),
    ]

    assert extract_messages_from_ax(nodes) == [
        {
            "text": "Hello there",
            "timestamp": "10:31",
            "direction": "incoming",
            "direction_source": "accessible-name",
        },
        {
            "text": "Hi Alice",
            "timestamp": "10:32",
            "direction": "outgoing",
            "direction_source": "accessible-name",
        },
    ]


def test_semantic_diagnostics_never_include_accessible_message_text():
    nodes = [
        _ax("root", "RootWebArea", "X", ("m1",), "https://x.com/i/chat/123?secret=x"),
        _ax("m1", "listitem", "Message from Alice", ("text",)),
        _ax("text", "StaticText", "private message body"),
    ]

    report = semantic_diagnostics(nodes)

    assert report["route"] == "/i/chat/123"
    assert report["roles"]["listitem"] == 1
    assert "private message body" not in json.dumps(report)


def test_live_shape_excludes_preview_rows_profile_cards_and_date_separators():
    nodes = [
        _ax("root", "RootWebArea", "X", ("preview-list", "timeline")),
        _ax(
            "preview-list", "listbox", "Conversations", ("preview-row",), parent="root"
        ),
        _ax(
            "preview-row", "listitem", children=("preview-link",), parent="preview-list"
        ),
        _ax(
            "preview-link",
            "link",
            "user avatar Alice 1d preview",
            ("preview-text",),
            "https://x.com/i/chat/1-2",
            parent="preview-row",
        ),
        _ax("preview-text", "StaticText", "preview", parent="preview-link"),
        _ax(
            "timeline",
            "generic",
            children=("profile", "date", "in", "out"),
            parent="root",
            bounds=[600, 0, 800, 900],
        ),
        _ax("profile", "listitem", children=("profile-link",), parent="timeline"),
        _ax("profile-link", "link", "View Profile", parent="profile"),
        _ax("date", "listitem", children=("date-text",), parent="timeline"),
        _ax("date-text", "StaticText", "Fri, Jul 24", parent="date"),
        _ax("in", "listitem", children=("in-text", "in-time"), parent="timeline"),
        _ax(
            "in-text", "StaticText", "incoming", parent="in", bounds=[640, 10, 120, 30]
        ),
        _ax("in-time", "StaticText", "8:33 PM", parent="in"),
        _ax("out", "listitem", children=("out-text", "out-time"), parent="timeline"),
        _ax(
            "out-text",
            "StaticText",
            "outgoing",
            parent="out",
            bounds=[1100, 50, 180, 30],
        ),
        _ax("out-time", "StaticText", "8:34 PM", parent="out"),
    ]

    messages = extract_messages_from_ax(nodes)

    assert [(m["text"], m["direction"]) for m in messages] == [
        ("incoming", "incoming"),
        ("outgoing", "outgoing"),
    ]
    assert [m["timestamp"] for m in messages] == ["8:33 PM", "8:34 PM"]
    assert {m["direction_source"] for m in messages} == {"layout-heuristic"}


@pytest.mark.asyncio
async def test_cdp_capture_annotates_ax_nodes_with_dom_snapshot_bounds():
    class FakeCDP:
        def __init__(self):
            self.detached = False

        async def send(self, method, _params=None):
            if method == "Accessibility.getFullAXTree":
                return {
                    "nodes": [
                        _ax("message", "StaticText", "private")
                        | {"backendDOMNodeId": 22}
                    ]
                }
            assert method == "DOMSnapshot.captureSnapshot"
            return {
                "documents": [
                    {
                        "nodes": {"backendNodeId": [11, 22]},
                        "layout": {"nodeIndex": [1], "bounds": [[10, 20, 30, 40]]},
                    }
                ]
            }

        async def detach(self):
            self.detached = True

    cdp = FakeCDP()

    class Context:
        async def new_cdp_session(self, _page):
            return cdp

    page = type("Page", (), {"context": Context()})()
    nodes = await capture_accessibility_tree(page)

    assert nodes[0]["_bounds"] == [10, 20, 30, 40]
    assert cdp.detached is True
