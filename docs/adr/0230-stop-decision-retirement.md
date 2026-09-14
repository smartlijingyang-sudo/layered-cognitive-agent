# ADR-0230 — Stop-Decision Retirement

**Status:** Implemented (2026-09-14). Plan: `docs/plans/2026-09-14-stop-decision-retirement.md`. Build: commit `408e3b504` on `fix/sandbox-plane-tool-materialization`. Supersedes the stop-decision surface defined in ADR-0094.

## Decision

The stop-decision half of the stop phase is retired. Loop termination is driven by the model's own `decision.action_type` and by Body's `DeterministicToolError`. There is no host-side policy class, no `StopPolicy` Protocol, no `DefaultStopPolicy` implementation, and no `should_stop` boolean on the typed `StopDecision` / `StopPayload` shapes.

## Mechanism

| Producer | Trigger | `reason` | Source |
|---|---|---|---|
| Model | RESPOND with non-empty `response_text` | (none, terminal commit derives payload) | outer-plan `terminal.commit` node reads `decision.action_type` and `decision.response_text` |
| Body | `EffectReceipt.failure_kind == execution` | `ERROR` | `act.observe` sets `should_terminate=True` on the result payload; outer-plan edge routes to `terminal.commit` |
| Budget guard | `state.budget.exceeded()` | `BUDGET_EXCEEDED` | edge predicate fires on the budget artifact |

The outer-plan `terminal.commit` node (replacing `stop.main`) lifts to `BindingKind.TERMINATE` and runs `TerminateStrategy.execute`, which builds a `StopPayload` from the `decision` and `act_outcome` inputs. The driver reads `terminal_outcome` via `_stop_from_interpretation_output` and runs `apply_stop` then `apply_terminal_outcome`.

Spine events: `spine.terminal.commit` (OBSERVABILITY, emitted by the terminator) and `spine.body.deterministic_fail` (STRUCTURAL, reserved for the future Body raise path). The journal fold maps both to `terminal_outcome` for the reducer.

## What changed

- `StopDecision` lost `should_stop`; `StopReason` lost `TASK_COMPLETED`.
- `StopPayload` lost `should_stop` and `focus_converged`.
- `StopPolicy` Protocol deleted. `DefaultStopPolicy` deleted.
- 8 plugin modules deleted (3 stop primitives, 2 control providers, 2 concept executors, the state policy provider).
- 3 bundle YAMLs deleted (`stop_subgraph.yaml`, `concept/stop_should_check.yaml`, `agent/stop_turn.yaml`).
- `phase_main_outer.yaml` and `agent/run_phase.yaml` swap `stop.main` for `terminal.commit`; edges rewrite to data-shape predicates.
- `act.observe` emits `should_terminate` on `FAILURE_KIND_EXECUTION` and on legacy failed receipts (the historical `run_0d71855ae274` regression class).

## Why

Five prior fixes (per the plan's census) piled onto the same premise — that loop termination is a host-side judgment over model outputs. Each fix added a new predicate to `DefaultStopPolicy` until the policy class carried four rules competing for the same decision. The premise was wrong: the model already decides when it is done. The host's only legitimate termination signal is "Body hit a non-recoverable error."

## Invariants upheld

- C4 (Reducer single write) — Reducer still the sole writer of terminal state via `apply_stop` then `apply_terminal_outcome`.
- C5 (capability monotonic) — no new capability; the new edge predicates read only what the outer kernel already published on the typed payload.
- C10 (Execution narrow gate) — `cognition → Body → SafeExecutor → Sandbox` is unchanged. Body's deterministic-failure signal now travels through `act.observe.should_terminate` instead of through a policy class.
- C12 (Reducer contract) — `apply_stop` precedes `apply_terminal_outcome` (unchanged).

## Historical regression classes no longer reachable

| run_id | Class | Old path | New path |
|---|---|---|---|
| `run_2cd22760a828` | Stale-port loop after producer success | `_delivery_satisfied_stop` + `live_tool_ok` | `act.main → think.main` on `action_type == "use_tool"` |
| `run_0d71855ae274` | Deterministic-failure loop | `_deterministic_failure_stop` | `act.observe.should_terminate` on `FAILURE_KIND_EXECUTION` |
| `run_def5b19c20c0` | Suppressed second think | `_delivery_satisfied_stop` early commit | `act.main → think.main` on `use_tool`; `think.main → terminal.commit` on `respond` with non-empty `response_text` |

The unit tests added in commit `408e3b504` (`tests/contracts/test_stop_decision_shape.py`, `tests/events/test_spine_terminal_commit.py`, `tests/loop/test_act_observe_should_terminate.py`) pin each regression class to the new mechanism.

## Out of scope

- The pre-existing port-name mismatch between `think.gate`'s outer declared outputs (`[decision]`) and `concept/decision_enforce`'s inner schema (`[enforced_decision]`) was not introduced by this work and remains a separate concern. The kernel's port registry drops unmatched names silently; the symptom is `result.payload.decision == None` on outer edge evaluation. Fix lives in `bundles/think.yaml` or `bundles/concept/decision_enforce.yaml`, not in the stop-decision surface.
- `decision.action_type` is currently read off the outer-payload reflection; if the inner-schema mismatch above is fixed, the new edges fire as designed without further change.
