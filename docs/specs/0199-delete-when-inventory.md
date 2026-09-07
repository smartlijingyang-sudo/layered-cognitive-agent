# ADR-0199 COMPAT Inventory & Delete-When Conditions

> **Status:** Living — owned by ADR-0199 §12 (兼容与迁移).
> **Rule:** Every COMPAT block introduced across P1..P5 has an explicit delete-when condition. This file is the SSOT for those conditions; expiry is enforceable by the corresponding gate test (HPC-L2 grep; HPC-L5 doctor CI; etc.).
> **Audience:** maintainers triaging technical debt.

## 0. How to use this file

1. **Find the COMPAT block** in the source.
2. **Look up the delete-when condition** here.
3. **Delete + drop the COMPAT entry** when the condition is met AND the gate test enforces it.

If a COMPAT block is older than the listed delete_when deadline, escalate to the next architecture review.

## 1. Inventory table

| ID | Source | COMPAT block | Owner ADR | delete_when condition | Verification gate |
|---|---|---|---|---|---|
| COMPAT-001 | `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py::create_run` | env-gated `LCA_RUNTIME_FACADE` switch — legacy RunPort.create_and_dispatch path retained when env var == "0" | ADR-0199 §12.2 | Switch flag removed + single-path test + zero hits in `scripts/route_legacy_patterns.py` for "create_run" + `test_0199_compat_gates` exits 0 | `tests/architecture/test_0199_compat_gates.py::test_route_legacy_patterns_reports_no_facade_bypass_in_handlers` |
| COMPAT-002 | `lca/plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py` | `LegacyRunDispatcher` adapter — bridges RunPort to RuntimeFacade.RunDispatcher | ADR-0199 §10 Phase 1 | Composition root wires production dispatcher (P1-13 follow-up); legacy adapter deleted | `tests/architecture/test_0199_compat_gates.py::test_route_legacy_patterns_reports_no_facade_bypass_in_handlers` |
| COMPAT-003 | `lca/infrastructure/cli/commands/runs/runs.py::_create_via_facade` | `--facade` flag for CLI in-process dispatch | ADR-0199 §10 Phase 1 | `--facade` becomes default + CLI↔HTTP parity test in CI + zero hits in route_legacy_patterns for "cli_resolve" | `tests/infrastructure/cli/test_runs_create_facade_path.py::test_facade_path_compat_comment_present` |
| COMPAT-004 | `lca/application/runtime/default_facade.py::dispatch_run` (early PR) | NotImplementedError placeholder (P1-09 stub superseded by P1-10) | ADR-0199 P1-09 | P1-10 merged (already true) | n/a (historical) |
| COMPAT-005 | `lca/plugins/events/hooks/model_visible/reasoner_prompt.py:19` | Pre-existing merge-conflict marker `<<<<<<< Updated upstream` — unrelated to ADR-0199 | pre-0187 PR | Merge conflict resolved | n/a (pre-existing, not ADR-0199) |
| COMPAT-006 | `lca/infrastructure/cli/commands/doctor/profile.py::register` | Subcommand registration (Typer sub-app) not yet wired into root CLI | ADR-0199 P2-08 | `register(...)` imported + called in `lca.infrastructure.cli.commands.__init__.py` or equivalent | Manual + `tests/infrastructure/cli/test_doctor_ci_integration.py` (covers via focused app) |
| COMPAT-007 | `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py::get_run_doctor` | `?shape=contracts` opt-in query parameter (web DoctorReport native shape preserved by default) | ADR-0199 P2-11 | All web doctor consumers migrate to contracts shape + default flips | `tests/lca_plugins/transport/webserver/doctor/test_contracts_adapter.py` |
| COMPAT-008 | `lca/contracts/runtime/runtime/__init__.py` (existing contracts/runtime/runtime/ from pre-ADR-0199) | Pre-existing contracts directory reused for ADR-0199 runtime types | pre-ADR-0199 | n/a (no migration needed; new types land alongside) | n/a |

## 2. Gate tests that enforce delete_when

| Gate test | Purpose | CI run command |
|---|---|---|
| `tests/architecture/test_0199_compat_gates.py` | P1-14 grep: no `facade_bypass` in handlers / no `intent_construction` outside adapters | `pytest tests/architecture/test_0199_compat_gates.py` |
| `tests/architecture/test_0199_phase1_acceptance.py` | P1-12 plan_ref cross-surface parity | `pytest tests/architecture/test_0199_phase1_acceptance.py` |
| `tests/architecture/test_0199_skill_scan_isolation.py` | P4-05 I-HPC-6 content scan isolation | `pytest tests/architecture/test_0199_skill_scan_isolation.py` |
| `tests/architecture/test_0199_invariants_snapshot.py` | P3-10 I-HPC-* snapshot | `pytest tests/architecture/test_0199_invariants_snapshot.py` |
| `tests/architecture/test_0199_proposal_no_hot_swap.py` | P4-08 I-HPC-10 no hot-swap | `pytest tests/architecture/test_0199_proposal_no_hot_swap.py` |
| `tests/architecture/test_0199_event_catalog_activation_ref.py` | P3-08 HPC-L6 activation_ref on EPs | `pytest tests/architecture/test_0199_event_catalog_activation_ref.py` |
| `tests/architecture/test_0199_no_global_tool_registry.py` | P5-05 HPC-L8 no global registry | `pytest tests/architecture/test_0199_no_global_tool_registry.py` |
| `tests/architecture/test_0199_doctor_golden.py` | P2-10 golden profiles doctor CI | `pytest tests/architecture/test_0199_doctor_golden.py` |
| `tests/architecture/test_0199_doctor_ci_gate.py` | P2-12 strict zero-error gate | `pytest tests/architecture/test_0199_doctor_ci_gate.py` |

## 3. Update protocol

When a COMPAT block is deleted:

1. Remove the COMPAT comment from the source file.
2. Update this file: mark the row as "deleted YYYY-MM-DD" or remove the row entirely.
3. Update `tests/architecture/test_0199_compat_gates.py` to remove the now-obsolete exemption if any.
4. Open a PR whose body cites the delete_when condition met.

## 4. Cross-references

- [ADR-0199 §12 兼容与迁移](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md#12-兼容与迁移)
- [Implementation plan §11 COMPAT 追踪](../specs/0199-implementation-plan.md#11-compat-与-delete-when-追踪)
- [scripts/route_legacy_patterns.py](../../scripts/route_legacy_patterns.py) — the AST grep gate
