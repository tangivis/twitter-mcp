"""Issue #60 guard: pr-review.yml carries the v2 prompt + schema + ladder.

These tests assert the workflow YAML contains the specific instructions
and structures specified in #60. They're sentinel-grep style (same
pattern as `tests/test_workflow_simplified.py`) — they prevent
regressions where someone copy-pastes the old prompt back in.

Three layers:

1. Prompt content (false-positive guards, Conventional Comments labels,
   grounding cheat sheet entries, few-shot blocks, self-critique pass,
   max-must-fix-per-kloc cap).
2. Schema content (Conventional Comments severity enum in JSON shape).
3. Ladder content (Sonnet escalation branch + iteration counter logic).
"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_PR_REVIEW = _ROOT / ".github/workflows/pr-review.yml"


# ── 1. Prompt content guards ─────────────────────────


_PROMPT_RULES = [
    # Hard rule: empty arrays are correct outputs.
    "Empty arrays are correct",
    # Hard rule: max 1 must_fix per kloc.
    "1 must_fix per 1000 lines",
    # Hard rule: don't speculate on what's not in the diff.
    "If you can't verify",
]


@pytest.mark.parametrize("rule", _PROMPT_RULES)
def test_pr_review_prompt_has_hard_rules(rule):
    """The prompt must include explicit anti-false-positive instructions
    (issue #60 acceptance: 'reduce false positives')."""
    src = _PR_REVIEW.read_text()
    assert rule in src, (
        f"pr-review.yml prompt missing hard rule {rule!r}. Issue #60 "
        f"requires explicit anti-false-positive instructions; without "
        f"this exact phrase the model defaults to bikeshed-finding mode."
    )


_CONVENTIONAL_COMMENTS_LABELS = (
    "must_fix",
    "issue",
    "suggestion",
    "nitpick",
    "praise",
    "question",
)


@pytest.mark.parametrize("label", _CONVENTIONAL_COMMENTS_LABELS)
def test_prompt_advertises_conventional_comments_labels(label):
    """The schema describes a single `items` array where each element
    has a `severity` from the Conventional Comments vocabulary."""
    src = _PR_REVIEW.read_text()
    assert label in src, (
        f"pr-review.yml prompt doesn't mention severity label {label!r}. "
        f"Issue #60 standardises on Conventional Comments labels for "
        f"the LLM to pick from."
    )


_GROUNDING_ENTRIES = [
    # i18n suffix-mode misunderstanding (caused PR #57 false positive)
    "i18n suffix mode",
    # snippets directive misunderstanding
    "pymdownx.snippets",
    # test fixture-shape rule
    "test_fixture_shapes",
    # typed-error pattern
    "TooManyRequests",
    # Workflow GITHUB_TOKEN cascade trap
    "GITHUB_TOKEN",
]


@pytest.mark.parametrize("entry", _GROUNDING_ENTRIES)
def test_prompt_includes_grounding_cheat_sheet(entry):
    """The prompt must include the 'easy false positive' cheat sheet —
    repo-specific gotchas the model would otherwise speculate about."""
    src = _PR_REVIEW.read_text()
    assert entry in src, (
        f"pr-review.yml prompt missing grounding entry {entry!r}. "
        f"This entry corresponds to a real false-positive class we've "
        f"seen in past reviews; without it the model can't reason about "
        f"the convention."
    )


def test_prompt_includes_few_shot_examples():
    """At least one good and one bad review example are inlined in the
    prompt (calibration > rules)."""
    src = _PR_REVIEW.read_text()
    # Each example is wrapped in a marker we control.
    assert "<example_good_review>" in src, "good few-shot example missing"
    assert "<example_noisy_review>" in src, "bad/noisy few-shot example missing"


def test_prompt_includes_self_critique_step():
    """The workflow has a second pass where M2 critiques its own first
    review (drops items it can't justify on second look)."""
    src = _PR_REVIEW.read_text()
    assert "self-critique" in src.lower() or "Self-critique" in src
    # The second call must happen — look for the second curl to MiniMax.
    assert src.count("api.minimaxi.com") >= 2, (
        "pr-review.yml only calls MiniMax once; self-critique pass "
        "requires a second call with the first review as input."
    )


# ── 2. Schema (items[] with severity) ────────────────


def test_prompt_schema_is_items_array():
    """Schema asks for a single `items[]` (not separate `must_fix[]` /
    `suggestions[]` / `nits[]`) — Conventional Comments style."""
    src = _PR_REVIEW.read_text()
    assert '"items"' in src, "schema must use a single `items[]` field"
    # Old multi-bucket schema must be GONE.
    for legacy_field in ('"must_fix":', '"suggestions":', '"nits":'):
        assert legacy_field not in src, (
            f"legacy multi-bucket schema field {legacy_field!r} still "
            f"present in prompt — issue #60 collapses these into a "
            f"single `items[]` with `severity` per item."
        )


def test_prompt_schema_includes_file_and_line():
    """Each item carries `file` + `line` so we can post inline-anchored
    review comments via the GitHub Review API."""
    src = _PR_REVIEW.read_text()
    assert '"file"' in src
    assert '"line"' in src


# ── 3. Sonnet escalation ladder ──────────────────────


def test_workflow_has_sonnet_escalation_branch():
    """After 5 MiniMax request-changes iterations on the same PR, the
    6th review uses Sonnet 4.6 via the existing OAuth token."""
    src = _PR_REVIEW.read_text()
    assert "claude-sonnet-4-6" in src, "Sonnet 4.6 model id missing"
    assert "api.anthropic.com" in src, "Anthropic Messages API endpoint missing"
    assert "CLAUDE_CODE_OAUTH_TOKEN" in src, "Sonnet branch must use OAuth token"


def test_workflow_counts_review_iterations():
    """A `<!-- review-iter -->` marker is embedded in each review post,
    and the workflow greps for its count to decide when to escalate."""
    src = _PR_REVIEW.read_text()
    assert "review-iter" in src, "iteration marker missing"
    # Some form of count-comparison-against-5 must exist.
    # We allow several forms; just check 'iter' appears alongside a comparison.
    assert any(form in src for form in ("-ge 5", ">= 5", "== 5", "iter=5"))


def test_workflow_files_needs_human_issue_on_sonnet_fail():
    """If Sonnet ALSO returns request-changes, the workflow opens a
    `needs-human` issue documenting the deadlock and stops reviewing."""
    src = _PR_REVIEW.read_text()
    assert "needs-human" in src, "needs-human label / issue path missing"


# ── 4. Inline review comments via PR Review API ──────


def test_workflow_posts_inline_review_via_pr_review_api():
    """Replaces the single `gh pr comment` with the GitHub Pull Request
    Review API, which supports `comments[]` anchored to file:line."""
    src = _PR_REVIEW.read_text()
    assert "/pulls/" in src and "/reviews" in src, (
        "pr-review.yml doesn't call the GH PR Review API "
        "(/repos/.../pulls/<num>/reviews). Issue #60 requires inline "
        "code-anchored comments."
    )


def test_workflow_keeps_summary_as_top_level_comment():
    """The issue-level summary stays as a single PR comment (it's not
    file-anchored). Only `items[]` go inline."""
    src = _PR_REVIEW.read_text()
    # gh pr comment OR equivalent issue-comment API call must still exist.
    assert "gh pr comment" in src or "issues/" in src, (
        "Summary must still post as a top-level PR comment so the "
        "iteration marker + decision are visible at-a-glance."
    )
