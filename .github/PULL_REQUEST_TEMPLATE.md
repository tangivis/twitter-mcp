## Summary

<!-- 1–3 sentences: what this PR does and why. Bot-opened PRs from
auto-fix loops should reference the triggering issue/comment. -->

## Test plan

<!-- What would convince a reviewer it works? Be concrete. -->

- [ ] All existing tests pass (`uv run pytest -q`).
- [ ] `twitter_mcp/server.py` coverage stays at 100% (`--cov-fail-under=95`).
- [ ] `ruff format` + `ruff check` clean.

## Spec / SDD checklist

(Skip a section if not applicable. Marking the boxes is the contract — leaving them blank tells the reviewer you skipped on purpose.)

- [ ] **New / changed MCP tool?** Tool docstring states args + output JSON shape + which `twikit` method backs it + which typed errors are translated.
- [ ] **Test fixture changed?** New / renamed attributes on `_fake_*` factories match the real `twikit` model — `tests/test_fixture_shapes.py` will catch drift, but please double-check before pushing.
- [ ] **Vendor-tree patch?** Carries `# twitter-mcp patch (issue #N)` marker AND a row in `docs/VENDORING.md` "本地 patch 清单" table.
- [ ] **New live-smoke target?** Added a validator in `.github/workflows/live-smoke.yml` that's shape-only (don't assert `len > 0` if X may legitimately gate the burner).
- [ ] **Tool count changed?** Bumped the count in `tests/test_vendor.py::test_server_still_works` AND in `README.md` / `docs/TECHNICAL.md` / `docs/VENDORING.md` / `CONTRIBUTING.md` references.

## Closes / refs

<!-- Issue / PR refs — `closes #N`, `refs #N`, links to live-smoke runs, etc. -->

---

<!--
Auto-fix-loop note for bot-opened PRs: the auto-summon comment will
include `<!-- auto-fix-iter -->` as a marker. The 5-iteration cap counts
those markers; after 5, the loop escalates to a `needs-human` issue
and stops summoning. See PR #43 for the design.
-->
