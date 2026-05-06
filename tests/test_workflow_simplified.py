"""Workflow-content guards for issue #54 simplification.

The PR pipeline policy (per issue #54): MiniMax review is purely
advisory; CC + maintainer drive merge via mcp__github__merge_pull_request.
The workflow-side auto-merge / auto-summon-@claude steps are removed.

These tests assert the workflow YAML does NOT regrow those steps. If a
future refactor reintroduces them, the failure message names the
specific section so the regression is unambiguous.
"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_PR_REVIEW = _ROOT / ".github/workflows/pr-review.yml"
_CI = _ROOT / ".github/workflows/ci.yml"


# Sentinels: distinctive substrings from the removed steps. We grep for
# these instead of parsing yaml because the failure mode we care about is
# "someone copy-pasted the old step back in", which substring grep catches
# directly.
_AUTO_MERGE_SENTINELS = (
    "gh pr merge --auto --squash",
    "Enable auto-merge",
)
_AUTO_SUMMON_SENTINELS = (
    "Auto-summon @claude",
    "auto_summon_claude.sh",
)
_CI_FAILURE_SENTINELS = (
    "ci-failure-auto-fix",
    "Auto-summon @claude on CI failure",
)


@pytest.mark.parametrize("sentinel", _AUTO_MERGE_SENTINELS)
def test_pr_review_has_no_auto_merge_step(sentinel: str):
    """pr-review.yml must NOT contain the workflow-side auto-merge step.

    Issue #54: merging is the maintainer's call (via
    mcp__github__merge_pull_request). The workflow only posts a review.
    """
    src = _PR_REVIEW.read_text()
    assert sentinel not in src, (
        f"pr-review.yml contains {sentinel!r} — the workflow-side auto-merge "
        f"step is supposed to be removed (issue #54). MiniMax review is "
        f"advisory; CC merges manually."
    )


@pytest.mark.parametrize("sentinel", _AUTO_SUMMON_SENTINELS)
def test_pr_review_does_not_auto_summon_claude(sentinel: str):
    """pr-review.yml must NOT auto-summon @claude on `request-changes`.

    Issue #54: real fixes come from CC reading the review and deciding,
    not from the workflow firing @claude unilaterally.
    """
    src = _PR_REVIEW.read_text()
    assert sentinel not in src, (
        f"pr-review.yml contains {sentinel!r} — auto-summoning @claude "
        f"from this workflow was removed (issue #54). `claude.yml` still "
        f"handles manual @claude mentions; that's the maintainer's lever."
    )


@pytest.mark.parametrize("sentinel", _CI_FAILURE_SENTINELS)
def test_ci_does_not_auto_fix_on_failure(sentinel: str):
    """ci.yml must NOT contain the ci-failure-auto-fix job.

    Issue #54: CI failures surface naturally on the PR; CC decides
    whether to push a fix or close the PR.
    """
    src = _CI.read_text()
    assert sentinel not in src, (
        f"ci.yml contains {sentinel!r} — the auto-fix-on-CI-failure job "
        f"was removed (issue #54). Failures are visible on the PR; the "
        f"maintainer drives any fix."
    )


def test_pr_review_permissions_back_to_contents_read():
    """pr-review.yml shouldn't request `contents: write` anymore.

    With auto-merge removed, the workflow only needs to read the diff
    and post a comment. Tightening back to read.
    """
    src = _PR_REVIEW.read_text()
    # Crude but effective: the perms block should NOT have `contents: write`.
    # `pull-requests: write` is still legitimate (posting the review comment).
    assert "contents: write" not in src, (
        "pr-review.yml requests `contents: write`; that was needed only "
        "for the removed auto-merge step (issue #54). Back to `contents: read`."
    )


def test_pr_review_still_runs_minimax_review():
    """Sanity: the productive part of pr-review.yml is intact.

    We removed *only* the auto-merge / auto-summon steps. MiniMax must
    still be called and its review posted as a PR comment.
    """
    src = _PR_REVIEW.read_text()
    assert "MiniMax M2 review" in src, "pr-review.yml job name lost"
    assert "https://api.minimaxi.com" in src, "pr-review.yml lost the MiniMax call"
    assert "gh pr comment" in src, "pr-review.yml lost the comment-post step"


def test_ci_still_runs_lint_test_protocol():
    """Sanity: the productive part of ci.yml is intact."""
    src = _CI.read_text()
    for job in ("Lint & Format", "Test (Python", "MCP Protocol Check"):
        assert job in src, f"ci.yml lost the {job!r} job"
