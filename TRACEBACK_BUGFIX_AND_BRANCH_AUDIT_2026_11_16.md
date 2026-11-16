# GRAFT-CKG branch review — traceback resolution and source extents

Date: 2026-11-16. Baseline: `krishna` at source-reported commit `642245cb719d5381ca246f8674b72f6399b00df5`. Review branch: `fix-pytest-frame-resolution-audit-2026-11-16`.

## Reported defect and root cause

Input: `2026-11-16-pytest-trace-frames-not-resolved.md` (SOP pilot).

- A pytest short traceback `microservices/rest-api/utils/auth_utils.py:68: in verify_token` yielded zero code nodes.
- The resolver consumed only the `file.py:68` part; the native Python traceback parser handled `File "...", line 68, in verify_token` separately.
- Python AST declarations stored `line_no=61` with no `line_end`, so generic body-line matching stopped at the declaration.
- No match caused graph guidance to disappear, while a Python-style stack frame for the same function still worked.

## Changes

1. `contracts/stack_frames.py`: explicit regex grammars for Python native traceback, pytest short format, Java stack frames, and generic Go/JavaScript/TypeScript/Python file:line; avoids parsing a specific frame a second time with a weak generic pattern; preserves original stack order.
2. `contracts/sckg_provider.py`: use the structured frame parser; prefer explicitly matching service, complete path suffix and in-range function declaration; for line-only frames choose the shortest enclosing function span (nested scopes); avoid ambiguous filename-only collisions across services. No service guess if a parseable frame remains unresolved.
3. `graft_ckg.py`: store inclusive Python AST `end_lineno` for functions (including async and nested) and classes.
4. `polyglot.py`: store inclusive Tree-sitter function extents (end point is exclusive), enabling line-only body frames from Go/JS/TS/Java.
5. `tests/test_pytest_traceback_resolution.py`: exact reported pytest path/name/lines, Windows and native tracebacks, Python/Go incremental equality after edits, TypeScript and Java body line, multiple service basename collisions and negative controls.

## Reproduction limitations

The pilot repository `Vikas-Personal-Research-Org/python-test-repo` at `163f2bee9dcdcd84fb98947177a74c8cd7d19c72` returned GitHub 404 to the current connector. The regression recreates its reported 61–68 function span and matching source path, but **does not** claim successful execution on that exact repository checkout.

## Verified GitHub Actions

Workflow: `.github/workflows/traceback-regression-review.yml`.

Latest green run on source commit `c2d4464500e09628e2d6a5e9fbdbee9e02ae3e0f`:
- Focused traceback, provider and SOP regression tests: **49 passed**.
- Full repository suite executed twice: **310 passed, 3 skipped** per run.
- Critical static Python lint: `ruff check --select E9,F63,F7,F82 .` passed.
- Repository-wide Python `compileall -q .` passed.
- Pinned DataHub `datahub-actions/src` real-source incremental vs fresh graph equivalence: **2/2**.
- `bench/run_paper_accuracy.py` closed-scope polyglot API and seven-relation fixture checks: both passed.

This is stronger than a single targeted unit test, but cannot prove no other defects exist. In particular, exact original private-repo replay, full coverage of every language/version/traceback format, real microservices telemetry and independent precision/recall gold labels are not part of this verification.

## Review boundary and known follow-up

- The earlier operational-evidence Build increment is in a separate draft PR (#2). It is not merged into this fix branch.
- Other potentially consequential logic outside Objective 1 is deliberately not certified. For example, `remediation.py::SCKGSelfHealingEngine.validate` reports `ckg_consistency=VERIFIED` after setting in-memory source lines but without actually rebuilding the graph. That is an existing **Objective 3 / Fix** verification-risk to address and test separately rather than using its report as proof of successful Build extraction.
- Production accuracy, security, performance, ambiguous reflection/dynamic dispatch and real CI provenance remain empirical research gates.

Do not describe the repository as categorically bug-free or publication-certified on the basis of this suite.
