"""Issue #84: download_tweet_video — yt-dlp wrapper for video tweets.

Mock-only: never invoke real yt-dlp / ffmpeg / network. Subprocess and
filesystem are the boundaries; we mock them.

Coverage targets:
- _resolve_download_dir: 3 paths (arg / env / default)
- _cookies_json_to_netscape: write format + missing-key error
- _ytdlp_classify_error: 4 known classes (yt-dlp missing / ffmpeg missing /
  no video / generic)
- _ytdlp_download: argv shape, JSON parse, error paths, cookies cleanup
- download_tweet_video tool: URL extraction, output dir resolution,
  cookies cleanup on failure
"""

import json as _json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from twitter_mcp import server

# ── _resolve_download_dir ───────────────────────────────────────


def test_resolve_download_dir_uses_arg_first(tmp_path, monkeypatch):
    monkeypatch.setenv("TWIKIT_DOWNLOAD_DIR", str(tmp_path / "from-env"))
    out = server._resolve_download_dir(str(tmp_path / "from-arg"))
    assert out == tmp_path / "from-arg"


def test_resolve_download_dir_falls_back_to_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TWIKIT_DOWNLOAD_DIR", str(tmp_path / "from-env"))
    out = server._resolve_download_dir(None)
    assert out == tmp_path / "from-env"


def test_resolve_download_dir_default_when_neither_set(monkeypatch):
    monkeypatch.delenv("TWIKIT_DOWNLOAD_DIR", raising=False)
    out = server._resolve_download_dir(None)
    # Default per issue #84 decision: ~/Downloads/twikit-mcp/
    assert out == Path.home() / "Downloads" / "twikit-mcp"


def test_resolve_download_dir_expands_tilde(monkeypatch):
    monkeypatch.delenv("TWIKIT_DOWNLOAD_DIR", raising=False)
    out = server._resolve_download_dir("~/x/y")
    assert out == Path.home() / "x" / "y"


# ── _cookies_json_to_netscape ───────────────────────────────────


def test_cookies_to_netscape_writes_two_lines(tmp_path):
    cj = tmp_path / "cookies.json"
    cj.write_text(_json.dumps({"ct0": "AAA", "auth_token": "BBB"}), encoding="utf-8")
    out_path = server._cookies_json_to_netscape(cj)
    try:
        contents = out_path.read_text(encoding="utf-8")
        assert "ct0\tAAA" in contents
        assert "auth_token\tBBB" in contents
    finally:
        out_path.unlink(missing_ok=True)


def test_cookies_to_netscape_uses_x_com_domain(tmp_path):
    cj = tmp_path / "cookies.json"
    cj.write_text(_json.dumps({"ct0": "x", "auth_token": "y"}), encoding="utf-8")
    out_path = server._cookies_json_to_netscape(cj)
    try:
        # Every cookie line starts with `.x.com<TAB>`.
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                assert line.startswith(".x.com\t")
    finally:
        out_path.unlink(missing_ok=True)


def test_cookies_to_netscape_raises_on_missing_keys(tmp_path):
    cj = tmp_path / "cookies.json"
    cj.write_text(_json.dumps({"ct0": "only"}), encoding="utf-8")
    with pytest.raises(ToolError, match="missing.*auth_token|missing.*ct0"):
        server._cookies_json_to_netscape(cj)


# ── _ytdlp_classify_error ───────────────────────────────────────


def test_ytdlp_classify_yt_dlp_not_found_via_returncode():
    err = server._ytdlp_classify_error(127, "/bin/sh: yt-dlp: not found\n")
    assert isinstance(err, ToolError)
    assert "uv tool install yt-dlp" in str(err)


def test_ytdlp_classify_ffmpeg_not_found():
    err = server._ytdlp_classify_error(
        1, "ERROR: ffmpeg is not installed. Please install ffmpeg.\n"
    )
    assert isinstance(err, ToolError)
    assert "ffmpeg" in str(err).lower()
    assert "install ffmpeg" in str(err)


def test_ytdlp_classify_no_video_attachment():
    err = server._ytdlp_classify_error(
        1, "ERROR: Unsupported URL: https://x.com/i/status/123 (no video)\n"
    )
    assert isinstance(err, ToolError)
    assert "no video" in str(err).lower()


def test_ytdlp_classify_generic_error():
    err = server._ytdlp_classify_error(2, "ERROR: something else broke\n")
    assert isinstance(err, ToolError)
    assert "exit 2" in str(err) or "yt-dlp failed" in str(err)


# ── _ytdlp_download ──────────────────────────────────────────────


_FAKE_YTDLP_JSON = _json.dumps(
    {
        "id": "1234567890",
        "ext": "mp4",
        "duration": 23.4,
        "width": 1280,
        "height": 720,
        "webpage_url": "https://x.com/jack/status/1234567890",
        "filepath": "/abs/path/to/1234567890.mp4",
    }
)


def _fake_proc(stdout=b"", stderr=b"", returncode=0):
    """Build an AsyncMock subprocess that returns canned bytes."""
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc


async def test_ytdlp_download_argv_shape(tmp_path, monkeypatch):
    """Constructed command must include --cookies, -f, -o template, URL."""
    captured = {}

    async def fake_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        return _fake_proc(stdout=_FAKE_YTDLP_JSON.encode())

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    # Patch Path.stat so the parser doesn't crash on the fake path.
    monkeypatch.setattr(Path, "stat", lambda self: SimpleNamespace(st_size=1234))
    monkeypatch.setattr(Path, "exists", lambda self: True)

    cookies = tmp_path / "cookies.txt"
    cookies.touch()
    out = tmp_path / "videos"
    info = await server._ytdlp_download(
        url="https://x.com/i/status/1234567890",
        cookies_path=cookies,
        output_dir=out,
        format_spec="best[ext=mp4]",
    )
    cmd = captured["cmd"]
    assert cmd[0] == "yt-dlp"
    assert "--cookies" in cmd
    assert str(cookies) in cmd
    assert "-f" in cmd and "best[ext=mp4]" in cmd
    assert "-o" in cmd
    assert any("%(id)s.%(ext)s" in arg for arg in cmd)
    assert "https://x.com/i/status/1234567890" in cmd

    assert info["tweet_id"] == "1234567890"
    assert info["duration_sec"] == 23.4
    assert info["width"] == 1280


async def test_ytdlp_download_parses_print_json(tmp_path, monkeypatch):
    """yt-dlp --print-json stdout → parsed dict shape."""
    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_proc(stdout=_FAKE_YTDLP_JSON.encode())),
    )
    monkeypatch.setattr(Path, "stat", lambda self: SimpleNamespace(st_size=99))
    monkeypatch.setattr(Path, "exists", lambda self: True)

    info = await server._ytdlp_download(
        url="https://x.com/i/status/1234567890",
        cookies_path=tmp_path / "c.txt",
        output_dir=tmp_path / "v",
        format_spec="best[ext=mp4]",
    )
    assert info["path"].endswith("1234567890.mp4")
    assert info["size_bytes"] == 99
    assert info["format"] == "video/mp4"
    assert info["url"] == "https://x.com/jack/status/1234567890"


async def test_ytdlp_download_nonzero_exit_raises_classified_error(
    tmp_path, monkeypatch
):
    """Non-zero rc → _ytdlp_classify_error decides the message."""
    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        AsyncMock(
            return_value=_fake_proc(
                stderr=b"ERROR: Unsupported URL: ...no video\n", returncode=1
            )
        ),
    )
    with pytest.raises(ToolError, match="no video"):
        await server._ytdlp_download(
            url="https://x.com/i/status/1",
            cookies_path=tmp_path / "c.txt",
            output_dir=tmp_path / "v",
            format_spec="best[ext=mp4]",
        )


async def test_ytdlp_download_missing_binary_raises_install_hint(tmp_path, monkeypatch):
    """FileNotFoundError on exec (yt-dlp not on PATH) → ToolError with hint."""

    async def explode(*cmd, **kwargs):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'yt-dlp'")

    monkeypatch.setattr("asyncio.create_subprocess_exec", explode)
    with pytest.raises(ToolError, match="uv tool install yt-dlp"):
        await server._ytdlp_download(
            url="https://x.com/i/status/1",
            cookies_path=tmp_path / "c.txt",
            output_dir=tmp_path / "v",
            format_spec="best[ext=mp4]",
        )


async def test_ytdlp_download_no_json_in_stdout_raises(tmp_path, monkeypatch):
    """yt-dlp succeeded (rc=0) but stdout has no JSON line → ToolError."""
    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_proc(stdout=b"some banner\nnot a json line\n")),
    )
    with pytest.raises(ToolError, match="no JSON output"):
        await server._ytdlp_download(
            url="https://x.com/i/status/1",
            cookies_path=tmp_path / "c.txt",
            output_dir=tmp_path / "v",
            format_spec="best[ext=mp4]",
        )


async def test_ytdlp_download_filepath_fallback_from_id_ext(tmp_path, monkeypatch):
    """When yt-dlp JSON omits filepath/_filename, fall back to id.ext under
    the output_dir."""
    fallback_json = _json.dumps({"id": "555", "ext": "mp4", "duration": 1})
    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_proc(stdout=fallback_json.encode())),
    )
    monkeypatch.setattr(Path, "stat", lambda self: SimpleNamespace(st_size=42))
    monkeypatch.setattr(Path, "exists", lambda self: True)

    info = await server._ytdlp_download(
        url="https://x.com/i/status/555",
        cookies_path=tmp_path / "c.txt",
        output_dir=tmp_path / "out",
        format_spec="best[ext=mp4]",
    )
    assert info["path"].endswith("out/555.mp4")


# ── download_tweet_video (the MCP tool) ─────────────────────────


async def test_download_tweet_video_extracts_id_from_url(tmp_path, monkeypatch):
    """URL form arg → tweet_id extracted via existing helper, used in URL."""
    cookies_json = tmp_path / "cookies.json"
    cookies_json.write_text(
        _json.dumps({"ct0": "x", "auth_token": "y"}), encoding="utf-8"
    )
    monkeypatch.setattr(server, "COOKIES_PATH", cookies_json)

    captured = {}

    async def fake_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        return _fake_proc(stdout=_FAKE_YTDLP_JSON.encode())

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    monkeypatch.setattr(Path, "stat", lambda self: SimpleNamespace(st_size=1))
    monkeypatch.setattr(Path, "exists", lambda self: True)

    out = await server.download_tweet_video(
        tweet_id="https://x.com/jack/status/20",
        output_dir=str(tmp_path / "v"),
    )
    parsed = _json.loads(out)
    # The URL passed to yt-dlp uses the extracted ID.
    assert "https://x.com/i/status/20" in captured["cmd"]
    assert parsed["tweet_id"] == "1234567890"


async def test_download_tweet_video_uses_resolved_dir(tmp_path, monkeypatch):
    """output_dir arg flows to the -o template."""
    cookies_json = tmp_path / "cookies.json"
    cookies_json.write_text(
        _json.dumps({"ct0": "x", "auth_token": "y"}), encoding="utf-8"
    )
    monkeypatch.setattr(server, "COOKIES_PATH", cookies_json)

    captured = {}

    async def fake_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        return _fake_proc(stdout=_FAKE_YTDLP_JSON.encode())

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    monkeypatch.setattr(Path, "stat", lambda self: SimpleNamespace(st_size=1))
    monkeypatch.setattr(Path, "exists", lambda self: True)

    target = tmp_path / "custom-out"
    await server.download_tweet_video(tweet_id="20", output_dir=str(target))
    # -o template starts with the output dir.
    o_idx = list(captured["cmd"]).index("-o")
    template = captured["cmd"][o_idx + 1]
    assert template.startswith(str(target))


async def test_download_tweet_video_cleans_cookies_on_failure(tmp_path, monkeypatch):
    """Even if yt-dlp fails, the temp cookies.txt is unlinked."""
    cookies_json = tmp_path / "cookies.json"
    cookies_json.write_text(
        _json.dumps({"ct0": "x", "auth_token": "y"}), encoding="utf-8"
    )
    monkeypatch.setattr(server, "COOKIES_PATH", cookies_json)

    written_paths = []
    real_to_netscape = server._cookies_json_to_netscape

    def spy(json_path):
        p = real_to_netscape(json_path)
        written_paths.append(p)
        return p

    monkeypatch.setattr(server, "_cookies_json_to_netscape", spy)
    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_proc(stderr=b"ERROR: boom\n", returncode=1)),
    )
    with pytest.raises(ToolError):
        await server.download_tweet_video(tweet_id="20", output_dir=str(tmp_path / "v"))

    assert written_paths, "spy did not capture the cookies.txt path"
    for p in written_paths:
        assert not p.exists(), f"temp cookies.txt {p} not cleaned up"


# ── CLI: `twikit-mcp video` human subcommand ────────────────────


def test_cli_video_subcommand_dispatches_to_download(monkeypatch, capsys):
    """`twikit-mcp video <id>` calls download_tweet_video and prints a
    human-readable summary including the saved path."""
    fake_json = _json.dumps(
        {
            "path": "/tmp/twikit-mcp/1234567890.mp4",
            "size_bytes": 5_242_880,
            "duration_sec": 23.4,
            "format": "video/mp4",
            "width": 1280,
            "height": 720,
            "url": "https://x.com/jack/status/1234567890",
            "tweet_id": "1234567890",
        }
    )
    monkeypatch.setattr(
        server, "download_tweet_video", AsyncMock(return_value=fake_json)
    )
    rc = server.main(["video", "1234567890"])
    assert rc == 0
    out = capsys.readouterr().out
    # Path always shown; size + duration shown human-readably.
    assert "/tmp/twikit-mcp/1234567890.mp4" in out
    # 5_242_880 bytes = 5.0 MB; tolerance for rendering style.
    assert "MB" in out or "5.0 MB" in out
    assert "23" in out  # duration


def test_cli_video_subcommand_passes_output_dir_arg(monkeypatch):
    """`twikit-mcp video <id> -o /custom/dir` flows through."""
    captured = {}

    async def fake_dl(tweet_id, output_dir=None, format=None):
        captured["tweet_id"] = tweet_id
        captured["output_dir"] = output_dir
        return _json.dumps(
            {
                "path": f"{output_dir}/x.mp4",
                "size_bytes": 1,
                "duration_sec": 0,
                "format": "video/mp4",
                "width": 1,
                "height": 1,
                "url": "u",
                "tweet_id": tweet_id,
            }
        )

    monkeypatch.setattr(server, "download_tweet_video", fake_dl)
    rc = server.main(["video", "20", "-o", "/custom"])
    assert rc == 0
    assert captured["output_dir"] == "/custom"


def test_cli_video_subcommand_in_help(monkeypatch, capsys):
    """`twikit-mcp --help` lists the new `video` subcommand."""
    with pytest.raises(SystemExit):
        server.main(["--help"])
    out = capsys.readouterr().out
    assert "video" in out
