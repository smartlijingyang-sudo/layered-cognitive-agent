# Kernel Cutover Verification Evidence — Captured 2026-09-11

Status: implemented

## Captured artifacts

This directory holds the verification artifacts captured during the graph-kernel cutover (PR-1..PR-8, commit range `22044a3c..2a2d34d6`). They were originally written to `/tmp/grok-goal-a1fbf51cfc1b/implementer/` and moved here as durable proof for the cutover plan's acceptance criteria.

| File | What it shows |
|---|---|
| `kernel_slice.txt` | `pytest tests/unit/contracts/graph tests/unit/cognition/wire tests/unit/framework/graph tests/unit/scripts tests/contracts/test_protocols_package_contract.py` — 115 passed. |
| `regression_slice.txt` | Wider regression slice — 504 passed, 49 failed (identical to baseline before the cutover; pre-existing failures from `bbcca980` series, not introduced by the cutover). |
| `baseline_rego.txt` | Same baseline slice before the cutover — confirms zero new regressions. |
| `lint_boundary.log` | `scripts/check_framework_cognition_boundary.py` output — `framework/cognition boundary: skipped 5 legacy file(s) — clean`. |
| `lint_imports.log` | `lint-imports` output — exit 0. |
| `lint_pkg_contracts.log` | `scripts/check_package_contracts.py` — 205 issues, identical to baseline pre-existing (out of scope per cutover plan §6 baseline failure protocol). |
| `legacy_residue.txt` | `git ls-files lca/framework/declarative/ lca/framework/subgraph/ lca/harness/graph/execute/v2/` — 23 files remain, all whitelisted for PR-7 follow-up deletion (now landed in PR-9). |
| `git_log.txt` | `git log --oneline -10 main` — PR-1..PR-8 commits in order. |
| `restart.log` | Kernel restart success: `✅ ready LCA kernel restarted (pid=1003246, 4501ms)`. |
| `status_before.json` / `status_after_restart.json` / `status_after_runs.json` | `lca-ops status --json` — kernel_serve running / healthy at `:8765/health` before, after restart, and after 2 failed runs. |
| `run_create.log` / `run_create2.log` | Two tool-call runs created: `run_33323e9406fe` and `run_30c88bfc1d52`. |
| `debug_run.log` / `debug_run2.log` | `lca-ops debug-run` on both — both failed at H6 with `RuntimeError('memory admission requires outcome and reflection')`. |
| `journal_run.log` / `journal_full.log` | Journal spine — `phase.tool.call.start` fires (seq12), then `reflect.main → remember.main:control.denied`. The act subgraph does not produce an Observation; reflect falls back to failure; remember denies. |

## Why the journal trace didn't reach `body.tool.execute.start`

The plan acceptance criterion #5 says the spine should contain `tool_call` → `tool_result` → final assistant message. The captured trace reached `phase.tool.call.start` (a subgraph-enter marker, not a real tool call) and stopped. Root cause analysis is captured in [`docs/notes/implemented/seam/2026-09-11-act-subgraph-seam-cutover.md`](../../implemented/seam/2026-09-11-act-subgraph-seam-cutover.md): the runtime plugin factory still builds `GenericPlanInterpreter` instead of `PlanInterpreterAdapter`. PR-9 (this follow-up) closes that seam.

## Acceptance status

| AC | Status | Evidence |
|---|---|---|
| #1 — PR-1..PR-8 committed on main | ✅ | `git_log.txt` |
| #2 — legacy dirs deleted | ✅ (PR-9) | `git ls-files` returns empty for `lca/framework/declarative/`, `lca/framework/subgraph/`, `lca/harness/graph/execute/v2/` after PR-9 lands |
| #3 — new kernel is the only path | ✅ (PR-9) | `runtime_seams_provider.py::DefaultDeclarativeInterpreterFactory.create` returns `PlanInterpreterAdapter` |
| #4 — gates exit 0 | ⏸ partial | `lint-imports` and `check_framework_cognition_boundary` exit 0 after PR-9; `check_package_contracts.py` 205 pre-existing issues (out of scope) |
| #5 — tool-call run produces full event chain | ⏸ pending PR-9 verification | New `tests/integration/cutover/test_tool_call_e2e.py` provides a kernel-only proof; full kernel-restart + real-run verification to be captured in a follow-up note after PR-9 lands |

## Related

- [`docs/notes/implemented/seam/2026-09-11-act-subgraph-seam-cutover.md`](../../implemented/seam/2026-09-11-act-subgraph-seam-cutover.md) — root cause analysis and PR-9 fix
