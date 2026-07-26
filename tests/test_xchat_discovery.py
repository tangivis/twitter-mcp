"""Browser/profile discovery for Chromium-backed XChat databases."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from twitter_mcp.xchat.discovery import (
    discover_xchat_databases,
    resolve_xchat_database_path,
)
from twitter_mcp.xchat.errors import XChatUnavailable


def _xchat_database(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE dm_conversation (conversation_id TEXT);
        CREATE TABLE dm_entry (entry_id TEXT, plain_text TEXT);
        CREATE TABLE dm_user (id INTEGER);
        CREATE TABLE dm_key_material (tag TEXT, bytes BLOB);
        """
    )
    con.close()
    return path


def test_discovers_xchat_database_in_named_chrome_profile(tmp_path):
    root = tmp_path / "Chrome"
    expected = _xchat_database(root / "Profile 2" / "File System" / "005" / "db")

    report = discover_xchat_databases(browser="chrome", roots={"chrome": root})

    assert report["state"] == "found"
    assert report["matches"] == [
        {
            "browser": "chrome",
            "profile": "Profile 2",
            "database_path": str(expected.resolve()),
            "database_size": expected.stat().st_size,
            "last_updated": report["matches"][0]["last_updated"],
        }
    ]
    assert report["errors"] == []


def test_auto_scans_supported_browsers_and_sorts_newest_first(tmp_path):
    chrome_root = tmp_path / "Chrome"
    edge_root = tmp_path / "Edge"
    older = _xchat_database(chrome_root / "Default" / "File System" / "a")
    newer = _xchat_database(edge_root / "Profile 1" / "File System" / "b")
    older.touch()
    newer.touch()
    newer_mtime = older.stat().st_mtime + 10
    newer.touch()
    import os

    os.utime(newer, (newer_mtime, newer_mtime))

    report = discover_xchat_databases(roots={"chrome": chrome_root, "edge": edge_root})

    assert [match["browser"] for match in report["matches"]] == ["edge", "chrome"]


def test_profile_filter_avoids_other_profiles(tmp_path):
    root = tmp_path / "Chrome"
    _xchat_database(root / "Default" / "File System" / "a")
    selected = _xchat_database(root / "Profile 3" / "File System" / "b")

    report = discover_xchat_databases(
        browser="chrome", profile="Profile 3", roots={"chrome": root}
    )

    assert [row["database_path"] for row in report["matches"]] == [
        str(selected.resolve())
    ]


def test_ignores_non_sqlite_and_wrong_schema_without_reading_contents(tmp_path):
    root = tmp_path / "Chromium"
    fs = root / "Default" / "File System"
    fs.mkdir(parents=True)
    (fs / "plain").write_text("private message text", encoding="utf-8")
    wrong = sqlite3.connect(fs / "wrong")
    wrong.execute("CREATE TABLE unrelated(secret TEXT)")
    wrong.execute("INSERT INTO unrelated VALUES ('do-not-expose')")
    wrong.close()

    report = discover_xchat_databases(browser="chromium", roots={"chromium": root})

    assert report["state"] == "not_found"
    assert report["matches"] == []
    assert "do-not-expose" not in str(report)
    assert "private message text" not in str(report)


def test_missing_root_is_not_a_permission_error(tmp_path):
    report = discover_xchat_databases(
        browser="chrome", roots={"chrome": tmp_path / "missing"}
    )

    assert report["state"] == "not_found"
    assert report["errors"] == []


def test_permission_denied_is_reported_distinctly(monkeypatch, tmp_path):
    root = tmp_path / "Chrome"
    root.mkdir()

    def denied(_path):
        raise PermissionError("private browser profile")

    monkeypatch.setattr("twitter_mcp.xchat.discovery._profile_directories", denied)

    report = discover_xchat_databases(browser="chrome", roots={"chrome": root})

    assert report["state"] == "permission_denied"
    assert report["errors"] == [
        {"browser": "chrome", "path": str(root), "error": "permission_denied"}
    ]
    assert "private browser profile" not in str(report)


def test_unknown_browser_is_actionable(tmp_path):
    with pytest.raises(XChatUnavailable, match="Supported browsers"):
        discover_xchat_databases(browser="safari", roots={})


def test_resolver_prefers_explicit_path_without_discovery(monkeypatch, tmp_path):
    path = tmp_path / "explicit.db"
    monkeypatch.setattr(
        "twitter_mcp.xchat.discovery.discover_xchat_databases",
        lambda **kwargs: pytest.fail("explicit path must bypass discovery"),
    )

    assert resolve_xchat_database_path(path, "chrome", "Default") == path.resolve()


def test_resolver_returns_unique_discovery_match(monkeypatch, tmp_path):
    path = tmp_path / "chat.db"
    monkeypatch.setattr(
        "twitter_mcp.xchat.discovery.discover_xchat_databases",
        lambda **kwargs: {
            "state": "found",
            "matches": [{"database_path": str(path)}],
            "errors": [],
        },
    )

    assert resolve_xchat_database_path(None, "chrome", "Default") == path


@pytest.mark.parametrize(
    ("report", "message"),
    [
        (
            {"state": "permission_denied", "matches": [], "errors": [{}]},
            "Full Disk Access",
        ),
        ({"state": "not_found", "matches": [], "errors": []}, "finish syncing"),
        (
            {
                "state": "found",
                "matches": [
                    {
                        "browser": "chrome",
                        "profile": "Default",
                        "database_path": "/a",
                    },
                    {
                        "browser": "chrome",
                        "profile": "Profile 1",
                        "database_path": "/b",
                    },
                ],
                "errors": [],
            },
            "Multiple",
        ),
    ],
)
def test_resolver_reports_ambiguous_or_unavailable_discovery(
    monkeypatch, report, message
):
    monkeypatch.setattr(
        "twitter_mcp.xchat.discovery.discover_xchat_databases",
        lambda **kwargs: report,
    )

    with pytest.raises(XChatUnavailable, match=message):
        resolve_xchat_database_path(None, "chrome", None)


def test_resolver_returns_none_when_database_mode_is_unconfigured():
    assert resolve_xchat_database_path(None, None, None) is None


def test_cli_parser_accepts_discover_browser_and_profile():
    from twitter_mcp.xchat.cli import add_parser

    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers(dest="command"))

    args = parser.parse_args(
        ["xchat", "discover", "--browser", "chrome", "--profile", "Profile 2"]
    )

    assert args.xchat_cmd == "discover"
    assert args.browser == "chrome"
    assert args.profile == "Profile 2"


def test_cli_discover_prints_sanitized_report(monkeypatch, capsys):
    from twitter_mcp.xchat import cli

    report = {"state": "not_found", "matches": [], "errors": []}
    monkeypatch.setattr(cli, "discover_xchat_databases", lambda **kwargs: report)

    result = asyncio.run(cli.cmd_discover("chrome", "Default"))

    assert result == 2
    assert json.loads(capsys.readouterr().out) == report
