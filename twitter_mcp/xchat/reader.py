"""Turning the decrypted X web client's DOM into structured data.

Everything here is deliberately free of Playwright imports. The primary path
reads Chromium's accessibility tree over CDP and interprets plain dictionaries,
so the semantic contract can be tested without launching a browser. The older
`evaluate()` scripts remain only as safety fallbacks for fakes/engines without
the required CDP surface.

On UI drift: X ships changes regularly, and this package reads the rendered
client rather than an API, so drift is a *when*, not an *if*. The primary path
uses roles, accessible names, resolved link URLs, and DOMSnapshot bounds.
Legacy selectors are retained as a conservative compatibility lane:

1. Every legacy logical element has a list of candidate selectors, most-stable
   first. `data-testid` attributes lead; structural fallbacks trail.
2. `XCHAT_SELECTORS=/path/to.json` overrides any subset at runtime, so a break
   is a config edit rather than a release. `twikit-mcp xchat doctor` reports
   content-free semantic counts and the current route.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

# A logged-out visitor is served a login sheet that contains an account-password
# field. Typing the chat PIN into it would submit a secret to the wrong form and
# register a failed login against the account, so anything that matches this is
# never treated as a PIN field — see `LOGIN_PASSWORD_SELECTOR` in session.py.
LOGIN_PASSWORD_ATTRS = ('[name="password"]', '[autocomplete="current-password"]')

_CONVERSATION_PATH = re.compile(
    r"^/(?:i/chat|messages)/(?P<id>g?[0-9]+(?:-[0-9]+)*)/?$"
)
_HANDLE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{1,15})\b")
_MESSAGE_ROLES = frozenset({"article", "listitem"})
_CLOCK_TEXT = re.compile(r"^\d{1,2}:\d{2}\s*(?:AM|PM)$", re.IGNORECASE)
_RELATIVE_TIME = re.compile(r"^\d+\s*(?:s|m|h|d|w|mo|y)$", re.IGNORECASE)
_DATE_TEXT = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}$",
    re.IGNORECASE,
)

# Ordered candidates per logical element; first match wins at query time.
DEFAULT_SELECTORS: dict[str, list[str]] = {
    # Shown when the profile is not (or no longer) logged in. X moved this flow
    # to `/i/jf/onboarding/web?...&mode=login`, whose sheet carries none of the
    # old login test ids — hence the provider buttons and the username field,
    # which are what that sheet actually renders.
    "login_marker": [
        '[data-testid="loginButton"]',
        '[data-testid="login"]',
        '[data-testid="google_sign_in_container"]',
        '[data-testid="apple_sign_in_button"]',
        'input[name="text"][autocomplete="username"]',
        'div[role="dialog"] input[name="password"]',
        'a[href="/login"]',
    ],
    # The chat-PIN gate. X labels this differently across surfaces, so match on
    # the input's semantics as well as on any container test id.
    "pin_dialog": [
        '[data-testid="xChatPinPrompt"]',
        '[data-testid="EnterPin"]',
        'div[role="dialog"]:has(input[autocomplete="one-time-code"])',
    ],
    # NOTE: every candidate here must be incapable of matching the login sheet's
    # password field. The generic dialog fallback is therefore negated on the
    # account-password attributes rather than left open.
    "pin_input": [
        '[data-testid="xChatPinInput"]',
        'input[autocomplete="one-time-code"]',
        'div[role="dialog"] input[type="password"]'
        ':not([name="password"]):not([autocomplete="current-password"])',
    ],
    "pin_submit": [
        '[data-testid="xChatPinSubmit"]',
        'div[role="dialog"] [data-testid="confirmationSheetConfirm"]',
        'div[role="dialog"] button[type="submit"]',
    ],
    # Rejected-PIN feedback, so a wrong value fails loudly instead of hanging.
    "pin_error": [
        '[data-testid="xChatPinError"]',
        'div[role="dialog"] [role="alert"]',
    ],
    # The inbox itself — presence of this with no PIN gate means "ready".
    "conversation_list": [
        '[data-testid="conversation"]',
        'section[aria-label*="Timeline"] [data-testid="cellInnerDiv"]',
    ],
    "conversation": [
        '[data-testid="conversation"]',
    ],
    "message": [
        '[data-testid="messageEntry"]',
    ],
    "message_text": [
        '[data-testid="tweetText"]',
    ],
    # Container that actually scrolls when paging back through history.
    "message_scroller": [
        'div[data-testid="DmScrollerContainer"]',
        'section[role="region"]',
    ],
}


def load_selectors(path: Path | None = None) -> dict[str, list[str]]:
    """Return the default selector map, with any overrides from `path` merged in.

    Merging is per-key replacement, not append: an override exists because the
    defaults are wrong for that key, so keeping them as fallbacks would just
    re-match the stale element. Unknown keys are ignored rather than rejected —
    a forward-compatible override file should not break an older install.
    """
    selectors = {key: list(value) for key, value in DEFAULT_SELECTORS.items()}
    if path is None:
        return selectors
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read selector overrides at {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Selector overrides at {path} must be a JSON object.")
    for key, value in raw.items():
        if key not in selectors:
            continue
        if isinstance(value, str):
            selectors[key] = [value]
        elif isinstance(value, list) and all(isinstance(v, str) for v in value):
            selectors[key] = list(value)
        else:
            raise ValueError(f"Selector override `{key}` must be a string or list.")
    return selectors


# ── browser-side extraction ────────────────────────────
#
# These run inside the page. They take the resolved selector lists so the
# override mechanism reaches the DOM walk too, and they return plain JSON —
# no element handles, so nothing has to be disposed on the Python side.

EXTRACT_CONVERSATIONS_JS = """
(sel) => {
  const pick = (root, cands) => {
    for (const c of cands) { const el = root.querySelector(c); if (el) return el; }
    return null;
  };
  const all = (cands) => {
    for (const c of cands) {
      const els = document.querySelectorAll(c);
      if (els.length) return Array.from(els);
    }
    return [];
  };
  return all(sel.conversation).map((row) => {
    const link = row.querySelector('a[href*="/messages/"]');
    const href = link ? link.getAttribute('href') : null;
    const id = href ? href.split('/messages/')[1].split(/[?#]/)[0] : null;
    const time = row.querySelector('time[datetime]');
    const label = (row.getAttribute('aria-label') || '') + ' ' + (row.textContent || '');
    return {
      id,
      href,
      // The first line of a conversation row is the display name; the trailing
      // portion is the preview. We keep the raw text too so a caller can
      // recover anything this split gets wrong.
      text: (row.innerText || '').trim(),
      timestamp: time ? time.getAttribute('datetime') : null,
      encrypted: /encrypt|end-to-end/i.test(label),
      unread: !!pick(row, ['[data-testid="cellInnerDiv"] [aria-label*="nread"]']),
    };
  });
}
"""

EXTRACT_MESSAGES_JS = """
(sel) => {
  const all = (cands) => {
    for (const c of cands) {
      const els = document.querySelectorAll(c);
      if (els.length) return Array.from(els);
    }
    return [];
  };
  const rows = all(sel.message);
  const viewport = document.documentElement.clientWidth || 1;
  return rows.map((row, index) => {
    let text = '';
    for (const c of sel.message_text) {
      const nodes = row.querySelectorAll(c);
      if (nodes.length) { text = Array.from(nodes).map(n => n.innerText).join('\\n'); break; }
    }
    if (!text) text = (row.innerText || '').trim();
    const time = row.querySelector('time[datetime]');
    // Direction heuristic: X right-aligns your own messages. Geometry survives
    // class-name churn in a way that a CSS-class check would not, but it is
    // still a heuristic — callers see `direction_source` and can ignore it.
    const rect = row.getBoundingClientRect();
    const bubble = row.firstElementChild ? row.firstElementChild.getBoundingClientRect() : rect;
    let direction = 'unknown';
    if (bubble.width > 0 && rect.width > 0) {
      const centre = (bubble.left + bubble.right) / 2;
      const rowCentre = (rect.left + rect.right) / 2;
      if (centre > rowCentre + rect.width * 0.05) direction = 'outgoing';
      else if (centre < rowCentre - rect.width * 0.05) direction = 'incoming';
    }
    return {
      index,
      text: (text || '').trim(),
      timestamp: time ? time.getAttribute('datetime') : null,
      direction,
      viewport_width: viewport,
    };
  });
}
"""


def normalize_conversations(raw: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean the browser payload: drop id-less rows, de-duplicate, keep order.

    Rows without an id are real — X renders skeleton placeholders while the
    list loads — and they are useless to a caller who has to pass the id back
    in, so they are dropped rather than surfaced with `id: null`.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in raw or []:
        conversation_id = (row.get("id") or "").strip()
        if not conversation_id or conversation_id in seen:
            continue
        seen.add(conversation_id)
        lines = [line for line in (row.get("text") or "").splitlines() if line.strip()]
        out.append(
            {
                "conversation_id": conversation_id,
                "name": lines[0].strip() if lines else "",
                "preview": lines[-1].strip() if len(lines) > 1 else "",
                "timestamp": row.get("timestamp"),
                "encrypted": bool(row.get("encrypted")),
                "unread": bool(row.get("unread")),
            }
        )
    return out


def normalize_messages(
    raw: Iterable[dict[str, Any]], limit: int | None = None
) -> list[dict[str, Any]]:
    """Clean the browser payload and apply `limit` to the *newest* messages.

    X renders oldest-first, so a limit must slice from the end — taking the
    first N would hand back the oldest messages in the conversation, which is
    the opposite of what "last 50 messages" means.
    """
    out: list[dict[str, Any]] = []
    for row in raw or []:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        direction = row.get("direction")
        out.append(
            {
                "text": text,
                "timestamp": row.get("timestamp"),
                "direction": direction
                if direction in ("incoming", "outgoing")
                else "unknown",
                # Named so nobody downstream mistakes the geometry guess for
                # an authoritative sender field.
                "direction_source": "layout-heuristic",
            }
        )
    if limit is not None and limit > 0:
        out = out[-limit:]
    return out


# ── semantic accessibility extraction ────────────────


def _ax_value(node: dict[str, Any], key: str) -> Any:
    value = node.get(key)
    return value.get("value") if isinstance(value, dict) else value


def _ax_property(node: dict[str, Any], name: str) -> Any:
    for prop in node.get("properties") or []:
        if prop.get("name") == name:
            return _ax_value(prop, "value")
    return None


def _ax_index(nodes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(node["nodeId"]): node
        for node in nodes or []
        if node.get("nodeId") is not None
    }


def _has_ancestor_role(
    node: dict[str, Any],
    index: dict[str, dict[str, Any]],
    roles: set[str] | frozenset[str],
) -> bool:
    seen: set[str] = set()
    parent_id = node.get("parentId")
    while parent_id is not None:
        key = str(parent_id)
        if key in seen:
            return False
        seen.add(key)
        parent = index.get(key)
        if parent is None:
            return False
        if _ax_value(parent, "role") in roles:
            return True
        parent_id = parent.get("parentId")
    return False


def _descendants(
    node: dict[str, Any], index: dict[str, dict[str, Any]]
) -> Iterable[dict[str, Any]]:
    """Yield descendants once, tolerating malformed/cyclic diagnostic trees."""
    pending = list(reversed(node.get("childIds") or []))
    seen: set[str] = set()
    while pending:
        node_id = str(pending.pop())
        if node_id in seen:
            continue
        seen.add(node_id)
        child = index.get(node_id)
        if child is None:
            continue
        yield child
        pending.extend(reversed(child.get("childIds") or []))


def _conversation_id(url: str | None) -> str | None:
    if not url:
        return None
    try:
        match = _CONVERSATION_PATH.fullmatch(urlparse(url).path)
    except (TypeError, ValueError):
        return None
    return match.group("id") if match else None


def _leaf_texts(
    node: dict[str, Any], index: dict[str, dict[str, Any]]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for child in _descendants(node, index):
        role = str(_ax_value(child, "role") or "")
        if role not in {"StaticText", "time"}:
            continue
        text = str(_ax_value(child, "name") or "").strip()
        if text and (role, text) not in out:
            out.append((role, text))
    return out


def _layout_direction(node: dict[str, Any], index: dict[str, dict[str, Any]]) -> str:
    parent = index.get(str(node.get("parentId")))
    container = parent.get("_bounds") if parent else None
    text_node = next(
        (
            child
            for child in _descendants(node, index)
            if _ax_value(child, "role") == "StaticText" and child.get("_bounds")
        ),
        None,
    )
    bounds = text_node.get("_bounds") if text_node else None
    if not container or not bounds or container[2] <= 0 or bounds[2] <= 0:
        return "unknown"
    centre = bounds[0] + bounds[2] / 2
    container_centre = container[0] + container[2] / 2
    tolerance = container[2] * 0.05
    if centre > container_centre + tolerance:
        return "outgoing"
    if centre < container_centre - tolerance:
        return "incoming"
    return "unknown"


def extract_conversations_from_ax(
    nodes: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Read XChat rows from semantic link roles and resolved URLs.

    X's CSS classes and test ids rotate. Chromium's accessibility tree has the
    stable contract we actually need here: a conversation is a link, its URL
    contains the conversation id, and its descendants expose user-facing text.
    """
    node_list = list(nodes or [])
    index = _ax_index(node_list)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in node_list:
        if _ax_value(node, "role") != "link":
            continue
        conversation_id = _conversation_id(_ax_property(node, "url"))
        if not conversation_id or conversation_id in seen:
            continue
        seen.add(conversation_id)
        texts = [text for _role, text in _leaf_texts(node, index)]
        accessible_name = str(_ax_value(node, "name") or "").strip()
        handle_match = _HANDLE.search(" ".join((*texts, accessible_name)))
        handle = handle_match.group(1) if handle_match else None
        content = [text for text in texts if not _HANDLE.fullmatch(text)]
        name = content[0] if content else accessible_name
        preview = content[-1] if len(content) > 1 else ""
        timestamp = next(
            (
                text
                for role, text in _leaf_texts(node, index)
                if role == "time" or _RELATIVE_TIME.fullmatch(text)
            ),
            None,
        )
        rows.append(
            {
                "conversation_id": conversation_id,
                "name": name,
                "screen_name": handle,
                "preview": preview,
                "timestamp": timestamp,
                "encrypted": True,
                "unread": "unread" in accessible_name.lower(),
            }
        )
    return rows


def extract_messages_from_ax(
    nodes: Iterable[dict[str, Any]], limit: int | None = None
) -> list[dict[str, Any]]:
    """Read message items from semantic list/article boundaries.

    Sender direction is only reported when the accessible name says so. It is
    deliberately left unknown rather than inferred from generated classes or
    bubble geometry.
    """
    node_list = list(nodes or [])
    index = _ax_index(node_list)
    messages: list[dict[str, Any]] = []
    for node in node_list:
        if _ax_value(node, "role") not in _MESSAGE_ROLES:
            continue
        # Conversation previews are also list items, below a named listbox.
        if _has_ancestor_role(node, index, {"listbox"}):
            continue
        # Prefer the innermost semantic message boundary if X nests list items.
        if any(
            _ax_value(child, "role") in _MESSAGE_ROLES
            for child in _descendants(node, index)
        ):
            continue
        labelled = str(_ax_value(node, "name") or "").strip()
        leaves = _leaf_texts(node, index)
        descendants = list(_descendants(node, index))
        if any(
            _ax_value(child, "role") in {"link", "button"}
            and str(_ax_value(child, "name") or "").lower() == "view profile"
            for child in descendants
        ):
            continue
        timestamps = [
            text
            for role, text in leaves
            if role == "time" or _CLOCK_TEXT.fullmatch(text)
        ]
        text_parts = [
            text
            for role, text in leaves
            if role != "time" and not _CLOCK_TEXT.fullmatch(text)
        ]
        # Date and unread separators are timeline structure, not messages.
        if text_parts and all(
            _DATE_TEXT.fullmatch(text) or text.lower() == "new" for text in text_parts
        ):
            continue
        if not text_parts:
            continue
        lowered = labelled.lower()
        if re.search(r"\byou\b.*\b(sent|message)", lowered):
            direction = "outgoing"
        elif "message from" in lowered:
            direction = "incoming"
        else:
            direction = _layout_direction(node, index)
        direction_source = (
            "accessible-name"
            if re.search(r"\byou\b.*\b(sent|message)", lowered)
            or "message from" in lowered
            else "layout-heuristic"
            if direction != "unknown"
            else "unknown"
        )
        messages.append(
            {
                "text": "\n".join(text_parts),
                "timestamp": timestamps[-1] if timestamps else None,
                "direction": direction,
                "direction_source": direction_source,
            }
        )
    if limit is not None and limit > 0:
        messages = messages[-limit:]
    return messages


def semantic_diagnostics(nodes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return content-free AX counts suitable for doctor output and logs."""
    node_list = list(nodes or [])
    roles = Counter(str(_ax_value(node, "role") or "unknown") for node in node_list)
    root_url = next(
        (
            _ax_property(node, "url")
            for node in node_list
            if _ax_value(node, "role") == "RootWebArea"
        ),
        None,
    )
    route = None
    if root_url:
        try:
            route = urlparse(root_url).path
        except (TypeError, ValueError):
            route = None
    return {
        "route": route,
        "node_count": len(node_list),
        "roles": dict(sorted(roles.items())),
        "conversation_links": len(extract_conversations_from_ax(node_list)),
        "message_items": len(extract_messages_from_ax(node_list)),
        "ignored_nodes": sum(bool(node.get("ignored")) for node in node_list),
    }


async def capture_accessibility_tree(page: Any) -> list[dict[str, Any]]:
    """Capture Chromium's semantic tree through Playwright's CDP session."""
    session = await page.context.new_cdp_session(page)
    try:
        payload = await session.send("Accessibility.getFullAXTree")
        nodes = list(payload.get("nodes") or [])
        dom = await session.send(
            "DOMSnapshot.captureSnapshot",
            {"computedStyles": [], "includeDOMRects": True},
        )
        bounds: dict[int, list[float]] = {}
        for document in dom.get("documents") or []:
            backend_ids = document.get("nodes", {}).get("backendNodeId") or []
            layout = document.get("layout", {})
            for node_index, rect in zip(
                layout.get("nodeIndex") or [], layout.get("bounds") or []
            ):
                if 0 <= node_index < len(backend_ids):
                    bounds[int(backend_ids[node_index])] = list(rect)
        for node in nodes:
            backend_id = node.get("backendDOMNodeId")
            if backend_id in bounds:
                node["_bounds"] = bounds[backend_id]
        return nodes
    finally:
        await session.detach()


async def scroll_semantic_message_list(page: Any) -> bool:
    """Scroll the AX parent of message listitems to its top without selectors."""
    session = await page.context.new_cdp_session(page)
    try:
        payload = await session.send("Accessibility.getFullAXTree")
        nodes = list(payload.get("nodes") or [])
        index = _ax_index(nodes)
        message = next(
            (
                node
                for node in nodes
                if _ax_value(node, "role") in _MESSAGE_ROLES
                and not _has_ancestor_role(node, index, {"listbox"})
            ),
            None,
        )
        parent = index.get(str(message.get("parentId"))) if message else None
        backend_id = parent.get("backendDOMNodeId") if parent else None
        if backend_id is None:
            return False
        resolved = await session.send("DOM.resolveNode", {"backendNodeId": backend_id})
        object_id = (resolved.get("object") or {}).get("objectId")
        if not object_id:
            return False
        await session.send(
            "Runtime.callFunctionOn",
            {
                "objectId": object_id,
                "functionDeclaration": "function() { this.scrollTop = 0; }",
            },
        )
        return True
    finally:
        await session.detach()
