"""Browser-independent XChat reader using X's official ``chat-xdk`` SDK.

Unlike :mod:`twitter_mcp.xchat.database`, this backend receives encrypted
events directly from the paid X API.  The PIN unlocks this account's private
keys through Juicebox into the SDK's in-memory ``Chat`` object.  This module
never exports those keys, persists them, sends messages, or marks a thread
read.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from twitter_mcp.xchat.errors import XChatExtractionFailed, XChatUnavailable
from twitter_mcp.xchat.oauth import configured_access_token

_EVENT_FIELDS = [
    "conversation_id",
    "created_at",
    "encoded_event",
    "id",
    "sender_id",
]
_PUBLIC_KEY_FIELDS = [
    "identity_public_key_signature",
    "juicebox_config",
    "public_key",
    "public_key_version",
    "signing_public_key",
]


def _dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _items(value: Any) -> list[dict[str, Any]]:
    data = _dict(value).get("data")
    if data is None:
        data = getattr(value, "data", None)
    if not data:
        return []
    if not isinstance(data, list):
        data = [data]
    return [_dict(item) for item in data]


def _first_page(pages: Iterable[Any]) -> Any:
    try:
        return next(iter(pages))
    except StopIteration as exc:
        raise XChatExtractionFailed(
            "The X Chat API returned no response page."
        ) from exc


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if "T" in text:
        return text
    try:
        return (
            datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, TypeError, ValueError):
        return None


class ChatXdkReader:
    """Read and decrypt XChat via OAuth2 + Juicebox, with no browser process."""

    def __init__(
        self,
        access_token: str,
        pin: str,
        *,
        client: Any | None = None,
        chat_factory: Callable[[str], Any] | None = None,
    ) -> None:
        if not access_token:
            raise XChatUnavailable("XCHAT_API_ACCESS_TOKEN is required for chatxdk.")
        if not pin:
            raise XChatUnavailable("XCHAT_PIN is required to unlock chatxdk keys.")
        if client is None or chat_factory is None:
            try:
                from chat_xdk import Chat
                from xdk import Client
            except ImportError as exc:
                raise XChatUnavailable(
                    "Install the paid API backend with `pip install twikit-mcp[xchat-api]`."
                ) from exc
            client = client or Client(access_token=access_token)
            chat_factory = chat_factory or Chat
        self.client = client
        self._chat_factory = chat_factory
        self._pin = pin
        self._chat: Any | None = None
        self._owner_id: str | None = None
        self._usernames: dict[str, str] = {}

    @property
    def owner_id(self) -> str:
        self._connect()
        return str(self._owner_id)

    def _public_keys(self, user_id: str) -> list[dict[str, Any]]:
        response = self.client.users.get_public_key(
            user_id, public_key_fields=_PUBLIC_KEY_FIELDS
        )
        return _items(response)

    def _connect(self) -> None:
        if self._chat is not None:
            return
        response = self.client.users.get_me()
        response_dict = _dict(response)
        # Some generated XDK responses only expose `.data`; accept both shapes
        # without making a second billable request.
        user = _dict(response_dict.get("data") or getattr(response, "data", None))
        owner_id = str(user.get("id") or "")
        if not owner_id:
            raise XChatUnavailable("The X API did not identify the authenticated user.")
        if user.get("username"):
            self._usernames[owner_id] = str(user["username"])
        keys = self._public_keys(owner_id)
        usable = [item for item in keys if item.get("juicebox_config")]
        if not usable:
            raise XChatUnavailable(
                "No Juicebox-backed XChat key is registered for this user."
            )
        latest = max(usable, key=lambda item: int(item.get("public_key_version") or 0))
        chat = self._chat_factory(json.dumps(latest["juicebox_config"]))
        chat.unlock(self._pin)
        chat.set_identity(owner_id, str(latest.get("public_key_version") or "1"))
        chat.set_cache_keys(True)
        self._owner_id = owner_id
        self._chat = chat

    def status(self) -> dict[str, Any]:
        self._connect()
        return {
            "state": "ready",
            "source": "chat_xdk_api",
            "detail": "XChat keys unlocked in memory; no browser is required.",
            "paid_api": True,
        }

    def list_conversations(
        self, limit: int = 50, unread_only: bool = False
    ) -> list[dict[str, Any]]:
        self._connect()
        if unread_only:
            raise XChatUnavailable(
                "The chatxdk API reader cannot filter unread state without marking reads."
            )
        limit = max(1, min(int(limit), 100))
        page = _first_page(
            self.client.chat.get_conversations(
                max_results=limit,
                chat_conversation_fields=["group_name", "id", "type", "updated_at"],
                expansions=["participant_ids"],
                user_fields=["id", "name", "username"],
            )
        )
        page_dict = _dict(page)
        includes = _dict(page_dict.get("includes"))
        for user in includes.get("users") or []:
            item = _dict(user)
            if item.get("id") and item.get("username"):
                self._usernames[str(item["id"])] = str(item["username"])
        rows = []
        for item in _items(page)[:limit]:
            conversation_id = str(item.get("id") or "")
            direct_parts = conversation_id.replace(":", "-").split("-")
            if len(direct_parts) == 2 and direct_parts[0] == direct_parts[1]:
                # X includes an account-local control stream containing settings
                # and key events. It is not a user-visible conversation.
                continue
            participant_ids = [str(v) for v in item.get("participant_ids") or []]
            other = next((v for v in participant_ids if v != self.owner_id), None)
            username = self._usernames.get(other or "")
            rows.append(
                {
                    "conversation_id": conversation_id,
                    "name": item.get("group_name")
                    or username
                    or other
                    or conversation_id,
                    "screen_name": username,
                    "preview": "[fetch history to decrypt messages]",
                    "timestamp": _timestamp(item.get("updated_at")),
                    "encrypted": True,
                    "unread": None,
                }
            )
        return rows

    def _signing_keys(self, raw: list[dict[str, Any]]) -> list[dict[str, str]]:
        signing: list[dict[str, str]] = []
        user_ids = {self.owner_id} | {
            str(item["sender_id"]) for item in raw if item.get("sender_id")
        }
        for user_id in user_ids:
            for key in self._public_keys(user_id):
                signing.append(
                    {
                        "user_id": user_id,
                        "public_key_version": str(key.get("public_key_version") or ""),
                        "public_key": str(key.get("signing_public_key") or ""),
                        "identity_public_key": str(key.get("public_key") or ""),
                        "identity_public_key_signature": str(
                            key.get("identity_public_key_signature") or ""
                        ),
                    }
                )
        return signing

    def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        if not conversation_id:
            raise XChatExtractionFailed("conversation_id must be non-empty.")
        self._connect()
        limit = max(1, min(int(limit), 100))
        page_size = min(50, max(limit * 2, 10))
        pages = iter(
            self.client.chat.get_conversation_events(
                conversation_id.replace(":", "-"),
                max_results=page_size,
                chat_message_event_fields=_EVENT_FIELDS,
            )
        )
        raw: list[dict[str, Any]] = []
        result: dict[str, Any] = {}
        for _ in range(3):
            try:
                raw.extend(_items(next(pages)))
            except StopIteration:
                break
            if len(raw) > 100:
                raw = raw[:100]
            encoded = [
                str(item["encoded_event"]) for item in raw if item.get("encoded_event")
            ]
            if encoded:
                result = _dict(
                    self._chat.decrypt_events(encoded, self._signing_keys(raw))
                )
                decrypted_messages = [
                    wrapped
                    for wrapped in result.get("messages") or []
                    if _dict(_dict(wrapped).get("event")).get("type") == "Message"
                ]
                if len(decrypted_messages) >= limit or len(raw) >= 100:
                    break
        if not raw or not any(item.get("encoded_event") for item in raw):
            raise XChatExtractionFailed("The X Chat API returned no encrypted events.")
        messages = []
        for wrapped in result.get("messages") or []:
            event = _dict(_dict(wrapped).get("event"))
            if event.get("type") != "Message":
                continue
            content = _dict(event.get("content"))
            text = str(content.get("text") or "").strip()
            if not text:
                content_type = str(content.get("content_type") or "unknown").lower()
                text = f"[unsupported message type: {content_type}]"
            sender_id = str(event.get("sender_id") or "") or None
            messages.append(
                {
                    "text": text,
                    "timestamp": _timestamp(
                        event.get("created_at")
                        or event.get("created_at_msec")
                        or event.get("timestamp_msec")
                    ),
                    "direction": (
                        "outgoing" if sender_id == self.owner_id else "incoming"
                    ),
                    "direction_source": "chatxdk-authenticated-user",
                    "sender_id": sender_id,
                    "sender_screen_name": self._usernames.get(sender_id or ""),
                    "sequence_number": str(event.get("sequence_id") or "") or None,
                    "has_attachment": bool(content.get("attachments")),
                    "attachment_types": None,
                }
            )

        def sequence(item: dict[str, Any]) -> tuple[int, str]:
            value = str(item.get("sequence_number") or "")
            return (int(value), value) if value.isdigit() else (0, value)

        messages.sort(key=sequence)
        if not messages:
            errors = result.get("errors") or {}
            raise XChatExtractionFailed(
                "chat-xdk could not decrypt messages from the returned event page"
                + (f" ({len(errors)} SDK errors)." if errors else ".")
            )
        return messages[-limit:]

    def doctor(self) -> dict[str, Any]:
        status = self.status()
        return {**status, "sdk": "chatxdk", "key_storage": "juicebox-memory-only"}


_configured_instance: ChatXdkReader | None = None


def configured_chatxdk(settings: Any) -> ChatXdkReader | None:
    """Resolve the paid backend only when explicitly selected."""
    if settings.backend != "chatxdk":
        return None
    global _configured_instance
    if _configured_instance is None:
        _configured_instance = ChatXdkReader(
            configured_access_token(settings), settings.pin or ""
        )
    return _configured_instance


__all__ = ["ChatXdkReader", "configured_chatxdk"]
