"""Sentinel: README's "Works with" line must not drift from the Install page.

Why this exists
---------------

The Install page grew a Pi card in 0.1.34 and a DeepSeek Harness card in
0.1.40. Neither reached README's one-line client summary, because nothing
connected the two — the list quietly went stale for six releases while
looking authoritative.

Same failure class as the tool-count and live-smoke sentinels: a fact
duplicated in two places with no check that they agree. This asserts the
Install page is the source of truth and README follows it, in all three
locales.

Deliberately loose about *wording*: the README line is prose in three
languages and only needs to name each client. It is strict about
*coverage* — add a client card, and this test tells you exactly which
README lines to update.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_README = _ROOT / "README.md"

# `### Claude Desktop` → "Claude Desktop". Parenthesised qualifiers are
# dropped so `### Cline (VS Code extension)` matches a README that just
# says "Cline", and `### DeepSeek Harness (dsh)` matches either form.
_HEADING_RE = re.compile(r"^### (.+?)\s*(?:\(([^)]*)\))?\s*$", re.M)

# Not a client — the catch-all card at the end of the Install page.
_NOT_A_CLIENT = {"Any other MCP client"}

# The one-line summary in each locale. Each is a blockquote naming the
# clients and trailing off with etc./等/など.
_SUMMARY_MARKERS = {
    "en": "Works with:",
    "zh": "兼容：",
    "ja": "対応クライアント：",
}


def _install_clients() -> list[tuple[str, str | None]]:
    """(name, parenthesised alias) for every client card on the Install page."""
    src = (_ROOT / "docs" / "install.en.md").read_text(encoding="utf-8")
    return [
        (name.strip(), (alias or "").strip() or None)
        for name, alias in _HEADING_RE.findall(src)
        if name.strip() not in _NOT_A_CLIENT
    ]


def _summary_lines() -> dict[str, str]:
    lines = {}
    for line in _README.read_text(encoding="utf-8").splitlines():
        for locale, marker in _SUMMARY_MARKERS.items():
            if marker in line:
                lines[locale] = line
    return lines


def test_install_page_has_client_cards():
    """Meta-guard: if the heading walk breaks, the checks below go vacuous."""
    clients = _install_clients()
    assert len(clients) >= 8, (
        f"expected 8+ client cards on the Install page, found {len(clients)}: "
        f"{[c[0] for c in clients]} — did the heading format change?"
    )


def test_readme_has_a_summary_line_per_locale():
    lines = _summary_lines()
    missing = sorted(set(_SUMMARY_MARKERS) - set(lines))
    assert not missing, f"README lost its client summary for locale(s): {missing}"


def test_every_documented_client_appears_in_every_readme_summary():
    """Add a client card → this tells you which README lines to update."""
    lines = _summary_lines()
    problems = []
    for name, alias in _install_clients():
        for locale, line in sorted(lines.items()):
            # Either the full name or its parenthesised short form counts.
            if name in line or (alias and alias in line):
                continue
            problems.append(f"{locale}: {name!r} missing")
    assert not problems, (
        "README's client summary has drifted from docs/install.en.md:\n  "
        + "\n  ".join(problems)
        + "\n\nThe Install page is the source of truth. Add the client to the "
        "`Works with:` / `兼容：` / `対応クライアント：` lines in README.md."
    )
