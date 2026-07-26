"""Turning the decrypted X web client's DOM into structured data.

Everything here is deliberately free of Playwright imports. The browser-side
work is two `evaluate()` scripts (constants below) and the interpretation of
what they return is plain functions — so the fragile part (selectors) and the
lossy part (normalisation) can both be unit-tested without launching a browser.

On selector drift: X ships DOM changes regularly, and this package reads the
rendered client rather than an API, so drift is a *when*, not an *if*. Two
mitigations, in order of preference:

1. Every logical element has a *list* of candidate selectors, most-stable
   first. `data-testid` attributes survive X's CSS-in-JS class churn, so they
   lead; structural fallbacks trail.
2. `XCHAT_SELECTORS=/path/to.json` overrides any subset at runtime, so a break
   is a config edit rather than a release. `twikit-mcp xchat doctor` prints
   which candidates currently match.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

# A logged-out visitor is served a login sheet that contains an account-password
# field. Typing the chat PIN into it would submit a secret to the wrong form and
# register a failed login against the account, so anything that matches this is
# never treated as a PIN field — see `LOGIN_PASSWORD_SELECTOR` in session.py.
LOGIN_PASSWORD_ATTRS = ('[name="password"]', '[autocomplete="current-password"]')

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
