"""Read XChat plaintext from X's local SQLite store without browser control.

X's web client writes its already-decrypted conversation state to an SQLite
database in Chromium's origin-private filesystem. This module opens that file
with SQLite's read-only + immutable URI flags and queries only metadata and the
`plain_text` projection; it never reads or exports `dm_key_material.bytes`.

The source browser remains responsible for authentication, E2EE decryption, and
sync. This reader is deliberately incapable of sending messages or mutating read
state.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from twitter_mcp.xchat.errors import XChatExtractionFailed, XChatUnavailable

_REQUIRED_TABLES = frozenset(
    {"dm_conversation", "dm_entry", "dm_user", "dm_key_material"}
)


def _timestamp(value: Any) -> str | None:
    try:
        return (
            datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, TypeError, ValueError):
        return None


def _attachment_text(text: Any, has_attachment: Any, types: Any) -> str:
    clean = str(text or "").strip()
    if clean:
        return clean
    if has_attachment:
        kind = str(types or "attachment").strip() or "attachment"
        return f"[{kind} attachment]" if kind != "attachment" else "[attachment]"
    return "[message]"


class XChatDatabase:
    """A strictly read-only view over X's locally decrypted XChat database."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().resolve()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if not self.path.is_file():
            raise XChatUnavailable(
                f"Configured XChat database does not exist: {self.path}"
            )
        uri = f"file:{quote(str(self.path), safe='/')}?mode=ro&immutable=1"
        try:
            con = sqlite3.connect(uri, uri=True)
            con.row_factory = sqlite3.Row
            self._validate(con)
            yield con
        except XChatExtractionFailed:
            raise
        except sqlite3.DatabaseError as exc:
            raise XChatExtractionFailed(
                f"Could not read the local XChat database: {type(exc).__name__}."
            ) from exc
        finally:
            if "con" in locals():
                con.close()

    @staticmethod
    def _validate(con: sqlite3.Connection) -> None:
        tables = {
            str(row[0])
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise XChatExtractionFailed(
                "The configured database is missing required XChat tables: "
                + ", ".join(missing)
            )

    @staticmethod
    def _owner_id(con: sqlite3.Connection) -> str | None:
        row = con.execute(
            """
            SELECT sender_id
            FROM dm_entry
            WHERE sender_is_owner = 1 AND sender_id IS NOT NULL
            GROUP BY sender_id
            ORDER BY COUNT(*) DESC
            LIMIT 1
            """
        ).fetchone()
        return str(row[0]) if row else None

    @staticmethod
    def _screen_names(con: sqlite3.Connection, user_ids: set[str]) -> dict[str, str]:
        numeric = [int(value) for value in user_ids if value.isdigit()]
        if not numeric:
            return {}
        placeholders = ",".join("?" for _ in numeric)
        return {
            str(row["id"]): str(row["screen_name"])
            for row in con.execute(
                f"SELECT id, screen_name FROM dm_user "
                f"WHERE id IN ({placeholders}) AND screen_name IS NOT NULL",
                numeric,
            )
        }

    @staticmethod
    def _direct_other_id(conversation_id: str, owner_id: str | None) -> str | None:
        if conversation_id.startswith("g"):
            return None
        parts = [part for part in conversation_id.replace("-", ":").split(":") if part]
        if len(parts) != 2:
            return None
        if owner_id in parts:
            return parts[1] if parts[0] == owner_id else parts[0]
        return parts[-1]

    def status(self) -> dict[str, Any]:
        with self._connect() as con:
            conversation_count = int(
                con.execute(
                    "SELECT COUNT(*) FROM dm_conversation WHERE COALESCE(deleted, 0) = 0"
                ).fetchone()[0]
            )
        return {
            "state": "ready",
            "source": "local_database",
            "database_path": str(self.path),
            "database_exists": True,
            "conversation_count": conversation_count,
            "last_updated": _timestamp(self.path.stat().st_mtime_ns // 1_000_000),
            "detail": "Encrypted messages are readable from X's local decrypted store.",
        }

    def list_conversations(
        self, limit: int = 50, unread_only: bool = False
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as con:
            owner_id = self._owner_id(con)
            rows = list(
                con.execute(
                    """
                    WITH latest AS (
                        SELECT e.*,
                               ROW_NUMBER() OVER (
                                   PARTITION BY conversation_id
                                   ORDER BY timestamp DESC, sequence_number DESC
                               ) AS rank
                        FROM dm_entry e
                        WHERE entry_type = 'message'
                          AND COALESCE(affects_sort_order, 1) = 1
                    )
                    SELECT c.conversation_id, c.custom_title,
                           c.last_read_sequence_number, c.marked_unread_by_me,
                           l.sequence_number, l.timestamp, l.sender_id,
                           l.sender_is_owner, l.plain_text, l.has_attachment,
                           l.attachment_types
                    FROM dm_conversation c
                    JOIN latest l
                      ON l.conversation_id = c.conversation_id AND l.rank = 1
                    WHERE COALESCE(c.deleted, 0) = 0
                    ORDER BY l.timestamp DESC, l.sequence_number DESC
                    """
                )
            )
            direct_ids = {
                other
                for row in rows
                if (
                    other := self._direct_other_id(
                        str(row["conversation_id"]), owner_id
                    )
                )
            }
            names = self._screen_names(con, direct_ids)

        conversations: list[dict[str, Any]] = []
        for row in rows:
            conversation_id = str(row["conversation_id"])
            other_id = self._direct_other_id(conversation_id, owner_id)
            screen_name = names.get(other_id or "")
            title = str(row["custom_title"] or "").strip()
            unread = bool(row["marked_unread_by_me"]) or (
                row["last_read_sequence_number"] is None
                or int(row["sequence_number"]) > int(row["last_read_sequence_number"])
            )
            if unread_only and not unread:
                continue
            conversations.append(
                {
                    "conversation_id": conversation_id,
                    "name": title or screen_name or other_id or conversation_id,
                    "screen_name": screen_name,
                    "preview": _attachment_text(
                        row["plain_text"],
                        row["has_attachment"],
                        row["attachment_types"],
                    ),
                    "timestamp": _timestamp(row["timestamp"]),
                    "encrypted": True,
                    "unread": unread,
                }
            )
            if len(conversations) >= limit:
                break
        return conversations

    def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        if not conversation_id:
            raise XChatExtractionFailed("conversation_id must be non-empty.")
        limit = max(1, min(int(limit), 500))
        with self._connect() as con:
            rows = list(
                con.execute(
                    """
                    SELECT recent.*, u.screen_name
                    FROM (
                        SELECT entry_id, conversation_id, sequence_number,
                               timestamp, sender_id, sender_is_owner, plain_text,
                               has_attachment, attachment_types
                        FROM dm_entry
                        WHERE conversation_id = ? AND entry_type = 'message'
                          AND COALESCE(affects_sort_order, 1) = 1
                        ORDER BY timestamp DESC, sequence_number DESC
                        LIMIT ?
                    ) AS recent
                    LEFT JOIN dm_user u ON u.id = recent.sender_id
                    ORDER BY recent.timestamp ASC, recent.sequence_number ASC
                    """,
                    (conversation_id, limit),
                )
            )
        if not rows:
            raise XChatExtractionFailed(
                f"No local messages found for conversation {conversation_id}."
            )
        return [
            {
                "text": _attachment_text(
                    row["plain_text"], row["has_attachment"], row["attachment_types"]
                ),
                "timestamp": _timestamp(row["timestamp"]),
                "direction": "outgoing" if row["sender_is_owner"] else "incoming",
                "direction_source": "database-owner-flag",
                "sender_id": str(row["sender_id"]) if row["sender_id"] else None,
                "sender_screen_name": row["screen_name"],
                "sequence_number": str(row["sequence_number"]),
                "has_attachment": bool(row["has_attachment"]),
                "attachment_types": row["attachment_types"],
            }
            for row in rows
        ]

    def doctor(self) -> dict[str, Any]:
        with self._connect() as con:
            table_count = int(
                con.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                ).fetchone()[0]
            )
            conversation_count = int(
                con.execute("SELECT COUNT(*) FROM dm_conversation").fetchone()[0]
            )
            message_count = int(
                con.execute("SELECT COUNT(*) FROM dm_entry").fetchone()[0]
            )
            key_material_rows = int(
                con.execute("SELECT COUNT(*) FROM dm_key_material").fetchone()[0]
            )
        return {
            "source": "local_database",
            "database_path": str(self.path),
            "database_size": self.path.stat().st_size,
            "last_updated": _timestamp(self.path.stat().st_mtime_ns // 1_000_000),
            "table_count": table_count,
            "conversation_count": conversation_count,
            "message_count": message_count,
            "key_material_rows": key_material_rows,
        }


def configured_database(settings: Any) -> XChatDatabase | None:
    """Return the explicit or discovered database configured by settings."""
    from twitter_mcp.xchat.discovery import resolve_xchat_database_path

    path = resolve_xchat_database_path(
        settings.database_path,
        settings.database_browser,
        settings.database_profile,
    )
    return XChatDatabase(path) if path else None


__all__ = ["XChatDatabase", "configured_database"]
