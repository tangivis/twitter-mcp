"""Official chat-xdk browser-independent reader."""

from __future__ import annotations

import pytest

from twitter_mcp.xchat import chatxdk
from twitter_mcp.xchat.chatxdk import ChatXdkReader, configured_chatxdk
from twitter_mcp.xchat.config import XChatSettings
from twitter_mcp.xchat.errors import XChatExtractionFailed, XChatUnavailable


class FakeUsers:
    def __init__(self):
        self.me_calls = 0

    def get_me(self):
        self.me_calls += 1
        return {"data": {"id": "10", "username": "owner"}}

    def get_public_key(self, user_id, public_key_fields=None):
        assert public_key_fields
        return {
            "data": [
                {
                    "public_key_version": "2",
                    "public_key": f"identity-{user_id}",
                    "signing_public_key": f"signing-{user_id}",
                    "identity_public_key_signature": f"signature-{user_id}",
                    "juicebox_config": {"realm": "safe-test-config"},
                }
            ]
        }


class FakeChatApi:
    def get_conversations(self, **kwargs):
        assert kwargs["max_results"] == 5
        yield {
            "data": [
                {
                    "id": "10:20",
                    "participant_ids": ["10", "20"],
                    "updated_at": "2026-07-26T00:00:00Z",
                },
                {
                    "id": "10-10",
                    "participant_ids": ["10"],
                },
            ],
            "includes": {"users": [{"id": "20", "username": "alice"}]},
        }

    def get_conversation_events(self, conversation_id, **kwargs):
        assert conversation_id == "10-20"
        assert "encoded_event" in kwargs["chat_message_event_fields"]
        yield {
            "data": [
                {"encoded_event": "incoming", "sender_id": "20"},
                {"encoded_event": "outgoing", "sender_id": "10"},
            ]
        }


class FakeClient:
    def __init__(self):
        self.users = FakeUsers()
        self.chat = FakeChatApi()


class FakeChat:
    def __init__(self, config):
        assert "safe-test-config" in config
        self.pin = None
        self.identity = None
        self.cache = False

    def unlock(self, pin):
        self.pin = pin

    def set_identity(self, user_id, version):
        self.identity = (user_id, version)

    def set_cache_keys(self, enabled):
        self.cache = enabled

    def decrypt_events(self, events, signing):
        assert events == ["incoming", "outgoing"]
        assert {item["user_id"] for item in signing} == {"10", "20"}
        return {
            "messages": [
                {
                    "event": {
                        "type": "Message",
                        "sender_id": "10",
                        "sequence_id": "10",
                        "timestamp_msec": 1_700_000_001_000,
                        "content": {"text": "reply"},
                    }
                },
                {
                    "event": {
                        "type": "Message",
                        "sender_id": "20",
                        "sequence_id": "2",
                        "timestamp_msec": 1_700_000_000_000,
                        "content": {"text": "hello"},
                    }
                },
            ],
            "errors": {},
        }


def reader():
    return ChatXdkReader("token", "1234", client=FakeClient(), chat_factory=FakeChat)


def test_status_unlocks_once_and_never_exposes_secrets():
    instance = reader()

    first = instance.status()
    second = instance.status()

    assert first["source"] == "chat_xdk_api"
    assert first["paid_api"] is True
    assert "token" not in str(first)
    assert "1234" not in str(first)
    assert instance.client.users.me_calls == 1
    assert second == first


def test_list_conversations_maps_expanded_username_without_decrypting():
    rows = reader().list_conversations(limit=5)

    assert rows == [
        {
            "conversation_id": "10:20",
            "name": "alice",
            "screen_name": "alice",
            "preview": "[fetch history to decrypt messages]",
            "timestamp": "2026-07-26T00:00:00Z",
            "encrypted": True,
            "unread": None,
        }
    ]


def test_history_is_oldest_first_and_direction_uses_authenticated_user():
    rows = reader().get_history("10:20", limit=10)

    assert [(item["text"], item["direction"]) for item in rows] == [
        ("hello", "incoming"),
        ("reply", "outgoing"),
    ]
    assert rows[0]["timestamp"] == "2023-11-14T22:13:20.000Z"
    assert rows[0]["direction_source"] == "chatxdk-authenticated-user"


def test_configuration_requires_explicit_backend_and_both_secrets(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("twitter_mcp.xchat.chatxdk._configured_instance", None)
    local = XChatSettings(profile_dir=tmp_path)
    assert configured_chatxdk(local) is None

    api = XChatSettings(profile_dir=tmp_path, backend="chatxdk")
    with pytest.raises(XChatUnavailable, match="ACCESS_TOKEN"):
        configured_chatxdk(api)

    api.api_access_token = "token"
    with pytest.raises(XChatUnavailable, match="XCHAT_PIN"):
        configured_chatxdk(api)


def test_unread_filter_is_refused_not_guessed():
    with pytest.raises(XChatUnavailable, match="cannot filter unread"):
        reader().list_conversations(unread_only=True)


def test_empty_event_page_and_empty_decryption_are_honest_errors():
    instance = reader()
    instance.client.chat.get_conversation_events = lambda *a, **k: iter([{"data": []}])
    with pytest.raises(XChatExtractionFailed, match="no encrypted events"):
        instance.get_history("10:20")


def test_history_uses_created_at_msec_and_labels_unsupported_messages():
    instance = reader()

    def decrypt(events, signing):
        return {
            "messages": [
                {
                    "event": {
                        "type": "Message",
                        "sender_id": "20",
                        "sequence_id": "1",
                        "created_at_msec": 1_700_000_000_000,
                        "content": {"content_type": "Unknown"},
                    }
                }
            ]
        }

    instance._chat = FakeChat("safe-test-config")
    instance._owner_id = "10"
    instance._chat.decrypt_events = decrypt
    rows = instance.get_history("10:20", limit=1)
    assert rows[0]["timestamp"] == "2023-11-14T22:13:20.000Z"
    assert rows[0]["text"] == "[unsupported message type: unknown]"


def test_sdk_shape_helpers_accept_models_attributes_and_invalid_values():
    class Model:
        def model_dump(self):
            return {"data": {"id": "one"}}

    class AttributeResponse:
        data = {"id": "two"}

    assert chatxdk._dict(None) == {}
    assert chatxdk._dict(Model()) == {"data": {"id": "one"}}
    assert chatxdk._dict(object()) == {}
    assert chatxdk._items(Model()) == [{"id": "one"}]
    assert chatxdk._items(AttributeResponse()) == [{"id": "two"}]
    assert chatxdk._items({"data": None}) == []
    assert chatxdk._timestamp(None) is None
    assert chatxdk._timestamp("not-a-timestamp") is None
    with pytest.raises(XChatExtractionFailed, match="no response page"):
        chatxdk._first_page([])


def test_connect_reports_missing_identity_and_missing_juicebox_key():
    missing_identity = reader()
    missing_identity.client.users.get_me = lambda: {"data": {}}
    with pytest.raises(XChatUnavailable, match="identify"):
        missing_identity.status()

    missing_key = reader()
    missing_key.client.users.get_public_key = lambda *a, **k: {
        "data": [{"public_key_version": "1"}]
    }
    with pytest.raises(XChatUnavailable, match="No Juicebox"):
        missing_key.status()


def test_history_validates_id_and_reports_decryption_errors():
    instance = reader()
    with pytest.raises(XChatExtractionFailed, match="non-empty"):
        instance.get_history("")

    instance._chat = FakeChat("safe-test-config")
    instance._owner_id = "10"
    instance._chat.decrypt_events = lambda *a, **k: {
        "messages": [{"event": {"type": "Reaction"}}],
        "errors": {"bad": "event"},
    }
    with pytest.raises(XChatExtractionFailed, match="1 SDK errors"):
        instance.get_history("10:20")


def test_history_bounds_raw_events_and_doctor_reports_memory_only_keys():
    instance = reader()
    events = [
        {"encoded_event": f"event-{index}", "sender_id": "20"} for index in range(101)
    ]
    instance.client.chat.get_conversation_events = lambda *a, **k: iter(
        [{"data": events}]
    )
    instance._chat = FakeChat("safe-test-config")
    instance._owner_id = "10"
    instance._chat.decrypt_events = lambda encoded, signing: {
        "messages": [
            {
                "event": {
                    "type": "Message",
                    "sender_id": "20",
                    "sequence_id": "plain-sequence",
                    "created_at": "2026-07-26T00:00:00Z",
                    "content": {"text": "bounded", "attachments": ["file"]},
                }
            }
        ]
    }

    rows = instance.get_history("10:20", limit=100)
    assert rows[0]["text"] == "bounded"
    assert rows[0]["has_attachment"] is True
    assert instance.doctor()["key_storage"] == "juicebox-memory-only"


def test_conversation_listing_reports_empty_api_iterator():
    instance = reader()
    instance.client.chat.get_conversations = lambda **kwargs: iter([])
    with pytest.raises(XChatExtractionFailed, match="no response page"):
        instance.list_conversations()
