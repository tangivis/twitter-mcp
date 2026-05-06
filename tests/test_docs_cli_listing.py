"""Issue #58 guard: cli.{en,zh,ja}.md must end with the auto-generated
all-tools listing so the per-locale CLI page documents every tool.

Two layers of coverage:

1. **Snippet-include directive** must be present in each cli.md (static
   markdown check). This is what hooks the generated excerpt into
   the rendered cli page.
2. **Generator** must produce `docs/_cli_tools.{en,zh,ja}.md` files
   when run; each must contain a `twikit-mcp call <tool>` line for
   every tool in `mcp._tool_manager._tools`. (Subprocess, slow.)
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
def test_cli_page_includes_tools_excerpt(locale):
    """The cli page in every language must reference the auto-gen excerpt
    via pymdownx.snippets `--8<--` directive — otherwise the
    "All tools (machine CLI)" section won't render even when
    `_cli_tools.<locale>.md` is generated."""
    cli_page = _ROOT / "docs" / f"cli.{locale}.md"
    src = cli_page.read_text(encoding="utf-8")
    expected = f'--8<-- "docs/_cli_tools.{locale}.md"'
    assert expected in src, (
        f"{cli_page.name} doesn't include the snippet directive "
        f"{expected!r}. Issue #58: this is what stitches the auto-generated "
        f"all-tools listing into the per-locale CLI page."
    )


def test_gen_script_writes_per_locale_cli_tool_excerpts(tmp_path):
    """Run gen_api_docs.py — assert it produces all 3 cli-tool excerpts
    on disk + each contains a `twikit-mcp call <tool>` line for every
    registered tool name."""
    # Run the generator. It writes into <repo>/docs/, not tmp_path —
    # we'll clean up after.
    script = _ROOT / "scripts" / "gen_api_docs.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        timeout=30,
    )
    assert result.returncode == 0, f"gen_api_docs.py failed: {result.stderr}"

    # Pull the live tool list (same instance the script just walked) so
    # the assertion is exact, not approximate.
    sys.path.insert(0, str(_ROOT))
    from twitter_mcp.server import mcp  # noqa: E402

    tool_names = set(mcp._tool_manager._tools)

    for locale in ("en", "zh", "ja"):
        excerpt = _ROOT / "docs" / f"_cli_tools.{locale}.md"
        assert excerpt.exists(), (
            f"Generator didn't produce {excerpt.relative_to(_ROOT)}"
        )
        body = excerpt.read_text(encoding="utf-8")

        # Every tool name appears in a `twikit-mcp call <name>` line.
        # Use a regex that requires word boundary + the call form, so
        # "send_dm" doesn't false-match "send_dm_to_group" etc.
        for name in tool_names:
            pattern = rf"twikit-mcp call {re.escape(name)}\b"
            assert re.search(pattern, body), (
                f"_cli_tools.{locale}.md missing CLI invocation line "
                f"for tool {name!r}. The generator should emit one "
                f"`twikit-mcp call <name> …` example per tool, per locale."
            )


def test_gen_script_localizes_zh_section_headers():
    """Spot-check that zh excerpt actually has Chinese section labels —
    not English ones (which would mean the locale wiring is broken).

    Requires the previous test to have already produced the excerpts.
    """
    excerpt = _ROOT / "docs" / "_cli_tools.zh.md"
    if not excerpt.exists():
        pytest.skip("excerpt not generated yet — see prior test")
    body = excerpt.read_text(encoding="utf-8")
    # `_LOCALES["zh"]["sections"]["Tweets"]` is "推文 (Tweets)".
    assert "推文 (Tweets)" in body, "zh excerpt missing localized section header"


def test_gen_script_localizes_ja_section_headers():
    """Same for ja."""
    excerpt = _ROOT / "docs" / "_cli_tools.ja.md"
    if not excerpt.exists():
        pytest.skip("excerpt not generated yet — see prior test")
    body = excerpt.read_text(encoding="utf-8")
    assert "ツイート (Tweets)" in body, "ja excerpt missing localized section header"
