"""Settings + dotenv resolution for the XChat path."""

from pathlib import Path

from twitter_mcp.xchat.config import (
    DEFAULT_TIMEOUT_MS,
    XChatSettings,
    load_env_files,
    load_settings,
    parse_env_file,
)


def test_parse_env_file_handles_comments_quotes_and_export():
    parsed = parse_env_file(
        "\n".join(
            [
                "# a comment",
                "",
                "XCHAT_PIN='1234'",
                'XCHAT_PROFILE_DIR="/tmp/p"',
                "export XCHAT_HEADLESS=false",
                "NO_EQUALS_LINE",
                "=novalue",
            ]
        )
    )
    assert parsed == {
        "XCHAT_PIN": "1234",
        "XCHAT_PROFILE_DIR": "/tmp/p",
        "XCHAT_HEADLESS": "false",
    }


def test_parse_env_file_does_not_expand_variables():
    # A PIN containing `$` must survive verbatim.
    assert parse_env_file("XCHAT_PIN=12$HOME34")["XCHAT_PIN"] == "12$HOME34"


def _repo(tmp_path: Path) -> Path:
    # `parents=True` so callers can point at a not-yet-created nested dir.
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


def test_env_local_beats_env(tmp_path):
    root = _repo(tmp_path)
    (root / ".env").write_text("XCHAT_PIN=from-env\nXCHAT_TIMEOUT_MS=1\n")
    (root / ".env.local").write_text("XCHAT_PIN=from-env-local\n")
    merged = load_env_files(root)
    assert merged["XCHAT_PIN"] == "from-env-local"
    # Keys only present in `.env` still come through.
    assert merged["XCHAT_TIMEOUT_MS"] == "1"


def test_env_files_found_from_subdirectory(tmp_path):
    root = _repo(tmp_path)
    (root / ".env.local").write_text("XCHAT_PIN=up-there\n")
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    assert load_env_files(nested)["XCHAT_PIN"] == "up-there"


def test_walk_stops_at_repo_root(tmp_path):
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / ".env.local").write_text("XCHAT_PIN=outside\n")
    inner = _repo(outer / "repo")
    assert "XCHAT_PIN" not in load_env_files(inner)


def test_unreadable_env_file_is_skipped(tmp_path):
    root = _repo(tmp_path)
    # A directory named `.env.local` is readable as a path but not as a file.
    (root / ".env.local").mkdir()
    (root / ".env").write_text("XCHAT_PIN=ok\n")
    assert load_env_files(root)["XCHAT_PIN"] == "ok"


def test_permission_denied_env_file_is_skipped_not_fatal(tmp_path):
    """A root-owned or chmod-000 `.env.local` must not break every command."""
    root = _repo(tmp_path)
    unreadable = root / ".env.local"
    unreadable.write_text("XCHAT_PIN=unreadable\n")
    unreadable.chmod(0o000)
    try:
        (root / ".env").write_text("XCHAT_PIN=ok\n")
        assert load_env_files(root)["XCHAT_PIN"] == "ok"
    finally:
        unreadable.chmod(0o600)


def test_a_line_with_no_key_is_ignored():
    assert parse_env_file("=orphaned\nXCHAT_PIN=1234\n") == {"XCHAT_PIN": "1234"}


def test_process_env_wins_over_file(tmp_path):
    root = _repo(tmp_path)
    (root / ".env.local").write_text("XCHAT_PIN=file\n")
    settings = load_settings({"XCHAT_PIN": "shell"}, search_from=root)
    assert settings.pin == "shell"


def test_empty_process_value_falls_back_to_file(tmp_path):
    root = _repo(tmp_path)
    (root / ".env.local").write_text("XCHAT_PIN=file\n")
    assert load_settings({"XCHAT_PIN": ""}, search_from=root).pin == "file"


def test_defaults_when_nothing_configured(tmp_path):
    settings = load_settings({}, search_from=_repo(tmp_path))
    assert settings.pin is None
    assert settings.headless is True
    assert settings.pin_prompt == "auto"
    assert settings.timeout_ms == DEFAULT_TIMEOUT_MS
    assert settings.selector_overrides is None
    assert settings.cookie_file is None
    assert settings.database_path is None
    assert settings.has_pin is False


def test_invalid_values_fall_back_to_defaults(tmp_path):
    settings = load_settings(
        {
            "XCHAT_HEADLESS": "maybe",
            "XCHAT_TIMEOUT_MS": "soon",
            "XCHAT_PIN_PROMPT": "x",
        },
        search_from=_repo(tmp_path),
    )
    assert settings.headless is True
    assert settings.timeout_ms == DEFAULT_TIMEOUT_MS
    assert settings.pin_prompt == "auto"


def test_boolean_and_path_expansion(tmp_path):
    settings = load_settings(
        {
            "XCHAT_HEADLESS": "no",
            "XCHAT_PROFILE_DIR": "~/somewhere",
            "XCHAT_SELECTORS": "~/sel.json",
            "XCHAT_COOKIE_FILE": "~/cookies.json",
            "XCHAT_DATABASE_PATH": "~/chat.db",
            "XCHAT_PIN_PROMPT": "WEB",
        },
        search_from=_repo(tmp_path),
    )
    assert settings.headless is False
    assert "~" not in str(settings.profile_dir)
    assert "~" not in str(settings.selector_overrides)
    assert "~" not in str(settings.cookie_file)
    assert "~" not in str(settings.database_path)
    assert settings.pin_prompt == "web"


def test_pin_is_not_exposed_in_repr():
    settings = XChatSettings(profile_dir=Path("/tmp/p"), pin="9999")
    assert "9999" not in repr(settings)
    assert "<set>" in repr(settings)
    assert settings.has_pin is True
