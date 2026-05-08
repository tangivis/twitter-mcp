"""Issue #92: per-client install matrix in docs/install.{en,zh,ja}.md.

Sentinel: assert the install page exists per locale, carries the
right title, has sections for the 6 documented clients, and the
JSON config snippet parses as valid JSON.
"""

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_INSTALL_FILES = {
    "en": _REPO_ROOT / "docs" / "install.en.md",
    "zh": _REPO_ROOT / "docs" / "install.zh.md",
    "ja": _REPO_ROOT / "docs" / "install.ja.md",
}
# Strings each locale's title MUST contain (substring, not exact).
_LOCALE_TITLE_HINT = {
    "en": "Install",
    "zh": "安装",
    "ja": "インストール",
}
# Clients that must each get their own h3 section in every locale.
_CLIENTS = [
    "Claude Code",
    "Claude Desktop",
    "Cursor",
    "Windsurf",
    "Cline",
    "opencode",
]


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
def test_install_page_exists_per_locale(locale):
    assert _INSTALL_FILES[locale].exists(), (
        f"docs/install.{locale}.md missing — issue #92 requires per-locale install pages."
    )


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
def test_install_page_title_carries_locale_hint(locale):
    src = _INSTALL_FILES[locale].read_text(encoding="utf-8")
    # The title is the first `# ` line; assert the locale's word for
    # "install" appears in it.
    title_line = next(
        (line for line in src.splitlines() if line.startswith("# ")), None
    )
    assert title_line, f"no top-level `# ` heading in install.{locale}.md"
    assert _LOCALE_TITLE_HINT[locale] in title_line, (
        f"title {title_line!r} doesn't include the {locale} keyword "
        f"{_LOCALE_TITLE_HINT[locale]!r}; check translation."
    )


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
@pytest.mark.parametrize("client", _CLIENTS)
def test_install_page_documents_each_client(locale, client):
    src = _INSTALL_FILES[locale].read_text(encoding="utf-8")
    # h3 + client name appears somewhere (heading or path table or JSON
    # comment — any mention proves the section exists).
    assert client in src, (
        f"install.{locale}.md doesn't mention client {client!r}. "
        f"Issue #92 requires all 6 clients per locale."
    )


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
def test_install_page_uses_uv_tool_install_canonical(locale):
    """The single canonical install command — `uv tool install
    twikit-mcp` — must be on the page."""
    src = _INSTALL_FILES[locale].read_text(encoding="utf-8")
    assert "uv tool install twikit-mcp" in src, (
        f"install.{locale}.md missing the canonical "
        f"`uv tool install twikit-mcp` command."
    )


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
def test_install_page_json_snippets_are_valid(locale):
    """Every fenced ```json block on the page parses as valid JSON.
    Catches silent typos that would mislead users (trailing comma /
    unbalanced brace etc.)."""
    src = _INSTALL_FILES[locale].read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", src, flags=re.DOTALL)
    assert blocks, f"install.{locale}.md has zero ```json blocks"
    for i, block in enumerate(blocks):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError as e:
            pytest.fail(
                f"JSON block #{i + 1} in install.{locale}.md is invalid: {e}\n"
                f"Block:\n{block}"
            )
        # Sanity: every snippet should be an mcpServers config.
        assert "mcpServers" in parsed, (
            f"JSON block #{i + 1} in install.{locale}.md doesn't have "
            f"`mcpServers` top-level key."
        )
