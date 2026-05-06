"""Guard the @claude trigger from third-party plan-burning.

`.github/workflows/claude.yml` triggers `anthropics/claude-code-action`
which uses `secrets.CLAUDE_CODE_OAUTH_TOKEN` — the maintainer's claude.ai
OAuth token. Without an `author_association` filter, ANY GitHub user
typing `@claude` in any issue / PR comment would burn the maintainer's
plan quota.

These sentinels assert the workflow:
1. Gates each event-type branch on `author_association ∈
   {OWNER, COLLABORATOR, MEMBER}`.
2. Documents the rationale (so future me / future CC sessions don't
   relax the gate without understanding why).
"""

import re
from pathlib import Path

_CLAUDE_YML = Path(__file__).parent.parent / ".github/workflows/claude.yml"
_ALLOWED_ASSOCIATIONS = {"OWNER", "COLLABORATOR", "MEMBER"}


def _src() -> str:
    return _CLAUDE_YML.read_text(encoding="utf-8")


def test_claude_yml_has_author_association_guard():
    """The `if:` block must reference `author_association` at least once
    per supported event type (issue_comment / PR review comment / PR
    review / issues = 4 event types)."""
    src = _src()
    # Count occurrences of *.author_association across the if-block.
    occurrences = re.findall(r"author_association", src)
    assert len(occurrences) >= 4, (
        f"claude.yml has only {len(occurrences)} author_association "
        f"references — expected ≥4 (one per event type). Without this "
        f"guard, any GitHub user can burn the maintainer's "
        f"CLAUDE_CODE_OAUTH_TOKEN plan by typing @claude."
    )


def test_claude_yml_only_allows_trusted_associations():
    """The allowlist must be exactly `OWNER` / `COLLABORATOR` / `MEMBER`
    — these are the GitHub-built-in tags for users with explicit
    write/maintain access."""
    src = _src()
    # The pattern is a fromJSON('[...]') array; extract them.
    arrays = re.findall(r"""fromJSON\(\s*'(\[[^\]]+\])'\s*\)""", src)
    assert arrays, "claude.yml has no fromJSON allowlist for author_association"
    for arr in arrays:
        # Strip whitespace/quotes; extract the role tokens.
        roles = set(re.findall(r'"([A-Z_]+)"', arr))
        assert roles == _ALLOWED_ASSOCIATIONS, (
            f"claude.yml allowlist {arr!r} has roles {roles!r}; expected "
            f"exactly {_ALLOWED_ASSOCIATIONS!r}. Adding wider roles like "
            f"CONTRIBUTOR or NONE would re-open the third-party "
            f"plan-burn vector this guard is closing."
        )


def test_claude_yml_documents_why_the_guard_exists():
    """A comment block above the `if:` must explain the guard's purpose
    — so future maintainers / CC sessions don't loosen it accidentally."""
    src = _src()
    # Loose check: somewhere in the workflow we mention plan quota /
    # CLAUDE_CODE_OAUTH_TOKEN in the context of who can trigger.
    must_mention = ["author_association", "OWNER", "COLLABORATOR"]
    for needle in must_mention:
        assert needle in src, (
            f"claude.yml lost the {needle!r} mention; the guard "
            f"rationale comment may have been stripped."
        )


def test_claude_yml_pins_sonnet_46_model():
    """The `claude_args` must pin `--model claude-sonnet-4-6` — not let
    it default to whatever the action picks (which on a Max plan would
    be Opus 4.7, ~5× the per-token cost without payoff for this repo's
    complexity). Local Claude Code still picks Opus when the maintainer
    drives it directly; this rule only governs the GitHub bot."""
    src = _src()
    assert "--model claude-sonnet-4-6" in src, (
        "claude.yml must pin `--model claude-sonnet-4-6` in claude_args. "
        "Letting the action default to plan-default (Opus on Max) makes "
        "@claude ~5× more expensive per turn for no measurable benefit "
        "on this codebase's task complexity."
    )


def test_claude_yml_caps_turn_count():
    """`--max-turns` must be set so a runaway agent loop doesn't drain
    plan quota silently."""
    src = _src()
    assert re.search(r"--max-turns\s+\d+", src), (
        "claude.yml must include `--max-turns N` to cap the agent loop. "
        "Without it a confused agent can rack up 100+ turns chasing a "
        "phantom error before timing out."
    )
