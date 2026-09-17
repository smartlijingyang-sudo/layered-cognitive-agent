# ADR-0230 — Stop-Decision Retirement

**Status:** Implemented (2026-09-14). Plan: `docs/plans/2026-09-14-stop-decision-retirement.md`. Build: commit `408e3b504` on `fix/sandbox-plane-tool-materialization`. Supersedes the stop-decision surface defined in ADR-0094.

## Amendment (2026-09-17) — the Body termination trigger was wrong

Two claims below did not survive contact with production runs, and the second is corrected in code:

- **`DeterministicToolError` was never built.** No class definition and no raise site exist anywhere in the tree; the name survives only in docstrings (now corrected). PR-3 of the plan implemented the trigger as a graph node instead: `act.observe.terminate_decide` emitting a `should_terminate` port. `spine.body.deterministic_fail` stays reserved and unemitted.
- **Terminating on `failure_kind == execution` killed recoverable runs.** `execution` is stamped by the tool adapters on *any* non-success tool result, so an ordinary sandbox failure ended the run before the model could react. `run_eed09c1df112` died on `ModuleNotFoundError: pdf2image` at step 4 of a PDF analysis; `run_aebabe6c1056` died on `exit code 1`; `run_6d3aeff0b339` on `FileNotFoundError`. The premise that justified the shortcut — avoiding a cycle to `max_visits=8` — no longer held, because ADR-0225 deleted the per-node `max_visits` ceiling and `think.budget.gate` already bounds a stuck loop.

The trigger is now the unclassified receipt only (`failure_kind is None` with `outcome == failed`), which is what `concept.effect.execute` produces when the gateway itself raised — no tool ever reported a result. Classified failures return to the model, matching `docs/specs/tool-failure-recovery.md` §3/§6.1/§7, which this ADR had contradicted.

**The unclassified trigger was still unsound on a forked turn.** It reads `failure_kind is None` as "no tool ran", but two aggregation sites folded N per-call Observations into one and dropped the parts' tags on the way, so a batch whose tools *had* reported arrived unclassified. `ToolBatchExecutor._combine_observations` kept only `result_kind` and `tool_results` in `extra`; `DelegateOperation._aggregate_observations` did the same over member results. `_derive_outcome` reads the top level only, so the batch receipt looked like a host dispatch failure and ended the run.

`run_136671e2ff8a` died this way at step 1 of a PDF task: the model forked `runCommand` + `activate_skill`, `runCommand` reported `cd: /files: No such file or directory` (`execution`), and `terminal.commit` was handed `StopPayload(reason='continue')` while `kernel.run.stop` recorded `failure`. The model never saw the error, so it never got the turn in which `activate_skill`'s own result would have told it the upload was at `/mnt/data/`.

Both folds now take the highest-precedence tag among their failing parts — `fold_failure_kinds`, kept next to the `FAILURE_KIND_*` vocabulary in `lca/contracts/atoms/semantic/keys.py` because the fold is a property of the closed set, not of either caller. Precedence runs from the model outward (`tool_wire` > `validation` > `execution` > `transient`), which makes the aggregate independent of emission order and of which segment ran in parallel (C8). A tag outside the vocabulary still counts as classified, so extending the set cannot downgrade a batch to "host dispatch failure". When no part carries a tag the aggregate still folds to `None`, keeping the host-dispatch branch reachable and its meaning intact.

The single-call path never had the defect: `_as_tool_result` passes the tool's own `extra` through untouched.

What bounds a model that keeps re-issuing the same failing call is `think.budget.gate`, which runs on every think iteration and routes to `terminal.commit` once `Budget.exceeded()` — `create_budget()` in `lca/runtime/loop/runtime_loop.py` sets `max_steps=50` and `max_wall_clock_seconds=300`. So the `run_0d71855ae274` class is bounded, but at 50 steps rather than at the first failure.

**Open defect this amendment exposes.** `ToolLoopBreakerGate` (breaks at 3 same-tool failures) and `ProgressLoopDetector` (forces RESPOND at 6 no-progress steps) both read `control_turns(state)`. That reader prefers the durable `turn.control.v1` fold and falls back to `state.control_turns`, which `Reducer.apply_turn` writes. The only path to `apply_turn` in production is `TurnDeltaHandler.apply` → `Reducer.commit_turn`, and nothing under `lca/` constructs a `RunDelta`, so that chain never runs. Both gates therefore read zero turns on every run, not just on the failed-tool path. Measured on two live tool-loop runs: `remember` and `reflect` node visits are 0 each, and no `turn.*` fact appears in the ledger.

This predates the amendment and is why `think.budget.gate` is currently the only working bound on a stuck loop. Fixing it needs a decision about where a turn becomes a fact. `act.observe.commit_fact` is not available: it was deliberately reduced to a receipt passthrough, with RunFact construction moved upstream to `reducer.fold` via `FactCommitter` / `Session.append` (ADR-0192 single track).

## Decision

The stop-decision half of the stop phase is retired. Loop termination is driven by the model's own `decision.action_type` and by Body's `DeterministicToolError`. There is no host-side policy class, no `StopPolicy` Protocol, no `DefaultStopPolicy` implementation, and no `should_stop` boolean on the typed `StopDecision` / `StopPayload` shapes.

## Mechanism

| Producer | Trigger | `reason` | Source |
|---|---|---|---|
| Model | RESPOND with non-empty `response_text` | (none, terminal commit derives payload) | outer-plan `terminal.commit` node reads `decision.action_type` and `decision.response_text` |
| Body | unclassified receipt (`failure_kind is None` and `outcome == failed`); a forked batch folds its failing parts' tags into the one receipt — see Amendment | `ERROR` | `act.observe.terminate_decide` sets `should_terminate=True` on the result payload; outer-plan edge routes to `terminal.commit`. Originally `failure_kind == execution`; see Amendment |
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
- `act.observe` emits `should_terminate` on unclassified failed receipts. It originally also emitted on `FAILURE_KIND_EXECUTION`; see Amendment.

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
| `run_0d71855ae274` | Deterministic-failure loop | `_deterministic_failure_stop` | `think.budget.gate` routes to `terminal.commit` at `max_steps=50` / 300s wall clock. The two turn-reading gates cannot fire on this path yet — see Amendment |
| `run_def5b19c20c0` | Suppressed second think | `_delivery_satisfied_stop` early commit | `act.main → think.main` on `use_tool`; `think.main → terminal.commit` on `respond` with non-empty `response_text` |

The unit tests added in commit `408e3b504` (`tests/contracts/test_stop_decision_shape.py`, `tests/events/test_spine_terminal_commit.py`, `tests/loop/test_act_observe_should_terminate.py`) pin each regression class to the new mechanism.

## Out of scope

- The pre-existing port-name mismatch between `think.gate`'s outer declared outputs (`[decision]`) and `concept/decision_enforce`'s inner schema (`[enforced_decision]`) was not introduced by this work and remains a separate concern. The kernel's port registry drops unmatched names silently; the symptom is `result.payload.decision == None` on outer edge evaluation. Fix lives in `bundles/think.yaml` or `bundles/concept/decision_enforce.yaml`, not in the stop-decision surface.
- `decision.action_type` is currently read off the outer-payload reflection; if the inner-schema mismatch above is fixed, the new edges fire as designed without further change.
