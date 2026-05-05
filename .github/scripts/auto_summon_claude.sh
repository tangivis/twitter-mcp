#!/usr/bin/env bash
# Auto-summon @claude on a PR with iteration cap + escalation.
#
# Used by:
#   - pr-review.yml when MiniMax decision is "request-changes"
#   - ci.yml when any required check fails on a PR
#
# Logic:
#   - Counts existing comments on the PR matching the marker
#     `<!-- auto-fix-iter -->`. That's iteration N (already attempted).
#   - If N+1 ≤ MAX_ITER (5): post `@claude please fix (iter N+1/MAX)` with
#     `body_extra` (the failure context) appended, plus the marker comment.
#   - If N+1 > MAX_ITER: open a tracking issue with the same context, post
#     a non-summoning comment on the PR explaining the cap was hit, and
#     stop (no more @claude on this PR).
#
# Required env:
#   GH_TOKEN        — Bearer token (workflow secrets.GITHUB_TOKEN)
#   REPO            — owner/repo
#   PR_NUM          — PR number
#   REASON          — short label for the trigger ("MiniMax review",
#                     "Lint & Format", "Test (ubuntu)", …)
#   BODY_FILE       — path to a markdown file with the full failure context
#                     (review body, CI log excerpt, etc.). Pasted verbatim.
#
# Optional env:
#   MAX_ITER        — default 5

set -euo pipefail

: "${GH_TOKEN:?}"
: "${REPO:?}"
: "${PR_NUM:?}"
: "${REASON:?}"
: "${BODY_FILE:?}"
MAX_ITER="${MAX_ITER:-5}"

MARKER="<!-- auto-fix-iter -->"

api() {
  curl -sS \
    -H "Authorization: Bearer $GH_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "$@"
}

# Count prior auto-summons by greping the marker in PR comments. We page
# up to 200 comments — far more than any sane PR ever needs.
prior=$(api "https://api.github.com/repos/$REPO/issues/$PR_NUM/comments?per_page=100" \
        | jq -r '.[].body' \
        | grep -cF "$MARKER" || true)
next=$((prior + 1))

if [ ! -s "$BODY_FILE" ]; then
  echo "::warning::BODY_FILE ($BODY_FILE) is empty; nothing to post."
  exit 0
fi

if [ "$next" -le "$MAX_ITER" ]; then
  # Build the @claude summon comment.
  jq -nc \
    --arg marker "$MARKER" \
    --arg reason "$REASON" \
    --arg n "$next" \
    --arg max "$MAX_ITER" \
    --rawfile body "$BODY_FILE" \
    '{body: ($marker + "\n\n@claude auto-fix iteration \($n)/\($max) — triggered by **\($reason)**.\n\nPlease address the feedback below by pushing a fix to this branch (TDD: red regression test → green fix → ensure all 480+ tests stay green and `--cov-fail-under=95`). After your push, the workflows re-run automatically; if the next review/CI is clean, the PR auto-merges. If you cannot fix this in one round, leave a comment explaining why instead of pushing a half-finished change.\n\n---\n\n\($body)")}' \
    > /tmp/summon.json

  api -X POST \
    -d @/tmp/summon.json \
    "https://api.github.com/repos/$REPO/issues/$PR_NUM/comments" \
    -o /dev/null \
    -w "Posted @claude summon (iter $next/$MAX_ITER) → HTTP %{http_code}\n"
  exit 0
fi

# Cap hit. Open escalation issue + post non-summoning explainer.
echo "Auto-fix cap reached ($prior prior summons, MAX=$MAX_ITER). Escalating."

jq -nc \
  --arg pr "$PR_NUM" \
  --arg reason "$REASON" \
  --arg max "$MAX_ITER" \
  --rawfile body "$BODY_FILE" \
  '{
    title: "Auto-fix cap hit on PR #\($pr) — needs human review",
    body: "Auto-fix loop on **PR #\($pr)** reached the iteration cap (**\($max)/\($max)**) without going green. The bot has stopped pushing fixes; a maintainer needs to look.\n\nLast trigger: **\($reason)**\n\n---\n\n\($body)\n\n---\n\nSee PR #\($pr) for the full conversation and prior auto-fix attempts.",
    labels: ["ci", "needs-human"]
  }' > /tmp/issue.json

issue_url=$(api -X POST \
  -d @/tmp/issue.json \
  "https://api.github.com/repos/$REPO/issues" \
  | jq -r '.html_url // ""')

# Post a non-summoning explainer on the PR (no `@claude`, just info).
jq -nc \
  --arg url "$issue_url" \
  --arg max "$MAX_ITER" \
  --arg reason "$REASON" \
  '{body: "🛑 Auto-fix cap reached (\($max)/\($max)). Last trigger: **\($reason)**.\n\nEscalated to: \($url)\n\nNo more @claude summons will fire on this PR; a human maintainer needs to inspect."}' \
  > /tmp/explain.json

api -X POST \
  -d @/tmp/explain.json \
  "https://api.github.com/repos/$REPO/issues/$PR_NUM/comments" \
  -o /dev/null \
  -w "Posted escalation explainer → HTTP %{http_code}\n"
