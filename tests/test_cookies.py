"""Tests for cookie loading via _get_client()."""

import json

import pytest

from twitter_mcp import server


@pytest.fixture
def cookies_file(tmp_path, monkeypatch):
    """Return a factory that writes cookie data to a temp file and points
    server.COOKIES_PATH at it."""

    def _write(content: str | None = None, *, absent: bool = False):
        path = tmp_path / "cookies.json"
        if not absent:
            path.write_text(content if content is not None else "")
        monkeypatch.setattr(server, "COOKIES_PATH", path)
        return path

    return _write


async def test_get_client_reads_cookies_and_sets_them(cookies_file, monkeypatch):
    cookies_file(
        json.dumps({"auth_token": "abc123", "ct0": "def456", "extra": "ignored"})
    )

    captured = {}

    class FakeClient:
        def __init__(self, lang):
            captured["lang"] = lang

        def set_cookies(self, cookies):
            captured["cookies"] = cookies

    monkeypatch.setattr(server, "Client", FakeClient)

    client = await server._get_client()

    assert isinstance(client, FakeClient)
    assert captured["lang"] == "en"
    # Only auth_token and ct0 forwarded — "extra" is dropped.
    assert captured["cookies"] == {"auth_token": "abc123", "ct0": "def456"}


async def test_get_client_raises_when_file_missing(cookies_file):
    cookies_file(absent=True)
    with pytest.raises(FileNotFoundError):
        await server._get_client()


async def test_get_client_raises_on_malformed_json(cookies_file):
    cookies_file("{this is not json")
    with pytest.raises(json.JSONDecodeError):
        await server._get_client()


@pytest.mark.parametrize("missing", ["auth_token", "ct0"])
async def test_get_client_raises_when_required_key_missing(cookies_file, missing):
    full = {"auth_token": "a", "ct0": "c"}
    del full[missing]
    cookies_file(json.dumps(full))
    with pytest.raises(KeyError) as exc:
        await server._get_client()
    assert missing in str(exc.value)
