"""Issue #124: the review workflow must survive an unreachable LLM API.

Run #141 died with `curl: (28) ... 0 bytes received` and turned an
already-approved PR red. The workflow *has* a warn-and-skip handler, but
GitHub Actions runs `run:` blocks under `bash -e`, so a non-zero curl
exit kills the script at the assignment line — before the handler is
reached. It only ever covered "curl succeeded, HTTP != 200", which is the
less likely failure.

Testing approach
----------------

These tests extract the `run:` block **straight out of pr-review.yml**
and execute it under bash with a stub `curl` on PATH. That matters: a
test that reimplemented the logic could pass while CI still broke. Here
the shell under test is the shell CI runs.

`jq` and `bash` are required; the tests skip rather than fail where they
are unavailable, so this suite stays honest on a bare Windows runner.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = _ROOT / ".github" / "workflows"
_PR_REVIEW = _WORKFLOWS / "pr-review.yml"

pytestmark = pytest.mark.skipif(
    not (shutil.which("bash") and shutil.which("jq")),
    reason="needs bash + jq to execute the extracted workflow snippet",
)


def _extract_run_block(step_id: str) -> str:
    """The literal shell of the step with `id: <step_id>`.

    Parsed rather than hand-copied so the test can't drift from the file.
    """
    src = _PR_REVIEW.read_text(encoding="utf-8")
    anchor = src.index(f"id: {step_id}")
    run_at = src.index("run: |", anchor)
    body_start = src.index("\n", run_at) + 1

    lines = []
    for line in src[body_start:].splitlines():
        if line.strip() and not line.startswith(" " * 10):
            break  # dedented past the block → next step
        lines.append(line[10:] if len(line) > 10 else "")
    assert lines, f"could not extract the run block for id: {step_id}"
    return "\n".join(lines)


def _run_snippet(tmp_path: Path, *, curl_exit: int, curl_stdout: str = "") -> tuple:
    """Execute the extracted review-call shell with a stubbed curl.

    Mirrors the runner: `bash -e`, the same env the step declares, and a
    real $GITHUB_OUTPUT file.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "curl"
    # The stub also honours `-o <file>`, so `head -c` on the response has
    # something to read — matching what real curl leaves behind.
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "out=''\n"
        "while [ $# -gt 0 ]; do\n"
        '  if [ "$1" = "-o" ]; then out="$2"; shift; fi\n'
        "  shift\n"
        "done\n"
        f'[ -n "$out" ] && printf \'%s\' \'{{"stub":"body"}}\' > "$out"\n'
        f"printf '%s' '{curl_stdout}'\n"
        f"exit {curl_exit}\n"
    )
    stub.chmod(0o755)

    (tmp_path / "prompt.txt").write_text("review this diff please")
    github_output = tmp_path / "github_output"
    github_output.touch()

    env = dict(
        os.environ,
        PATH=f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
        GITHUB_OUTPUT=str(github_output),
        K="stub-minimax-key",
        A="stub-anthropic-key",
        ESCALATE="false",
    )
    proc = subprocess.run(
        ["bash", "-e", "-c", _extract_run_block("call")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, github_output.read_text()


# ── the regression: curl itself fails ────────────────


@pytest.mark.parametrize(
    ("curl_exit", "label"),
    [(28, "timeout"), (6, "could not resolve host"), (7, "connection refused")],
)
def test_curl_failure_degrades_instead_of_failing_the_pr(tmp_path, curl_exit, label):
    """An unreachable LLM must produce a warning and a clean exit.

    This is the exact shape of run #141: connection made, nothing
    returned, curl exits 28 under `bash -e`.
    """
    proc, outputs = _run_snippet(tmp_path, curl_exit=curl_exit)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, (
        f"curl exit {curl_exit} ({label}) failed the step instead of skipping "
        f"the review.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "::warning::" in combined, f"no warning emitted for {label}"
    assert "http=" in outputs, "the downstream http guard needs a defined value"


def test_a_failed_call_never_reports_http_200(tmp_path):
    """Downstream steps gate on `steps.call.outputs.http == '200'`. A
    failed call must not accidentally satisfy that."""
    _, outputs = _run_snippet(tmp_path, curl_exit=28)
    http_values = re.findall(r"^http=(.*)$", outputs, re.M)
    assert http_values, "no http output written at all"
    assert http_values[-1].strip() != "200", (
        "a failed curl reported http=200; the critique and post steps would run "
        "against a body that was never fetched"
    )


# ── the case that already worked, pinned ─────────────


def test_non_200_response_still_degrades(tmp_path):
    """curl succeeds, API returns 500 — the path the author did handle."""
    proc, outputs = _run_snippet(tmp_path, curl_exit=0, curl_stdout="500")
    assert proc.returncode == 0
    assert "::warning::" in proc.stdout + proc.stderr
    assert "http=500" in outputs


def test_happy_path_does_not_warn(tmp_path):
    proc, outputs = _run_snippet(tmp_path, curl_exit=0, curl_stdout="200")
    assert proc.returncode == 0, proc.stderr
    assert "::warning::" not in proc.stdout + proc.stderr
    assert "http=200" in outputs
    assert "model=minimax" in outputs


# ── static guards, so a new call site can't regress ──


def test_every_curl_capture_in_every_workflow_tolerates_failure():
    """A bare `x=$(curl ...)` under `bash -e` must not abort the step.

    Checked across all workflows, not just pr-review.yml — the first run of
    this test found the same latent bug in issue-triage.yml, which had not
    failed yet.

    Piped captures — `x=$(curl ... | jq ...)` — are exempt *only* in
    workflows that don't set `pipefail`. GitHub's default shell is
    `bash -e` without `-o pipefail`, so there a pipeline's status comes
    from its last command and a failing curl at the head merely yields an
    empty value. That is safe by accident, not by design, so the exemption
    is decided per file: `live-smoke.yml` does set `pipefail`, and piped
    captures there would abort like any other.
    """
    # `[^)]*` spans the backslash-continued lines; the trailing `[^\n]*`
    # captures any `|| ...` guard following the closing paren.
    capture_re = re.compile(r"(\w+)=\$\(\s*curl\b[^)]*\)[^\n]*")
    offenders = []
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        src = workflow.read_text(encoding="utf-8")
        pipefail = "pipefail" in src
        for match in capture_re.finditer(src):
            command = match.group(0)
            piped = "|" in command.split(")")[0].replace("||", "")
            tolerant = "|| " in command or "curl_status" in command
            if tolerant or (piped and not pipefail):
                continue
            offenders.append(
                f"{workflow.name}: {match.group(1)}=$(curl ...)"
                + (
                    " [pipefail is set, so the pipeline does not protect it]"
                    if piped
                    else ""
                )
            )
    assert not offenders, (
        "these curl captures abort the step on a network failure instead of "
        "degrading (issue #124):\n  " + "\n  ".join(offenders)
    )


# ── the duplicate-review trigger ─────────────────────


def test_ready_for_review_is_still_a_trigger():
    """Deliberately kept: an outside contributor flipping a draft to ready
    wants a review then. The duplicate is fixed by deduping on head SHA,
    not by dropping the event (issue #124)."""
    src = _PR_REVIEW.read_text(encoding="utf-8")
    types_line = re.search(r"types:\s*\[(.*?)\]", src)
    assert types_line, "could not find the pull_request types list"
    assert "ready_for_review" in types_line.group(1)


def test_a_duplicate_review_for_the_same_sha_is_skipped():
    """The guard that makes `ready_for_review` cheap: if a review already
    landed for this head SHA, don't spend another API call on it."""
    src = _PR_REVIEW.read_text(encoding="utf-8")
    assert "already reviewed" in src.lower() or "duplicate" in src.lower(), (
        "no same-SHA dedupe guard found; every draft→ready flip will spend "
        "a redundant review call (issue #124)"
    )
