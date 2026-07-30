"""Read-only access to X's already-decrypted local XChat SQLite store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from twitter_mcp.xchat.database import XChatDatabase
from twitter_mcp.xchat.errors import XChatExtractionFailed, XChatUnavailable


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "chat.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE dm_conversation (
            conversation_id TEXT PRIMARY KEY,
            custom_title TEXT,
            last_read_sequence_number INTEGER,
            marked_unread_by_me INTEGER,
            deleted INTEGER
        );
        CREATE TABLE dm_entry (
            entry_id TEXT PRIMARY KEY,
            conversation_id TEXT,
            sequence_number INTEGER,
            timestamp INTEGER,
            entry_type TEXT,
            sender_id INTEGER,
            message_status TEXT,
            plain_text TEXT,
            has_attachment INTEGER,
            affects_sort_order INTEGER,
            sender_is_owner INTEGER,
            attachment_types TEXT
        );
        CREATE TABLE dm_user (
            id INTEGER PRIMARY KEY,
            screen_name TEXT
        );
        CREATE TABLE dm_group_participant (
            conversation_id TEXT,
            user_id INTEGER,
            is_current_member INTEGER
        );
        CREATE TABLE dm_key_material (tag TEXT PRIMARY KEY, bytes BLOB);
        """
    )
    con.executemany(
        "INSERT INTO dm_user(id, screen_name) VALUES (?, ?)",
        [(10, "owner"), (20, "alice"), (30, "bob")],
    )
    con.executemany(
        "INSERT INTO dm_conversation VALUES (?, ?, ?, ?, ?)",
        [
            ("10:20", None, 1, 0, 0),
            ("g-team", "Team Chat", 4, 0, 0),
            ("10:30", None, 8, 1, 0),
            ("deleted", None, 0, 0, 1),
        ],
    )
    con.executemany(
        "INSERT INTO dm_entry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "m1",
                "10:20",
                1,
                1_700_000_000_000,
                "message",
                20,
                "Sent",
                "hello",
                0,
                1,
                0,
                None,
            ),
            (
                "m2",
                "10:20",
                2,
                1_700_000_001_000,
                "message",
                10,
                "Sent",
                "hi",
                0,
                1,
                1,
                None,
            ),
            (
                "m3",
                "g-team",
                5,
                1_700_000_002_000,
                "message",
                30,
                "Sent",
                "group update",
                0,
                1,
                0,
                None,
            ),
            (
                "m4",
                "10:30",
                8,
                1_700_000_003_000,
                "message",
                10,
                "Sent",
                "",
                1,
                1,
                1,
                "link",
            ),
            (
                "info",
                "10:20",
                3,
                1_700_000_004_000,
                "informational",
                10,
                None,
                "joined",
                0,
                0,
                1,
                None,
            ),
        ],
    )
    con.executemany(
        "INSERT INTO dm_group_participant VALUES (?, ?, ?)",
        [("g-team", 10, 1), ("g-team", 30, 1)],
    )
    con.execute("INSERT INTO dm_key_material VALUES ('do-not-expose-tag', x'0102')")
    con.commit()
    con.close()
    return path


def test_status_validates_expected_schema_without_exposing_keys(tmp_path):
    db = XChatDatabase(_database(tmp_path))

    status = db.status()

    assert status["state"] == "ready"
    assert status["source"] == "local_database"
    assert status["conversation_count"] == 3
    assert "do-not-expose-tag" not in str(status)


def test_list_conversations_maps_names_unread_and_attachment_preview(tmp_path):
    rows = XChatDatabase(_database(tmp_path)).list_conversations()

    assert [row["conversation_id"] for row in rows] == [
        "10:30",
        "g-team",
        "10:20",
    ]
    assert rows[0]["timestamp"] == "2023-11-14T22:13:23.000Z"
    assert rows[0]["name"] == "bob"
    assert rows[0]["preview"] == "[link attachment]"
    assert rows[0]["unread"] is True
    assert rows[1]["name"] == "Team Chat"
    assert rows[1]["screen_name"] is None
    assert rows[1]["preview"] == "group update"
    assert rows[1]["unread"] is True
    assert rows[2]["name"] == "alice"
    assert rows[2]["unread"] is True
    assert all(row["encrypted"] is True for row in rows)


def test_list_conversations_can_filter_unread_and_limit(tmp_path):
    rows = XChatDatabase(_database(tmp_path)).list_conversations(
        limit=1, unread_only=True
    )
    assert [row["conversation_id"] for row in rows] == ["10:30"]


def test_history_is_oldest_first_and_uses_database_owner_flag(tmp_path):
    rows = XChatDatabase(_database(tmp_path)).get_history("10:20", limit=10)

    assert [(row["text"], row["direction"]) for row in rows] == [
        ("hello", "incoming"),
        ("hi", "outgoing"),
    ]
    assert rows[0]["sender_screen_name"] == "alice"
    assert rows[0]["direction_source"] == "database-owner-flag"
    assert rows[0]["timestamp"].endswith("Z")


def test_history_uses_attachment_placeholder_and_newest_limit(tmp_path):
    rows = XChatDatabase(_database(tmp_path)).get_history("10:30", limit=1)
    assert rows[0]["text"] == "[link attachment]"
    assert rows[0]["has_attachment"] is True


def test_missing_database_is_unavailable(tmp_path):
    with pytest.raises(XChatUnavailable, match="does not exist"):
        XChatDatabase(tmp_path / "missing.db").status()


def test_wrong_schema_is_reported_without_dumping_contents(tmp_path):
    path = tmp_path / "wrong.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE unrelated(secret TEXT)")
    con.execute("INSERT INTO unrelated VALUES ('do-not-log')")
    con.commit()
    con.close()

    with pytest.raises(XChatExtractionFailed, match="required XChat tables") as exc:
        XChatDatabase(path).status()
    assert "do-not-log" not in str(exc.value)


def test_doctor_is_content_free(tmp_path):
    report = XChatDatabase(_database(tmp_path)).doctor()
    assert report["message_count"] == 5
    assert report["key_material_rows"] == 1
    assert "group update" not in str(report)
