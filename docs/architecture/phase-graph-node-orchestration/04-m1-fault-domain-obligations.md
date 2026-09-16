# 04 — M1 fault-domain obligations (attachment)

> **Status:** M1 attachment (Issue #14, 2026-09-15). Obligations only —
> **no** Defer-Add node kinds / `*NodeRuntime` / second outer / `GraphRuntime`.
> Source table: [`03-six-column-0206.md`](./03-six-column-0206.md) §M1 附件要点.

ControlPlan edge SSOT: `bundles/outer/phase_main.yaml` (`phase.main.outer`).
Terminal name: `terminal.commit` (not `stop.main`).

## 1. Recover

| Obligation | Rule |
|---|---|
| Edge | `reflect.main → think.main` when `routing.next_hint == admit_recovery` |
| Bound | Edge `loop.maxIterations ≥ 1` + non-empty `loop.budget` (LoopGuard=1 default) |
| Hint vs edge | Reflect `admit_recovery` node / plugins emit **hints only**; edges live on outer |
| Fail loud | Missing recovery edge **or** missing/unbound loop → **compile / boot fail** |
| Ban | Silent skip of missing edge; unbounded re-entry; parallel recovery edge table (`declarative-recovery`) |

## 2. Interrupt (HITL) — obligations only (Defer-Add implementation)

| Obligation | Rule |
|---|---|
| Cut point | Only **pre-envelope** (authorize → envelope); never after side-effect dispatch |
| Resume | `Command` closed-set resume; journal is truth |
| Fail-closed | Missing `approval_resume_node` → fail-closed (no soft continue) |
| Timeout / abort | Abort path must **not** slip into envelope / Body |
| Ban | New intervene `*NodeRuntime` in M1; string-only `ask_user` as sole resume path |

## 3. Fanout — obligations only (Defer-Add implementation)

| Obligation | Rule |
|---|---|
| Pairing | Every fanout **N** requires a join barrier |
| Partial failure | Domain declared at compile time (all-stop / partial-admit+audit / HITL) |
| Cursor | Must not advance while fanout cursor uncleared |
| Ban | Fanout without join; mixing ForkedTools visibility with Body execution in tests |

## 4. Delete / residual

| Former edge SSOT | M1 disposition |
|---|---|
| `bundles/declarative-phase-graph.yaml` edge table | Retired; file is history/residual (policy-only optional). delete-when: 2026-10-15 |
| `bundles/declarative-recovery.yaml` | Retired empty residual. delete-when: 2026-10-15 |
| Docs `stop.main` / `phase_main_outer.yaml` | Rename to `terminal.commit` / `bundles/outer/phase_main.yaml` |

## 5. Compile contract

Boot check `AdmitRecoveryEdgeCheck` (`lca_kernel.boot.plan_validation.checks.admit_recovery_edge`)
enforces §1 on `phase.main.outer` only. Tests:
`tests/lca_kernel/boot/test_admit_recovery_edge_check.py`.
