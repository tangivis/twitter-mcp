"""Issue #118: dependency-free local XChat reader.

X's web client decrypts XChat conversations locally and writes the
plaintext to a SQLite database in Chromium's origin-private filesystem.
This reader opens that file read-only and projects `plain_text`; it never
touches key material, never writes, and needs no network, no PIN, and no
credentials.

Why these tests can exist at all
--------------------------------

The browser-automation and paid-API paths in PR #107 cannot be exercised
in CI — no browser profiles, no XChat PIN, no paid credentials. This
slice can: a SQLite file is trivially constructible, so every test below
drives the *real* code path against a *real* database. Nothing about the
component under test is mocked. Discovery takes an injectable roots map
so profile scanning runs against a `tmp_path` tree.

The fixture schema mirrors the columns the reader actually projects. If X
changes its schema this suite keeps passing while production breaks —
that is the accepted fragility recorded in #118, and it is why
`_validate` checks table names up front and raises a clean error.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from twitter_mcp.xchat import (
    XChatDatabase,
    XChatExtractionFailed,
    XChatUnavailable,
    discover_xchat_databases,
    resolve_xchat_database_path,
)

# ── fixture: a real XChat-shaped SQLite database ─────


def _build_db(path: Path, *, rows: list[dict] | None = None) -> Path:
    """Create a SQLite file with X's XChat schema and sample content.

    Columns mirror what the reader projects. `dm_key_material` exists
    because discovery and validation require the table name — the reader
    only ever COUNTs it, never reads `bytes`.
    """
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE dm_conversation (
            conversation_id TEXT PRIMARY KEY,
            custom_title TEXT,
            last_read_sequence_number INTEGER,
            marked_unread_by_me INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0
        );
        CREATE TABLE dm_entry (
            entry_id TEXT PRIMARY KEY,
            conversation_id TEXT,
            sequence_number INTEGER,
            timestamp INTEGER,
            sender_id TEXT,
            sender_is_owner INTEGER,
            plain_text TEXT,
            has_attachment INTEGER DEFAULT 0,
            attachment_types TEXT,
            entry_type TEXT DEFAULT 'message',
            affects_sort_order INTEGER DEFAULT 1
        );
        CREATE TABLE dm_user (id INTEGER PRIMARY KEY, screen_name TEXT);
        CREATE TABLE dm_key_material (conversation_id TEXT, bytes BLOB);
        """
    )
    # owner = 100, peer = 200; group conversation has its own id shape.
    con.executemany(
        "INSERT INTO dm_user (id, screen_name) VALUES (?, ?)",
        [(100, "me"), (200, "alice"), (300, "bob")],
    )
    con.executemany(
        "INSERT INTO dm_conversation "
        "(conversation_id, custom_title, last_read_sequence_number, "
        " marked_unread_by_me, deleted) VALUES (?, ?, ?, ?, ?)",
        [
            ("100-200", None, 2, 0, 0),  # fully read
            ("g-777", "Team chat", 1, 0, 0),  # has a custom title, unread
            ("100-300", None, 1, 1, 0),  # explicitly marked unread
            ("100-999", None, 1, 0, 1),  # deleted → must never appear
        ],
    )
    entries = rows if rows is not None else _default_entries()
    con.executemany(
        "INSERT INTO dm_entry (entry_id, conversation_id, sequence_number, "
        "timestamp, sender_id, sender_is_owner, plain_text, has_attachment, "
        "attachment_types, entry_type, affects_sort_order) "
        "VALUES (:entry_id, :conversation_id, :sequence_number, :timestamp, "
        ":sender_id, :sender_is_owner, :plain_text, :has_attachment, "
        ":attachment_types, :entry_type, :affects_sort_order)",
        entries,
    )
    con.commit()
    con.close()
    return path


def _entry(**kw):
    base = {
        "entry_id": "e1",
        "conversation_id": "100-200",
        "sequence_number": 1,
        "timestamp": 1_700_000_000_000,
        "sender_id": "200",
        "sender_is_owner": 0,
        "plain_text": "hello",
        "has_attachment": 0,
        "attachment_types": None,
        "entry_type": "message",
        "affects_sort_order": 1,
    }
    base.update(kw)
    return base


def _default_entries():
    return [
        _entry(entry_id="a1", sequence_number=1, timestamp=1_700_000_001_000),
        _entry(
            entry_id="a2",
            sequence_number=2,
            timestamp=1_700_000_002_000,
            sender_id="100",
            sender_is_owner=1,
            plain_text="hi back",
        ),
        # group conversation, newer than the direct one
        _entry(
            entry_id="g1",
            conversation_id="g-777",
            sequence_number=2,
            timestamp=1_700_000_009_000,
            sender_id="300",
            plain_text="standup in 5",
        ),
        _entry(
            entry_id="u1",
            conversation_id="100-300",
            sequence_number=2,
            timestamp=1_700_000_003_000,
            sender_id="300",
            plain_text="ping",
        ),
        # deleted conversation's message — must never surface
        _entry(
            entry_id="d1",
            conversation_id="100-999",
            sequence_number=2,
            timestamp=1_700_000_100_000,
            plain_text="SHOULD NOT APPEAR",
        ),
    ]


@pytest.fixture
def db(tmp_path):
    return XChatDatabase(_build_db(tmp_path / "xchat.sqlite"))


# ── status ───────────────────────────────────────────


def test_status_reports_ready_with_counts(db):
    out = db.status()
    assert out["state"] == "ready"
    assert out["source"] == "local_database"
    assert out["database_exists"] is True
    assert out["conversation_count"] == 3  # the deleted one is excluded
    assert out["last_updated"].endswith("Z")


def test_status_on_missing_file_raises_unavailable(tmp_path):
    missing = tmp_path / "nope.sqlite"
    with pytest.raises(XChatUnavailable) as caught:
        XChatDatabase(missing).status()
    # The message must name the path and say what to do about it.
    assert str(missing) in str(caught.value)
    assert "sync" in str(caught.value).lower()


# ── list_conversations ───────────────────────────────


def test_list_conversations_newest_first_with_names(db):
    out = db.list_conversations()
    assert [c["conversation_id"] for c in out] == ["g-777", "100-300", "100-200"]
    # custom_title wins for the group; screen_name resolves for direct chats
    assert out[0]["name"] == "Team chat"
    assert out[1]["screen_name"] == "bob"
    assert out[2]["screen_name"] == "alice"
    assert out[2]["preview"] == "hi back"
    assert all(c["encrypted"] is True for c in out)


def test_deleted_conversations_never_surface(db):
    ids = [c["conversation_id"] for c in db.list_conversations()]
    assert "100-999" not in ids
    blob = json.dumps(db.list_conversations())
    assert "SHOULD NOT APPEAR" not in blob


def test_unread_computed_from_sequence_and_flag(db):
    by_id = {c["conversation_id"]: c for c in db.list_conversations()}
    assert by_id["100-200"]["unread"] is False  # last_read 2 >= seq 2
    assert by_id["g-777"]["unread"] is True  # last_read 1 < seq 2
    assert by_id["100-300"]["unread"] is True  # marked_unread_by_me


def test_unread_only_filters(db):
    out = db.list_conversations(unread_only=True)
    assert {c["conversation_id"] for c in out} == {"g-777", "100-300"}


def test_list_limit_is_clamped(db):
    assert len(db.list_conversations(limit=1)) == 1
    assert len(db.list_conversations(limit=0)) == 1  # clamped up to 1
    assert len(db.list_conversations(limit=10_000)) == 3  # clamped down, no crash


# ── get_history ──────────────────────────────────────


def test_history_is_oldest_first_with_direction(db):
    out = db.get_history("100-200")
    assert [m["text"] for m in out] == ["hello", "hi back"]
    assert out[0]["direction"] == "incoming"
    assert out[1]["direction"] == "outgoing"
    assert out[0]["sender_screen_name"] == "alice"
    assert out[0]["timestamp"].endswith("Z")


def test_history_unknown_conversation_raises_clean_error(db):
    with pytest.raises(XChatExtractionFailed, match="No local messages"):
        db.get_history("100-does-not-exist")


def test_history_rejects_empty_conversation_id(db):
    with pytest.raises(XChatExtractionFailed, match="non-empty"):
        db.get_history("")


def test_history_limit_returns_most_recent(db):
    out = db.get_history("100-200", limit=1)
    assert [m["text"] for m in out] == ["hi back"]


# ── entry rendering ──────────────────────────────────


def test_attachment_only_entry_renders_placeholder(tmp_path):
    db = XChatDatabase(
        _build_db(
            tmp_path / "x.sqlite",
            rows=[
                _entry(plain_text="", has_attachment=1, attachment_types="image"),
                _entry(entry_id="e2", sequence_number=2, plain_text=None),
            ],
        )
    )
    texts = [m["text"] for m in db.get_history("100-200")]
    assert texts == ["[image attachment]", "[message]"]
    assert all(t.strip() for t in texts), "an agent must never see a blank message"


def test_bare_attachment_without_type(tmp_path):
    db = XChatDatabase(
        _build_db(
            tmp_path / "x.sqlite",
            rows=[_entry(plain_text=None, has_attachment=1, attachment_types=None)],
        )
    )
    assert db.get_history("100-200")[0]["text"] == "[attachment]"


def test_non_message_and_unsorted_entries_are_excluded(tmp_path):
    db = XChatDatabase(
        _build_db(
            tmp_path / "x.sqlite",
            rows=[
                _entry(plain_text="real"),
                _entry(
                    entry_id="e2", sequence_number=2, entry_type="trust_conversation"
                ),
                _entry(entry_id="e3", sequence_number=3, affects_sort_order=0),
            ],
        )
    )
    assert [m["text"] for m in db.get_history("100-200")] == ["real"]


def test_unparseable_timestamp_becomes_none(tmp_path):
    db = XChatDatabase(_build_db(tmp_path / "x.sqlite", rows=[_entry(timestamp=None)]))
    assert db.get_history("100-200")[0]["timestamp"] is None


# ── validation of the target file ────────────────────


def test_non_xchat_sqlite_is_rejected(tmp_path):
    other = tmp_path / "other.sqlite"
    con = sqlite3.connect(other)
    con.execute("CREATE TABLE unrelated (id INTEGER)")
    con.commit()
    con.close()
    with pytest.raises(XChatExtractionFailed, match="missing required XChat tables"):
        XChatDatabase(other).status()


def test_non_sqlite_file_raises_extraction_error(tmp_path):
    junk = tmp_path / "junk.sqlite"
    junk.write_bytes(b"definitely not a database")
    with pytest.raises(XChatExtractionFailed, match="Could not read"):
        XChatDatabase(junk).status()


# ── the reader must never mutate the source ──────────


def test_full_read_cycle_leaves_the_file_untouched(db):
    before = (db.path.stat().st_size, db.path.stat().st_mtime_ns)
    db.status()
    db.list_conversations()
    db.get_history("100-200")
    db.doctor()
    assert (db.path.stat().st_size, db.path.stat().st_mtime_ns) == before


def test_module_source_contains_no_write_statements():
    """Belt-and-braces against a future edit introducing a write."""
    import twitter_mcp.xchat.database as mod

    src = Path(mod.__file__).read_text(encoding="utf-8").upper()
    for verb in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "ATTACH "):
        assert verb not in src, f"{verb.strip()} appeared in the read-only reader"


def test_key_material_is_only_ever_counted():
    """Every SQL statement touching the key table must be a COUNT.

    Reading `dm_key_material.bytes` would turn a plaintext reader into a
    key extractor. Checked against the SQL itself rather than by prose
    proximity, so a future query can't sneak past.
    """
    import re

    import twitter_mcp.xchat.database as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    reads = re.findall(r"FROM\s+dm_key_material", src, re.I)
    counts = re.findall(r"SELECT\s+COUNT\(\*\)\s+FROM\s+dm_key_material", src, re.I)
    assert reads, "the key table should still be counted for diagnostics"
    assert len(reads) == len(counts), (
        f"{len(reads) - len(counts)} non-COUNT read(s) of dm_key_material"
    )


def test_doctor_reports_diagnostics(db):
    out = db.doctor()
    assert out["conversation_count"] == 4  # doctor counts deleted rows too
    assert out["message_count"] == 5
    assert out["key_material_rows"] == 0
    assert out["database_size"] > 0


# ── discovery against a synthetic profile tree ───────


def _profile_tree(tmp_path, *, with_db=True, name="Default"):
    root = tmp_path / "ChromeRoot"
    fs = root / name / "File System" / "001" / "p"
    fs.mkdir(parents=True)
    if with_db:
        _build_db(fs / "store.sqlite")
    return root


def test_discovery_finds_a_matching_database(tmp_path):
    root = _profile_tree(tmp_path)
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["state"] == "found"
    assert len(out["matches"]) == 1
    match = out["matches"][0]
    assert match["browser"] == "chrome" and match["profile"] == "Default"
    assert match["database_size"] > 0


def test_discovery_ignores_non_xchat_sqlite(tmp_path):
    root = _profile_tree(tmp_path, with_db=False)
    stray = root / "Default" / "File System" / "001" / "p" / "cookies.sqlite"
    con = sqlite3.connect(stray)
    con.execute("CREATE TABLE cookies (host TEXT)")
    con.commit()
    con.close()
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["state"] == "not_found"
    assert out["matches"] == []


def test_discovery_handles_absent_root(tmp_path):
    out = discover_xchat_databases(
        browser="chrome", roots={"chrome": tmp_path / "missing"}
    )
    assert out["state"] == "not_found"
    assert out["errors"] == []


def test_discovery_rejects_unsupported_browser(tmp_path):
    with pytest.raises(XChatUnavailable, match="Unsupported browser"):
        discover_xchat_databases(browser="safari", roots={})


def test_discovery_accepts_browser_aliases(tmp_path):
    root = _profile_tree(tmp_path)
    out = discover_xchat_databases(browser="google-chrome", roots={"chrome": root})
    assert out["requested_browser"] == "chrome"
    assert out["state"] == "found"


def test_discovery_auto_scans_every_configured_root(tmp_path):
    a = _profile_tree(tmp_path / "a")
    b = _profile_tree(tmp_path / "b")
    out = discover_xchat_databases(browser="auto", roots={"chrome": a, "edge": b})
    assert {m["browser"] for m in out["matches"]} == {"chrome", "edge"}


def test_discovery_selects_a_named_profile(tmp_path):
    root = _profile_tree(tmp_path, name="Profile 2")
    out = discover_xchat_databases(
        browser="chrome", profile="Profile 2", roots={"chrome": root}
    )
    assert out["matches"][0]["profile"] == "Profile 2"
    assert out["requested_profile"] == "Profile 2"


# ── resolution to a single path ──────────────────────


def test_resolve_prefers_explicit_path(tmp_path):
    explicit = _build_db(tmp_path / "explicit.sqlite")
    assert resolve_xchat_database_path(explicit, "chrome", None) == explicit.resolve()


def test_resolve_returns_none_without_configuration():
    assert resolve_xchat_database_path(None, None, None) is None


def test_resolve_errors_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "twitter_mcp.xchat.discovery._default_roots",
        lambda: {"chrome": tmp_path / "missing"},
    )
    with pytest.raises(XChatUnavailable, match="No local XChat database"):
        resolve_xchat_database_path(None, "chrome", None)


def test_resolve_errors_on_multiple_matches(tmp_path, monkeypatch):
    a = _profile_tree(tmp_path / "a")
    b = _profile_tree(tmp_path / "b")
    monkeypatch.setattr(
        "twitter_mcp.xchat.discovery._default_roots",
        lambda: {"chrome": a, "edge": b},
    )
    with pytest.raises(XChatUnavailable, match="Multiple local XChat databases"):
        resolve_xchat_database_path(None, "auto", None)


# ── MCP tool layer ───────────────────────────────────
#
# The reader is exercised above; these cover the boundary — env wiring,
# ToolError translation, and the unconfigured path that must stay
# helpful rather than just failing.


@pytest.fixture
def clean_env(monkeypatch):
    for key in ("XCHAT_DATABASE_PATH", "XCHAT_BROWSER", "XCHAT_BROWSER_PROFILE"):
        monkeypatch.delenv(key, raising=False)


async def test_tools_registered_and_documented():
    from twitter_mcp.server import _registered_tools

    tools = _registered_tools()
    for name in ("xchat_status", "xchat_list_conversations", "xchat_get_history"):
        assert name in tools
        assert tools[name].description, f"{name} has no docstring"
    params = tools["xchat_get_history"].parameters
    assert "conversation_id" in params["required"]


async def test_status_unconfigured_reports_discovery(clean_env, monkeypatch, tmp_path):
    """With nothing set the tool must explain what it found, not just fail."""
    monkeypatch.setattr(
        "twitter_mcp.xchat.discovery._default_roots",
        lambda: {"chrome": tmp_path / "absent"},
    )
    from twitter_mcp import server

    out = json.loads(await server.xchat_status())
    assert out["state"] == "not_configured"
    assert "XCHAT_BROWSER" in out["detail"]
    assert out["discovery"]["state"] == "not_found"


async def test_status_with_explicit_path(clean_env, monkeypatch, tmp_path):
    path = _build_db(tmp_path / "x.sqlite")
    monkeypatch.setenv("XCHAT_DATABASE_PATH", str(path))
    from twitter_mcp import server

    out = json.loads(await server.xchat_status())
    assert out["state"] == "ready"
    assert out["conversation_count"] == 3


async def test_list_and_history_through_the_tools(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("XCHAT_DATABASE_PATH", str(_build_db(tmp_path / "x.sqlite")))
    from twitter_mcp import server

    listed = json.loads(await server.xchat_list_conversations())
    assert listed["count"] == 3
    assert listed["conversations"][0]["conversation_id"] == "g-777"

    history = json.loads(await server.xchat_get_history("100-200"))
    assert history["count"] == 2
    assert [m["text"] for m in history["messages"]] == ["hello", "hi back"]
    assert history["conversation_id"] == "100-200"


async def test_unread_only_through_the_tool(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("XCHAT_DATABASE_PATH", str(_build_db(tmp_path / "x.sqlite")))
    from twitter_mcp import server

    out = json.loads(await server.xchat_list_conversations(unread_only=True))
    assert out["count"] == 2


async def test_missing_config_raises_actionable_toolerror(clean_env):
    from mcp.server.mcpserver.exceptions import ToolError

    from twitter_mcp import server

    with pytest.raises(ToolError) as caught:
        await server.xchat_list_conversations()
    message = str(caught.value)
    assert "XCHAT_BROWSER" in message and "XCHAT_DATABASE_PATH" in message
    assert "xchat_status" in message


async def test_reader_errors_become_toolerror_not_tracebacks(
    clean_env, monkeypatch, tmp_path
):
    monkeypatch.setenv("XCHAT_DATABASE_PATH", str(_build_db(tmp_path / "x.sqlite")))
    from mcp.server.mcpserver.exceptions import ToolError

    from twitter_mcp import server

    with pytest.raises(ToolError, match="No local messages"):
        await server.xchat_get_history("nope-nope")


async def test_history_rejects_empty_id_at_the_boundary(clean_env):
    from mcp.server.mcpserver.exceptions import ToolError

    from twitter_mcp import server

    with pytest.raises(ToolError, match="non-empty"):
        await server.xchat_get_history("")


async def test_discovery_failure_surfaces_as_toolerror(
    clean_env, monkeypatch, tmp_path
):
    """A configured browser that yields nothing must say so actionably."""
    monkeypatch.setenv("XCHAT_BROWSER", "chrome")
    monkeypatch.setattr(
        "twitter_mcp.xchat.discovery._default_roots",
        lambda: {"chrome": tmp_path / "absent"},
    )
    from mcp.server.mcpserver.exceptions import ToolError

    from twitter_mcp import server

    with pytest.raises(ToolError, match="No local XChat database"):
        await server.xchat_status()


async def test_env_config_reads_all_three_keys(clean_env, monkeypatch):
    monkeypatch.setenv("XCHAT_DATABASE_PATH", "/tmp/x.sqlite")
    monkeypatch.setenv("XCHAT_BROWSER", "edge")
    monkeypatch.setenv("XCHAT_BROWSER_PROFILE", "Profile 2")
    from twitter_mcp import xchat

    assert xchat.env_config() == {
        "database_path": "/tmp/x.sqlite",
        "browser": "edge",
        "profile": "Profile 2",
    }


async def test_unconfigured_env_yields_no_database(clean_env):
    from twitter_mcp import xchat

    assert xchat.database_from_env() is None


# ── platform defaults and denied-permission paths ────
#
# These are the branches a real user hits and CI otherwise never does:
# the per-OS profile locations, and macOS refusing access until the MCP
# host is granted Full Disk Access. Permission errors are injected rather
# than chmod'ed — the test suite may run as root, where chmod proves
# nothing.


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("darwin", "Library/Application Support/Google/Chrome"),
        ("linux", "google-chrome"),
        ("win32", "Google/Chrome/User Data"),
    ],
)
def test_default_roots_per_platform(monkeypatch, platform, expected):
    import twitter_mcp.xchat.discovery as disco

    monkeypatch.setattr(disco.sys, "platform", platform)
    monkeypatch.setenv("LOCALAPPDATA", "/tmp/AppDataLocal")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    roots = disco._default_roots()
    assert "chrome" in roots
    assert expected.replace("/", "\\") in str(roots["chrome"]).replace("/", "\\")
    # aside is macOS-only; the others ship everywhere Chromium does
    assert ("aside" in roots) is (platform == "darwin")


def test_default_roots_honours_xdg_config_home(monkeypatch, tmp_path):
    import twitter_mcp.xchat.discovery as disco

    monkeypatch.setattr(disco.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert disco._default_roots()["chromium"] == tmp_path / "chromium"


def test_denied_root_is_reported_not_crashed(tmp_path, monkeypatch):
    root = _profile_tree(tmp_path)
    real_stat = Path.stat

    def deny(self, *a, **kw):
        if self == root:
            raise PermissionError(13, "denied")
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(Path, "stat", deny)
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["state"] == "permission_denied"
    assert out["errors"][0]["error"] == "permission_denied"
    assert out["matches"] == []


def test_denied_profile_walk_is_reported(tmp_path, monkeypatch):
    import twitter_mcp.xchat.discovery as disco

    root = _profile_tree(tmp_path)

    def walk_denied(path, onerror=None):
        if onerror:
            onerror(PermissionError(13, "denied"))
        return iter(())

    monkeypatch.setattr(disco.os, "walk", walk_denied)
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["state"] == "permission_denied"


def test_denied_filesystem_dir_is_reported(tmp_path, monkeypatch):
    root = _profile_tree(tmp_path)
    target = root / "Default" / "File System"
    real_stat = Path.stat

    def deny(self, *a, **kw):
        if self == target:
            raise PermissionError(13, "denied")
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(Path, "stat", deny)
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["state"] == "permission_denied"


def test_resolve_reports_denied_access_actionably(tmp_path, monkeypatch):
    import twitter_mcp.xchat.discovery as disco

    root = _profile_tree(tmp_path)
    monkeypatch.setattr(disco, "_default_roots", lambda: {"chrome": root})
    monkeypatch.setattr(
        disco,
        "discover_xchat_databases",
        lambda **kw: {
            "state": "permission_denied",
            "matches": [],
            "errors": [{"error": "permission_denied"}],
        },
    )
    with pytest.raises(XChatUnavailable, match="Full Disk Access"):
        resolve_xchat_database_path(None, "chrome", None)


def test_profile_without_file_system_dir_is_skipped(tmp_path):
    root = tmp_path / "Root"
    (root / "Default").mkdir(parents=True)
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["state"] == "not_found"


def test_file_system_as_a_file_is_skipped(tmp_path):
    root = tmp_path / "Root"
    (root / "Default").mkdir(parents=True)
    (root / "Default" / "File System").write_text("not a directory")
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["state"] == "not_found"


def test_non_sqlite_files_in_a_profile_are_skipped_on_header(tmp_path):
    root = _profile_tree(tmp_path, with_db=False)
    leaf = root / "Default" / "File System" / "001" / "p"
    (leaf / "notes.txt").write_text("hello")
    (leaf / "empty.bin").write_bytes(b"")
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["state"] == "not_found"


def test_unreadable_candidate_is_skipped(tmp_path, monkeypatch):
    import twitter_mcp.xchat.discovery as disco

    root = _profile_tree(tmp_path)
    monkeypatch.setattr(disco, "_schema_matches", lambda p: True)
    real_stat = Path.stat

    def fail_on_leaf(self, *a, **kw):
        if self.name == "store.sqlite":
            raise OSError(5, "I/O error")
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(Path, "stat", fail_on_leaf)
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert out["matches"] == []


def test_explicitly_named_missing_browser_is_skipped(tmp_path):
    """`roots` may omit a browser the caller named — that is not an error."""
    out = discover_xchat_databases(browser="edge", roots={"chrome": tmp_path})
    assert out["state"] == "not_found"
    assert out["matches"] == []


# ── conversation-id shapes ───────────────────────────
#
# The peer id is parsed out of the conversation id, so every id shape X
# uses has to be handled. Getting this wrong mislabels who you are
# talking to.


@pytest.mark.parametrize(
    ("conversation_id", "owner", "expected"),
    [
        ("100-200", "100", "200"),  # owner first
        ("200-100", "100", "200"),  # owner second
        ("200-300", "100", "300"),  # owner absent → last wins
        ("100:200", "100", "200"),  # colon separator
        ("g-777", "100", None),  # group chat has no single peer
        ("weird", "100", None),  # unparseable → no peer, not a crash
        ("1-2-3", "100", None),  # three parts is not a direct chat
    ],
)
def test_direct_peer_id_shapes(conversation_id, owner, expected):
    assert XChatDatabase._direct_peer_id(conversation_id, owner) == expected


def test_group_only_database_resolves_no_screen_names(tmp_path):
    """All-group history must not blow up the name lookup."""
    db = XChatDatabase(
        _build_db(
            tmp_path / "x.sqlite",
            rows=[_entry(conversation_id="g-777", plain_text="group only")],
        )
    )
    listed = db.list_conversations()
    assert [c["conversation_id"] for c in listed] == ["g-777"]
    assert listed[0]["screen_name"] is None
    assert listed[0]["name"] == "Team chat"


def test_corrupt_sqlite_candidate_is_skipped_during_discovery(tmp_path):
    """A file with a valid header but a truncated body must not abort a scan."""
    root = _profile_tree(tmp_path)
    leaf = root / "Default" / "File System" / "001" / "p"
    good = (leaf / "store.sqlite").read_bytes()
    (leaf / "corrupt.sqlite").write_bytes(good[:32])  # header only, no pages
    out = discover_xchat_databases(browser="chrome", roots={"chrome": root})
    assert len(out["matches"]) == 1
    assert Path(out["matches"][0]["database_path"]).name == "store.sqlite"


def test_resolve_uses_the_single_discovered_match(tmp_path, monkeypatch):
    import twitter_mcp.xchat.discovery as disco

    root = _profile_tree(tmp_path)
    monkeypatch.setattr(disco, "_default_roots", lambda: {"chrome": root})
    resolved = resolve_xchat_database_path(None, "chrome", None)
    assert resolved is not None and resolved.name == "store.sqlite"
