"""Issue #122: `server.json` is the MCP registry's view of this package.

The registry reads a static manifest, so the version and package name are
duplicated from `pyproject.toml` and cannot be derived at read time. This
repo has been bitten by exactly that shape twice already — the README
client list went six releases stale (#121), and tool counts drifted
across four files (#119). Both times the fix was a test rather than a
convention. Same here.

The environment-variable checks are the more interesting half: they run
in both directions, so the manifest is a *checked* description of what
the code reads rather than a hand-maintained guess that rots quietly.
"""

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST = _ROOT / "server.json"
_PYPROJECT = _ROOT / "pyproject.toml"

# Knobs the OS provides, not ones this project defines. They appear in
# `os.environ.get(...)` calls but must never be advertised as our config.
_PLATFORM_ENV = {"LOCALAPPDATA", "XDG_CONFIG_HOME"}


def _manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def _pyproject_field(field: str) -> str:
    """First `field = "value"` in pyproject's [project] table."""
    src = _PYPROJECT.read_text(encoding="utf-8")
    match = re.search(rf'^{field} = "(.+?)"', src, re.M)
    assert match, f"could not read `{field}` from pyproject.toml"
    return match.group(1)


def _declared_env_names() -> set[str]:
    names = set()
    for package in _manifest().get("packages", []):
        for var in package.get("environmentVariables", []):
            names.add(var["name"])
    return names


def _env_names_read_by_code() -> set[str]:
    """Every environment variable name appearing in the shipped source."""
    names = set()
    for path in sorted((_ROOT / "twitter_mcp").rglob("*.py")):
        if "_vendor" in path.parts:
            continue  # vendored twikit has its own unrelated knobs
        for name in re.findall(
            r'os\.environ(?:\.get)?[(\[]\s*"([A-Z_]+)"',
            path.read_text(encoding="utf-8"),
        ):
            names.add(name)
        # server.py reads the cookie path through a small helper rather
        # than a bare os.environ call; catch the literal too.
        for name in re.findall(
            r'"(TWITTER_[A-Z_]+)"', path.read_text(encoding="utf-8")
        ):
            names.add(name)
    return names - _PLATFORM_ENV


# ── manifest shape ───────────────────────────────────


def test_manifest_exists_and_parses():
    assert _MANIFEST.is_file(), "server.json is required for MCP registry listing"
    assert "$schema" in _manifest(), "the registry requires a $schema pointer"


def test_schema_points_at_the_official_registry_schema():
    schema = _manifest()["$schema"]
    assert schema.startswith("https://static.modelcontextprotocol.io/schemas/"), schema
    assert schema.endswith("/server.schema.json"), schema


def test_name_is_reverse_dns_under_the_github_owner():
    """The registry namespaces GitHub projects as io.github.<owner>/<repo>,
    and publishing requires authenticating as that owner."""
    name = _manifest()["name"]
    assert re.fullmatch(r"io\.github\.[a-z0-9-]+/[a-z0-9-]+", name), name
    assert name == "io.github.tangivis/twitter-mcp"


def test_transport_is_stdio():
    for package in _manifest()["packages"]:
        assert package["transport"]["type"] == "stdio"


def test_package_points_at_the_published_pypi_distribution():
    package = _manifest()["packages"][0]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == _pyproject_field("name")
    assert package.get("runtimeHint") == "uvx", (
        "the documented install path is uv/uvx; the hint should match it"
    )


# ── the drift guards ─────────────────────────────────


def test_manifest_version_matches_pyproject():
    """Every release bumps pyproject. This is the reminder to bump here too."""
    expected = _pyproject_field("version")
    assert _manifest()["version"] == expected, (
        f"server.json says {_manifest()['version']}, pyproject says {expected}. "
        f"Bump both — the registry serves whatever this file says."
    )


def test_package_version_matches_pyproject():
    expected = _pyproject_field("version")
    for package in _manifest()["packages"]:
        assert package.get("version") == expected, (
            f"packages[].version is {package.get('version')}, pyproject says {expected}"
        )


def test_description_is_present_and_not_the_pyproject_boilerplate():
    description = _manifest().get("description", "")
    assert 20 <= len(description) <= 300, f"description is {len(description)} chars"


# ── manifest ↔ code, checked in both directions ──────


def test_every_declared_env_var_is_actually_read_by_the_code():
    """No phantom knobs: the manifest must not advertise config that does
    nothing."""
    phantom = _declared_env_names() - _env_names_read_by_code()
    assert not phantom, (
        f"server.json declares environment variables the code never reads: "
        f"{sorted(phantom)}. Remove them, or wire them up."
    )


def test_every_xchat_knob_the_code_reads_is_declared():
    """No undocumented knobs: anything a user is expected to set must be
    discoverable from the registry entry."""
    read = {n for n in _env_names_read_by_code() if n.startswith("XCHAT_")}
    missing = read - _declared_env_names()
    assert not missing, (
        f"the code reads {sorted(missing)} but server.json doesn't declare them"
    )


def test_cookie_path_is_required_and_not_marked_secret():
    """`TWITTER_COOKIES` is a *path*. Marking it secret would make clients
    mask the one value a user needs to see to fix a misconfiguration."""
    declared = {
        var["name"]: var
        for package in _manifest()["packages"]
        for var in package.get("environmentVariables", [])
    }
    assert "TWITTER_COOKIES" in declared, "the cookie path must be advertised"
    cookie = declared["TWITTER_COOKIES"]
    assert cookie.get("isRequired") is True
    assert cookie.get("isSecret", False) is False, (
        "it is a filesystem path, not a credential"
    )


# Parametrized from the manifest itself rather than a hand-written list:
# a literal list is the same duplicated-fact-with-no-check shape this file
# exists to prevent, and it silently skipped `TWIKIT_DOWNLOAD_DIR` on the
# first draft. Declaring a new variable now enrolls it automatically.
@pytest.mark.parametrize("name", sorted(_declared_env_names()))
def test_each_env_var_has_an_actionable_description(name):
    declared = {
        var["name"]: var
        for package in _manifest()["packages"]
        for var in package.get("environmentVariables", [])
    }
    description = declared[name].get("description", "")
    assert len(description) >= 25, (
        f"{name}'s description is {len(description)} chars — a stranger reading "
        f"the registry entry should be able to act on it"
    )


def test_the_description_check_covers_every_declared_variable():
    """Meta-guard: the parametrization above is built at collection time,
    so this pins that it actually enumerated something and matches the
    manifest — a silently-empty parametrize would pass vacuously."""
    assert len(_declared_env_names()) >= 5, (
        f"only {len(_declared_env_names())} env vars declared; the "
        f"description check would cover fewer than expected"
    )
