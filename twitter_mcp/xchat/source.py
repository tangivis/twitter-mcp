"""Resolve the explicitly selected XChat read source."""

from __future__ import annotations

from typing import Any

from twitter_mcp.xchat.chatxdk import configured_chatxdk
from twitter_mcp.xchat.database import configured_database


def configured_reader(settings: Any) -> Any | None:
    """Prefer chat-xdk only when selected; otherwise retain local behavior."""
    api = configured_chatxdk(settings)
    return api if api is not None else configured_database(settings)


__all__ = ["configured_reader"]
