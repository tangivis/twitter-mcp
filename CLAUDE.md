# CLAUDE.md — repo-specific conventions for Claude Code sessions

This file is read by Claude Code when a session starts in this repo. It captures
**non-obvious conventions** the maintainer has explicitly chosen, so any future
session (or sub-agent) immediately knows the local rules without re-deriving
them from chat history.

Out of scope here: things already documented in `README.md` (install + usage),
`CONTRIBUTING.md` (test strategy, CI structure), `docs/TECHNICAL.md` (architecture).

---

## Merge policy — zero-confirmation when checks are green

When you (Claude Code) open a PR via `mcp__github__create_pull_request` and the
follow-up CI runs land, **act on the result without prompting the maintainer**:

| Condition | Action |
|---|---|
| CI 6/6 green AND MiniMax review decision is `approve` OR `comment` | **Immediately call `mcp__github__merge_pull_request` (squash).** Don't ask. |
| CI 6/6 green AND review decision is `request-changes` | Read the review's `must_fix` items. Push fixes for the real ones, skip false-positives. Trigger a new review iteration. |
| CI red | Inspect the failing job, push a fix. Don't ask. |
| MiniMax can't converge after 5 iterations | The `pr-review.yml` workflow auto-escalates to Sonnet 4.6 (issue #60). If Sonnet also blocks, it opens a `needs-human` issue — at that point ping the maintainer. |

You merge through the user's MCP-authenticated path (their token, not workflow
GITHUB_TOKEN), so the resulting `push: main` cascades to `publish.yml` and
`docs.yml` automatically. No PAT needed (issue #54).

**Only prompt the maintainer when:**
- The MiniMax review is genuinely ambiguous (you can't tell true from false positive)
- The PR changes user-facing public API surface (PyPI version, MCP tool schema, etc.)
- A workflow fails in a way you haven't seen before (novel error class)
- The maintainer explicitly says "wait for me" / "I'll merge"

The instinct to "ask before merging" is wrong here. The maintainer has already
delegated this decision via #54's pipeline simplification + repeated explicit
agreement. Asking again per-PR is friction without value.

---

## Spec-first workflow

Per the maintainer's emphasized SDD/TDD pattern:

1. Open an issue with the spec (problem, acceptance criteria, design, out-of-scope, TDD plan).
2. Branch + write red tests first.
3. Implement; verify green.
4. Open PR referencing the issue (`closes #N`).
5. PR runs through review + CI; merge per the policy above.

For genuinely tiny changes (one-line typo fix, dependency bump) the issue step
is acceptable to skip — but document the trade-off in the PR body. The maintainer
called this out in late conversation: "issue → spec → SDD → TDD" is the bar.

---

## Review labels (Conventional Comments-derived)

`pr-review.yml` uses these severity labels (issue #60). Treat them at face value:

| Label | Meaning | What to do |
|---|---|---|
| `must_fix` | Real bug, security hole, broken contract | Caps merge until fixed |
| `issue` | Design problem worth discussing | Discuss; usually fix |
| `suggestion` | Improvement, not blocking | Apply if cheap; skip if not |
| `nitpick` | Style/wording/naming | Skip-without-explanation OK |
| `praise` | Well-done point | Read; no action |
| `question` | Reviewer doesn't understand | Reply; no code change unless ambiguity is real |

The MiniMax review on this repo is **advisory** — the maintainer (you) makes the
call. False-positives are common; trust your judgment over the model's.

---

## Other repo-local conventions worth knowing

These are documented elsewhere but easy to miss:

- **`json.dumps` is renamed `_dumps()`** repo-wide — always `ensure_ascii=False`.
- **Test fakes** in `tests/test_tools.py` MUST mirror real twikit model attributes
  — `tests/test_fixture_shapes.py` enforces this (issue #37 was caused by drift).
- **Vendor patches** in `twitter_mcp/_vendor/twikit/` carry `# twitter-mcp patch
  (issue #N)` markers AND are logged in `docs/VENDORING.zh.md` patch table.
- **Coverage gate**: `--cov-fail-under=95` on `twitter_mcp/server.py`. New
  branches without tests fail CI.
- **i18n suffix mode**: `mkdocs-static-i18n` rewrites `cli.md` → `cli.<locale>.md`.
  Don't claim missing files inside `docs/` without checking the suffix variants.
- **Docs auto-generation**: `scripts/gen_api_docs.py` writes `docs/api.md` and
  `docs/_cli_tools.{en,zh,ja}.md` at every build (gitignored).

---

## Branch / PR hygiene

- Branch names: `claude/<short-task-name>` (e.g. `claude/cli-cards-issue-61`).
- One PR per issue when possible. Squash-merge always. Auto-delete head branches
  is enabled at the repo level — branches vanish on merge.
- PR body should reference the issue (`closes #N`) and include the spec/SDD
  checklist (PR template prompts for it).
