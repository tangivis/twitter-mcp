"""Issue #90: API docs page must be localized per locale.

Sentinel: run `scripts/gen_api_docs.py` (idempotent, mock-free) and
assert that `docs/api.{en,zh,ja}.md` exist with locale-appropriate
chrome (title) and tool-name parity (every registered MCP tool
appears in every locale page).

Pattern matches `tests/test_docs_cli_listing.py`.
"""

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_FILES = {
    "en": _REPO_ROOT / "docs" / "api.en.md",
    "zh": _REPO_ROOT / "docs" / "api.zh.md",
    "ja": _REPO_ROOT / "docs" / "api.ja.md",
}
_LOCALE_TITLES = {
    "en": "MCP Tools API Reference",
    "zh": "MCP 工具 API 参考",
    "ja": "MCP ツール API リファレンス",
}


@pytest.fixture(scope="module", autouse=True)
def _regen_docs():
    """Run the generator once per module so tests see fresh files.
    The script is mock-free (reads `mcp._tool_manager._tools`) and idempotent.
    """
    import subprocess

    subprocess.run(
        ["python", str(_REPO_ROOT / "scripts" / "gen_api_docs.py")],
        check=True,
        cwd=_REPO_ROOT,
    )


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
def test_api_page_exists_per_locale(locale):
    """Every locale gets a `docs/api.<locale>.md`."""
    assert _API_FILES[locale].exists(), (
        f"docs/api.{locale}.md missing — gen_api_docs.py didn't emit it. "
        f"Issue #90: api docs must be localized."
    )


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
def test_api_page_title_is_localized(locale):
    """Title (first `# ` line) is in the right language."""
    src = _API_FILES[locale].read_text(encoding="utf-8")
    expected_title = _LOCALE_TITLES[locale]
    assert f"# {expected_title}" in src, (
        f"docs/api.{locale}.md doesn't start with '# {expected_title}'. "
        f"Either the chrome translation drifted or i18n broke."
    )


def test_api_pages_have_tool_name_parity():
    """Every registered MCP tool appears in all 3 locale pages — i.e. the
    locales differ only in chrome, never in which tools they document."""
    from twitter_mcp.server import mcp

    tool_names = set(mcp._tool_manager._tools.keys())
    pages = {
        locale: path.read_text(encoding="utf-8") for locale, path in _API_FILES.items()
    }

    missing_per_locale = {}
    for locale, src in pages.items():
        # Tool names appear as `### \`<name>\`` headers in the generated md.
        missing = [n for n in tool_names if f"`{n}`" not in src]
        if missing:
            missing_per_locale[locale] = missing
    assert not missing_per_locale, (
        f"Tool-name parity broken across locales: {missing_per_locale}. "
        f"Every locale must list every tool — chrome-only translation, "
        f"docstrings stay native."
    )


def test_legacy_api_md_is_not_emitted():
    """The pre-issue-#90 `docs/api.md` (single English file) is no
    longer the source of truth — i18n now uses `api.<locale>.md`. Make
    sure the generator cleaned up any leftover."""
    legacy = _REPO_ROOT / "docs" / "api.md"
    assert not legacy.exists(), (
        f"Legacy {legacy} found. The generator should unlink it after "
        f"writing the per-locale files (issue #90)."
    )
