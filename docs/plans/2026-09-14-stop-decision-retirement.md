---
title: retire stop-decision half of stop phase
type: plan
status: proposed
created: 2026-09-14
owner: lichao
related:
  - docs/adr/0094-stop-policy-locality.md
  - docs/adr/0196-convergence-control-plane-and-prompt-surface.md
  - docs/adr/0217-bundle-graph-schema-v2.md
  - docs/adr/0221-concept-decision-classify-parse-merge.md
  - docs/specs/glossary.md
---

# Stop-Decision Retirement plan

Stop the loop by `decision.action_type` and the model's own `response_text`, not by a host-side policy class. Land six PRs that shrink `StopDecision`, retire `StopPolicy` and `DefaultStopPolicy`, retire the three stop primitives, retire the two stop control providers, retire the two concept stop executors, replace the `stop.main` outer node with a thin `terminal.commit`, move the deterministic-failure shortcut out of the policy into Body, and add a closed-loop e2e that proves each historical regression class still cannot recur through the new mechanism.

## How to read this

One box is one unit of work. Every PR names the evidence that checks it. The body is a how-to. Appendices explain and record.

The program runs `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. The root PR targets `main`. Each child branch rebases onto its parent tip. PR 6 is the merge gate.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

Check a box only when its evidence exists. Names the evidence.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on her explicit go.
- [ ] On her go, arm a `/goal` with this exact text. "/home/lichao/layered-cognitive-agent/docs/plans/2026-09-14-stop-decision-retirement.md, PR ids PR-1 through PR-6 in order, the verification rule from multi-phase-plan.md, owner merges via autopilot-stack, done condition is PR-6 swarm-clean at the stack root."
- [ ] Read these from trunk at program start. Re-read them at every tick.
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `git show origin/main:pstack/skills/swarm/SKILL.md`
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `git show origin/main:lca/contracts/models/core/policy/stop.py`
  - [ ] `git show origin/main:bundles/phase_main_outer.yaml`
- [ ] Arm the 30-minute audit tick. In a local session, a real terminal `/loop`. In a cloud root, a cloud-sleeper wake chain. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the autopilot-stack playbook from trunk and the armed /goal. Audit the operation against both and fix drift in this tick. Probe every active PR and judge progress by side effects only. Stand down a stuck PR and dispatch its replacement now. Then send the operator a status message, whether or not anything changed, with the queue table of PR id, owner, state, head SHA, the verdicts since the last tick, what merged, open operator gates, and blockers."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the autopilot-stack playbook names.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges, or base it on the parent branch when the playbook stacks.
  - [ ] PR-1 and PR-2 are independent and first. Both branch from `main`.
  - [ ] PR-3 after PR-1.
  - [ ] PR-4 after PR-1 and PR-2.
  - [ ] PR-5 after PR-3 and PR-4.
  - [ ] PR-6 after PR-5.
- [ ] Hold the file boundaries. PR-1 touches only `lca/contracts/**`. PR-2 touches only `lca/contracts/event.py`, `lca_kernel/events/**`, `lca/session/catalog.py`, `lca/plugins/session/derivers/step_tree/journal_fold.py`, `lca/contracts/observability/observation/m5_event_traces/**`. PR-3 touches only `lca/body/**` and tests. PR-4 touches only `bundles/**` and `profiles/**`. PR-5 deletes retired plugins and tests. PR-6 closes the loop.
- [ ] Hold the review gate. PR-4 changes an interaction. It waits for the operator's review in chat with screenshots and a video before merge.

### PR mechanics, for every PR

- [ ] Resolve the forge once. Default to `gh`; if `command -v origin` succeeds and Origin can resolve the repository, use `origin pr` for every PR operation. Record any fallback to `gh`. Never require `gt`.
- [ ] Open the PR ready, never draft, with `origin pr create --status open --base <base-branch>` or `gh pr create --base <base-branch>` according to the resolved forge. A stack child targets its parent branch.
- [ ] Run the repo's lint and typecheck once before the PR-facing push. Push with hooks on.
- [ ] Run `/deslop` before each commit and `/no-comments` before review.
- [ ] Triage every Bugbot and security-reviewer comment per `pstack/skills/poteto-mode/references/bugbot-triage.md`.
- [ ] Rebase onto current trunk before babysit and again before the merge-ready report.

### Verdict and merge, for every PR

- [ ] At the merge-ready head SHA, run the swarm per `pstack/skills/swarm/SKILL.md`. One gates lane. The ten live lanes from the PR's Verify, live block. The perf lane from its Verify, perf block. One audit lane that reads the diff and the receipts and distrusts the PR body.
- [ ] Clean only when every lane is `PASS`. Findings go back to the owner. A new head gets a fresh swarm and a fresh verdict.
- [ ] Owner squash-merges its own PR after the swarm verdict lands clean. The root of the stack is PR-1.

### Boot recipe, for every live lane

Each live lane runs on its own cloud VM at the PR head. Drive through `control-cli` from `cursor-team-kit` since the surface is a CLI / kernel.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] Start the kernel. `./scripts/lca-ops heal --json` and wait for `kernel_serve: healthy`.
- [ ] Trigger the run. `./scripts/lca-ops runs create --user-text "<scenario text>" --profile web-standard --wait --json`.
- [ ] Capture diagnostics. `./scripts/lca-ops debug-run "$RUN_ID"` and `./scripts/lca-ops journal trace "$RUN_ID" --human`.
- [ ] Save every screenshot to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.png` and return the paths with the report.

## PR-1 shrink StopDecision and retire StopPolicy Protocol

**Depends on.** None.

**Files.**

- [ ] Edit `lca/contracts/models/core/policy/stop.py`.
- [ ] Edit `lca/contracts/protocols/runtime/runtime/runtime.py`.
- [ ] Edit `lca/contracts/__init__.py`.
- [ ] Edit `lca/contracts/protocols/__init__.py`.

**Build.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Remove `StopDecision.should_stop`. Keep `reason / final_output / status / failure`. New docstring is "loop's terminal payload; `reason` is set by the model (RESPOND) or by Body (FAILURE_KIND_EXECUTION) or by the budget guard (BUDGET_EXCEEDED). `TASK_COMPLETED` is removed."
- [ ] Remove `StopReason.TASK_COMPLETED`. Keep `CONTINUE / BUDGET_EXCEEDED / ERROR`.
- [ ] Remove `StopPolicy` Protocol from `lca/contracts/protocols/runtime/runtime/runtime.py`.
- [ ] Remove `StopPolicy` from `lca/contracts/protocols/__init__.py` re-export list.
- [ ] Remove `StopPolicy` from `lca/contracts/__init__.py` re-export list.

**You see.**

- [ ] `python -c "from lca.contracts.models.core.policy.stop import StopDecision, StopReason; print(StopDecision.__dataclass_fields__.keys())"` prints `dict_keys(['reason', 'final_output', 'status', 'failure'])` and `python -c "from lca.contracts.models.core.policy.stop import StopReason; print(list(StopReason))"` prints `[<CONTINUE>, <BUDGET_EXCEEDED>, <ERROR>]`.
- [ ] `grep -r "from lca.contracts.protocols.runtime.runtime.runtime import .*StopPolicy" lca/` returns zero hits (production code, not tests).

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/contracts/test_stop_decision_shape.py` (new file) asserts `StopDecision.__dataclass_fields__` does not contain `should_stop`, `StopReason` does not contain `TASK_COMPLETED`. Run `python -m pytest tests/contracts/test_stop_decision_shape.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Trunk still imports `StopPolicy`. Pass when `python -c "from lca.contracts.protocols.runtime.runtime.runtime import StopPolicy"` fails on the head and succeeds on trunk. Save `/tmp/swarm-PR-1/worker-1/lane_1.png`.
- [ ] Lane 2. `python -m pytest tests/contracts/ -k "stop or terminal"` exits 0 at the head. Save `/tmp/swarm-PR-1/worker-2/lane_2.png`. Pass when the named command exits 0.
- [ ] Lane 3. `python -m pytest tests/runtime/test_reducer.py -k "stop"` exits 0 at the head. Save `/tmp/swarm-PR-1/worker-3/lane_3.png`. Pass when the named command exits 0.
- [ ] Lane 4. `ruff check lca/contracts/models/core/policy/stop.py lca/contracts/protocols/runtime/runtime/runtime.py` exits 0. Save `/tmp/swarm-PR-1/worker-4/lane_4.png`. Pass when the named command exits 0.
- [ ] Lane 5. `python -m mypy lca/contracts/models/core/policy/stop.py lca/contracts/protocols/runtime/runtime/runtime.py` exits 0. Save `/tmp/swarm-PR-1/worker-5/lane_5.png`. Pass when the named command exits 0.
- [ ] Lane 6. `python scripts/check_package_contracts.py` exits 0. Save `/tmp/swarm-PR-1/worker-6/lane_6.png`. Pass when the named command exits 0.
- [ ] Lane 7. `python scripts/check_no_any.py` exits 0. Save `/tmp/swarm-PR-1/worker-7/lane_7.png`. Pass when the named command exits 0.
- [ ] Lane 8. `python scripts/check_protocol_schema_version.py` exits 0. Save `/tmp/swarm-PR-1/worker-8/lane_8.png`. Pass when the named command exits 0.
- [ ] Lane 9. `python scripts/check_plugin_metadata.py` exits 0. Save `/tmp/swarm-PR-1/worker-9/lane_9.png`. Pass when the named command exits 0.
- [ ] Lane 10. `python scripts/check_run_debug_sync.py` exits 0 (verify no doc still references `StopPolicy` as a live concept after the merge). Save `/tmp/swarm-PR-1/worker-10/lane_10.png`. Pass when the named command exits 0.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `python -m pytest tests/contracts/ -k "stop or terminal"` from cold.
- [ ] Probe. Run at trunk first (baseline), then at the head, interleaved 3 times.
- [ ] Baseline. Record the trunk value first.
- [ ] Rule. Head must be within 5 percent of trunk. Failure value is a 10 percent regression.

**Review gate.** None. PR-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.

## PR-2 add spine events and journal fold entries for the new termination mechanism

**Depends on.** None.

**Files.**

- [ ] Edit `lca/contracts/event.py`.
- [ ] Edit `lca_kernel/events/payloads/spine.py`.
- [ ] Edit `lca_kernel/events/config/observability/spine.yaml`.
- [ ] Edit `lca/session/catalog.py`.
- [ ] Edit `lca/plugins/session/derivers/step_tree/journal_fold.py`.
- [ ] Edit `lca/contracts/observability/observation/m5_event_traces/__init__.py`.

**Build.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Add `SPINE_TERMINAL_COMMIT = "spine.terminal.commit"` to `lca/contracts/event.py` and its whitelist mapping at `lca_kernel/events/payloads/spine.py`. Plane mapping is OBSERVABILITY. yaml entry at `lca_kernel/events/config/observability/spine.yaml`.
- [ ] Add `SPINE_BODY_DETERMINISTIC_FAIL = "spine.body.deterministic_fail"` to the same files. Plane mapping is STRUCTURAL. yaml entry.
- [ ] Update `lca/session/catalog.py:34-44` so the merged `known_session_event_types()` includes the two new EPs without further changes (the existing merge covers them via the `SPINE_EXECUTION_POINTS` set).
- [ ] Add `"spine.terminal.commit": "terminal_commit"` and `"spine.body.deterministic_fail": "deterministic_fail"` to `PHASE_FOLD_EPS` at `lca/plugins/session/derivers/step_tree/journal_fold.py:77` adjacent to the existing `phase.stop.fold` entry. Extend `_capture_outcome` so `spine.terminal.commit` with `outcome=completed` sets `terminal_outcome="completed"`, with `reason="budget_exhausted"` sets `terminal_outcome="budget_exhausted"`, with `reason="error"` sets `terminal_outcome="failed"`. Extend so `spine.body.deterministic_fail` sets `terminal_outcome="failed"` and stamps `state.last_error`.
- [ ] Add `verdict_kind: Literal["allow", "deny", "terminate"]` (extend existing `ControlTrace`) so the new `spine.terminal.commit` carrier has a typed verdict slot. Place at `lca/contracts/observability/observation/m5_event_traces/__init__.py:34-41`.

**You see.**

- [ ] `python -c "from lca.contracts.event import SPINE_TERMINAL_COMMIT, SPINE_BODY_DETERMINISTIC_FAIL; print(SPINE_TERMINAL_COMMIT, SPINE_BODY_DETERMINISTIC_FAIL)"` prints `spine.terminal.commit spine.body.deterministic_fail`.
- [ ] `python scripts/check_events_catalog_consistency.py` exits 0.
- [ ] `python scripts/check_emit_single_entry.py` exits 0.
- [ ] `python scripts/check_cordis_event_derivation.py` exits 0.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/events/test_spine_terminal_commit.py` (new file) asserts the new EPs are in `SPINE_EXECUTION_POINTS`, in `known_session_event_types()`, in `PHASE_FOLD_EPS`, and that `_capture_outcome` produces the right `terminal_outcome` value for each `(event_name, reason)` pair. Run `python -m pytest tests/events/test_spine_terminal_commit.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Trunk does not emit these EPs. Pass when head emits `spine.terminal.commit` on a real run and trunk does not. Save `/tmp/swarm-PR-2/worker-1/lane_1.png`.
- [ ] Lane 2. `./scripts/lca-ops runs create --user-text "echo smoke" --profile web-standard --wait --json` produces a run whose `events.jsonl` contains a `spine.terminal.commit` row. Pass when grep returns one match. Save `/tmp/swarm-PR-2/worker-2/lane_2.png`.
- [ ] Lane 3. `python -m pytest tests/events/ -v` exits 0. Save `/tmp/swarm-PR-2/worker-3/lane_3.png`. Pass when the named command exits 0.
- [ ] Lane 4. `python scripts/check_emit_single_entry.py` exits 0. Save `/tmp/swarm-PR-2/worker-4/lane_4.png`. Pass when the named command exits 0.
- [ ] Lane 5. `python scripts/check_events_catalog_consistency.py` exits 0. Save `/tmp/swarm-PR-2/worker-5/lane_5.png`. Pass when the named command exits 0.
- [ ] Lane 6. `python scripts/check_cordis_event_derivation.py` exits 0. Save `/tmp/swarm-PR-2/worker-6/lane_6.png`. Pass when the named command exits 0.
- [ ] Lane 7. `python scripts/check_no_silent_swallow.py` exits 0. Save `/tmp/swarm-PR-2/worker-7/lane_7.png`. Pass when the named command exits 0.
- [ ] Lane 8. `python scripts/verify_observability_compile_plan.py` exits 0. Save `/tmp/swarm-PR-2/worker-8/lane_8.png`. Pass when the named command exits 0.
- [ ] Lane 9. `python -m mypy lca/contracts/event.py lca_kernel/events/payloads/spine.py lca/plugins/session/derivers/step_tree/journal_fold.py` exits 0. Save `/tmp/swarm-PR-2/worker-9/lane_9.png`. Pass when the named command exits 0.
- [ ] Lane 10. `python scripts/check_run_debug_sync.py` exits 0. Save `/tmp/swarm-PR-2/worker-10/lane_10.png`. Pass when the named command exits 0.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Spine event count per run for a one-tool one-respond scenario.
- [ ] Probe. Run a baseline script `python scripts/perf_spine_event_count.py --profile web-standard --user-text "echo smoke"` at trunk, then at head.
- [ ] Baseline. Record the trunk event count first.
- [ ] Rule. Head event count must be trunk count plus at most 2 (one new EP each from the two new sources). Anything above is over-emission.

**Review gate.** None. PR-2 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.

## PR-3 move deterministic-failure shortcut from policy into Body

**Depends on.** PR-1.

**Files.**

- [ ] Create `lca/body/act/errors.py` (new file).
- [ ] Edit the Body executor module (file path verified at execution time, candidate `lca/body/act/safe_executor.py`).
- [ ] Edit `lca/contracts/harness/act/effect_receipt.py`.
- [ ] Edit `lca/loop/driver.py`.

**Build.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Add `class DeterministicToolError(RuntimeError)` in `lca/body/act/errors.py`. Constructor takes `tool_name`, `arguments`, `original_error`.
- [ ] In the Body executor, when `failure_kind == "execution"` (per `lca/contracts/atoms/semantic/keys.py:FAILURE_KIND_EXECUTION`), raise `DeterministicToolError` instead of returning the failing `EffectReceipt`. The error carries the typed payload that Body would otherwise have returned.
- [ ] Update `lca/contracts/harness/act/effect_receipt.py` docstring at line 42 to remove the reference to `DefaultStopPolicy._deterministic_failure_stop`.
- [ ] In `lca/loop/driver.py` (the outer loop driver at line 285-308 per the inventory), wrap the Body call with a `try` / `except DeterministicToolError` that synthesises a `StopDecision(reason=StopReason.ERROR, status=TaskStatus.FAILED, failure=RunDiagnostic.from_error(...))` and feeds it directly into `apply_stop` / `apply_terminal_outcome`. Emit `SPINE_BODY_DETERMINISTIC_FAIL` per PR-2.
- [ ] Update `lca/plugins/loop/reducer/plugin.py:279-290` docstring to reflect that `apply_stop` now receives both model-driven and host-driven `StopDecision` instances with no policy intermediary.

**You see.**

- [ ] `python -c "from lca.body.act.errors import DeterministicToolError"` prints zero exit.
- [ ] A live run with a tool that deterministically fails (the historical `run_0d71855ae274` shape) emits `SPINE_BODY_DETERMINISTIC_FAIL` and terminates after one tool call instead of cycling to `max_visits=8`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/body/test_deterministic_tool_error.py` (new file) covers. Raises on `failure_kind == "execution"`. Does not raise on `failure_kind == "transient"`. Carries typed payload. Run `python -m pytest tests/body/test_deterministic_tool_error.py -v`.
- [ ] `tests/loop/test_driver_deterministic_fail.py` (new file) covers. Outer loop converts the exception into `apply_stop` without going through any policy. Run.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the historical scenario from `run_0d71855ae274` (tool is `cat /nonexistent/path/please_fail_gracefully`). Pass when the head terminates after one tool call with `terminal_outcome=failed`, and the `events.jsonl` contains `SPINE_BODY_DETERMINISTIC_FAIL`. Save `/tmp/swarm-PR-3/worker-1/lane_1.png`.
- [ ] Lane 2. Run the same scenario with a transient error (`failure_kind=transient`). Pass when head retries through Body normally and does not emit `SPINE_BODY_DETERMINISTIC_FAIL`. Save `/tmp/swarm-PR-3/worker-2/lane_2.png`.
- [ ] Lane 3. `python -m pytest tests/body/ tests/loop/ -v` exits 0. Save `/tmp/swarm-PR-3/worker-3/lane_3.png`. Pass when the named command exits 0.
- [ ] Lane 4. `python scripts/check_command_envelope_required.py` exits 0. Save `/tmp/swarm-PR-3/worker-4/lane_4.png`. Pass when the named command exits 0.
- [ ] Lane 5. `python scripts/check_no_silent_swallow.py` exits 0. Save `/tmp/swarm-PR-3/worker-5/lane_5.png`. Pass when the named command exits 0.
- [ ] Lane 6. `python scripts/check_writable_matrix_boundaries.py` exits 0. Save `/tmp/swarm-PR-3/worker-6/lane_6.png`. Pass when the named command exits 0.
- [ ] Lane 7. `python -m mypy lca/body/ lca/loop/driver.py` exits 0. Save `/tmp/swarm-PR-3/worker-7/lane_7.png`. Pass when the named command exits 0.
- [ ] Lane 8. `python scripts/check_evidence_atomic.py` exits 0. Save `/tmp/swarm-PR-3/worker-8/lane_8.png`. Pass when the named command exits 0.
- [ ] Lane 9. `python scripts/check_kernel_boundary.py` exits 0. Save `/tmp/swarm-PR-3/worker-9/lane_9.png`. Pass when the named command exits 0.
- [ ] Lane 10. `python scripts/check_run_debug_sync.py` exits 0. Save `/tmp/swarm-PR-3/worker-10/lane_10.png`. Pass when the named command exits 0.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Number of LLM round-trips for the `run_0d71855ae274` scenario (a deterministic-failure shortcut should reduce this from 8 to 1).
- [ ] Probe. Run `./scripts/lca-ops runs create --user-text "cat /nonexistent/path/please_fail_gracefully" --profile web-standard --wait --json` at head, compare to the recorded 8-step behavior of the trunk run.
- [ ] Baseline. Record trunk run total_steps = 8.
- [ ] Rule. Head total_steps must be 1. Any value above is a shortcut regression.

**Review gate.** None. PR-3 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.

## PR-4 replace stop.main outer node with terminal.commit

**Depends on.** PR-1 and PR-2.

**Files.**

- [ ] Edit `bundles/phase_main_outer.yaml`.
- [ ] Edit `bundles/agent/run_phase.yaml` (read at execution time to confirm surface).
- [ ] Edit `lca/framework/graph/lifter.py` if `sub_spec_ref` semantics need a no-op subgraph entry.
- [ ] Edit `lca/framework/graph/strategies/subgraph_strategy.py` (read-only verification; no change unless the lifter needs a new binding kind).
- [ ] Create `lca/framework/graph/strategies/terminal_commit.py` (new file).
- [ ] Edit `lca/loop/driver.py:285-308` outer-loop driver.
- [ ] Edit `docs/specs/glossary.md`.

**Build.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] In `bundles/phase_main_outer.yaml`, replace the `stop.main` node (lines 73-83) with `terminal.commit`. New shape is `id: terminal.commit`, `region: phase:terminal`, `max_visits: 1`, `terminal: true`, no `sub_spec_ref`. Inputs are `[decision]`. Outputs are `[terminal_outcome]`.
- [ ] Replace the five `<phase>.main → stop.main` error-short-circuit edges (lines 88-89, 95-96, 103-104, 111-112, 119-120) with `from: <phase>.main, to: terminal.commit, when: result.payload.should_terminate == true`. New edge semantics are, the outer driver stamps `should_terminate=true` on the `phase_result` payload only when the model emitted RESPOND with non-empty `response_text` OR when `DeterministicToolError` was caught OR when `state.budget.exceeded()` is true.
- [ ] Replace the `stop.main → perceive.main` loop-back edge (lines 124-126) with `from: terminal.commit, to: think, when: false` (terminal never loops back) AND add `from: act.main, to: think, when: result.payload.decision.action_type == USE_TOOL` (the new USE_TOOL → re-ask-model edge).
- [ ] Add a tiny executor `TerminalCommitExecutor` in `lca/framework/graph/strategies/terminal_commit.py` that reads `decision.action_type` and `decision.response_text`, builds a `StopDecision(reason=ERROR if no response_text else BUDGET_EXCEEDED if budget else CONTINUE mapped to model RESPOND with final_output=response_text)`, and feeds `apply_stop` then `apply_terminal_outcome`. Emit `SPINE_TERMINAL_COMMIT` per PR-2.
- [ ] Update `lca/framework/graph/lifter.py` so a node without `sub_spec_ref` and without `factory` that has `terminal: true` lifts to `BindingKind.TERMINAL_COMMIT` (new binding kind) and dispatches `TerminalCommitExecutor`.
- [ ] Update `docs/specs/glossary.md:85-86` to remove the `StopPolicy / StopDecision / StopReason` entries and add a single `Terminal commit` entry that says "Loop terminator driven by `decision.action_type` and Body's deterministic-failure raise; produces `terminal_outcome` for the reducer".

**You see.**

- [ ] `python -c "import yaml; spec=yaml.safe_load(open('bundles/phase_main_outer.yaml')); ids=[n['id'] for n in spec['nodes']]; print('terminal.commit' in ids, 'stop.main' not in ids)"` prints `True True`.
- [ ] `grep -rn "stop.main" bundles/ profiles/` returns zero hits.
- [ ] `./scripts/lca-ops runs create --user-text "hello" --profile web-standard --wait --json` produces a run whose `journal.narrative.md` ends at `terminal.commit` (not `stop.main`) and whose `events.jsonl` contains `SPINE_TERMINAL_COMMIT`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/framework/test_terminal_commit_binding.py` (new file) asserts the lifter produces `BindingKind.TERMINAL_COMMIT` for `terminal.commit` and dispatches the right executor. Run.
- [ ] `tests/framework/test_outer_plan_no_stop_node.py` (new file) loads `bundles/phase_main_outer.yaml` and asserts no node has `id=stop.*` and no edge references `stop.main`. Run.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Trunk terminates via `stop.main`; head via `terminal.commit`. Pass when the journal trace at head shows `terminal.commit` in the trajectory and trunk shows `stop.main`. Save `/tmp/swarm-PR-4/worker-1/lane_1.png`.
- [ ] Lane 2. Run the historical `run_def5b19c20c0` scenario (bash + summarize). Pass when the run produces two LLM round-trips (USE_TOOL then RESPOND with summary) and terminates with `final_output=non-empty summary`. Save `/tmp/swarm-PR-4/worker-2/lane_2.png`.
- [ ] Lane 3. Run a clean RESPOND-only prompt. Pass when the run does one LLM round-trip and terminates. Save `/tmp/swarm-PR-4/worker-3/lane_3.png`.
- [ ] Lane 4. `python -m pytest tests/framework/ -k "terminal or outer_plan" -v` exits 0. Save `/tmp/swarm-PR-4/worker-4/lane_4.png`. Pass when the named command exits 0.
- [ ] Lane 5. `python scripts/check_assembly_purity.py` exits 0. Save `/tmp/swarm-PR-4/worker-5/lane_5.png`. Pass when the named command exits 0.
- [ ] Lane 6. `python scripts/check_package_contracts.py` exits 0. Save `/tmp/swarm-PR-4/worker-6/lane_6.png`. Pass when the named command exits 0.
- [ ] Lane 7. `python scripts/check_writable_matrix_boundaries.py` exits 0. Save `/tmp/swarm-PR-4/worker-7/lane_7.png`. Pass when the named command exits 0.
- [ ] Lane 8. `python scripts/check_loop_cursor_bundle_required.py` exits 0. Save `/tmp/swarm-PR-4/worker-8/lane_8.png`. Pass when the named command exits 0.
- [ ] Lane 9. `python scripts/check_loop_cursor_no_deriver_hold.py` exits 0. Save `/tmp/swarm-PR-4/worker-9/lane_9.png`. Pass when the named command exits 0.
- [ ] Lane 10. `python scripts/check_run_debug_sync.py` exits 0. Save `/tmp/swarm-PR-4/worker-10/lane_10.png`. Pass when the named command exits 0.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. End-to-end run wall time for the `run_def5b19c20c0` scenario (now two LLM round-trips vs one before).
- [ ] Probe. Run `./scripts/lca-ops runs create --user-text "echo second-think-probe and then summarize" --profile web-standard --wait --json` at head, compare against trunk run wall time for the same prompt.
- [ ] Baseline. Record trunk wall time first.
- [ ] Rule. Head wall time must be at most trunk wall time plus one LLM-call latency budget (median of the 5 most recent runs). Larger than one-call budget means the re-prompt loop introduces extra cost beyond what the user asked for.

**Review gate.** The operator reviews before merge. PR-4 changes an interaction (the journal trajectory now shows `terminal.commit` instead of `stop.main` and the second-think case actually produces output).

- [ ] Copy Lane 1 and Lane 2 screenshots into `docs/media/PR-4-review-trajectory.png` and `docs/media/PR-4-review-second-think.png`.
- [ ] Record a 30 to 60 second video of the second-think recovery on a lane VM. Save it as `docs/media/PR-4-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.

## PR-5 delete retired stop-decision plugins, bundles, tests, and ADRs

**Depends on.** PR-3 and PR-4.

**Files.**

- [ ] Delete `lca/plugins/loop/state/stop_policy/plugin.py`.
- [ ] Delete `lca/plugins/loop/state/stop_policy/`.
- [ ] Delete `lca/plugins/loop/phase/stop/should_check/plugin.py`.
- [ ] Delete `lca/plugins/loop/phase/stop/should_check/`.
- [ ] Delete `lca/plugins/loop/phase/stop/focus/plugin.py`.
- [ ] Delete `lca/plugins/loop/phase/stop/focus/`.
- [ ] Delete `lca/plugins/loop/phase/stop/fail/plugin.py`.
- [ ] Delete `lca/plugins/loop/phase/stop/fail/`.
- [ ] Delete `lca/plugins/loop/phase/stop/`.
- [ ] Delete `lca/plugins/loop/control/stop_decide/plugin.py`.
- [ ] Delete `lca/plugins/loop/control/stop_decide/`.
- [ ] Delete `lca/plugins/loop/control/stop_focus/plugin.py`.
- [ ] Delete `lca/plugins/loop/control/stop_focus/`.
- [ ] Delete `lca/plugins/concept/stop_should_check/decide.py`.
- [ ] Delete `lca/plugins/concept/stop_should_check/focus_converge.py`.
- [ ] Delete `lca/plugins/concept/stop_should_check/`.
- [ ] Delete `bundles/stop_subgraph.yaml`.
- [ ] Delete `bundles/concept/stop_should_check.yaml`.
- [ ] Delete `bundles/agent/stop_turn.yaml`.
- [ ] Delete `tests/plugins/state/test_stop_policy.py`.
- [ ] Delete `tests/plugins/state/test_stop_policy_delivery.py`.
- [ ] Delete `tests/plugins/state/test_stop_policy_delivery_via_observation.py`.
- [ ] Delete `tests/plugins/state/test_stop_policy_no_second_think_repro.py`.
- [ ] Delete `tests/agent_lab/test_stop_focus_subgraph.py`.
- [ ] Edit `bundles/base.yaml` (lines 125-162, 140-141).
- [ ] Edit `bundles/runtime-core.yaml` (lines 9-11).
- [ ] Edit `bundles/web-app.yaml` (lines 124-126).
- [ ] Edit `lca/contracts/__init__.py` and `lca/contracts/protocols/__init__.py`.
- [ ] Edit `lca/contracts/protocols/README.md:181`.
- [ ] Edit `lca/contracts/harness/act/effect_receipt.py:42`.
- [ ] Edit `lca/contracts/models/core/state/state.py:40, 115`.
- [ ] Edit `lca/plugins/composer/runtime/fixture/runtime_adapter.py:44, 59`.
- [ ] Edit `lca/plugins/composer/perceive/perceive.py`.
- [ ] Edit `lca/plugins/composer/perceive/composer.py`.
- [ ] Edit `lca/plugins/composer/runtime/fixture/runtime_input.py`.
- [ ] Edit `lca/plugins/lab/control/ops.py:133, 294, 297-299, 506`.
- [ ] Edit `lca/plugins/agent/run_phase/loop.py`.
- [ ] Edit `lca/plugins/act/delta/handlers_provider.py:159-169`.
- [ ] Edit `lca/plugins/act/action/handlers_provider.py:71`.
- [ ] Edit `lca/plugins/loop/reducer/plugin.py:279-371` docstrings.
- [ ] Edit `lca/plugins/concept/reflection_critique/observation_build.py:86` docstring.
- [ ] Edit `lca/plugins/control_contributions/__init__.py:12-25` and `lca/plugins/control_contributions/README.md:41, 46`.
- [ ] Edit `lca/runtime/agent_runtime/phases.py:11`.
- [ ] Edit `lca/plugins/tools/diagnostics/debug/run.py:430-440`.
- [ ] Edit `lca/infrastructure/cli/commands/journal_extra/journal_trace.py:295-391, 605-615`.
- [ ] Edit `scripts/lca-inspect-plan.py:55-154`.
- [ ] Edit `scripts/e2e_smoke_test.py:195`.
- [ ] Edit `agent_lab/graphs/configs/control/stop_decide.yaml`.
- [ ] Edit `agent_lab/graphs/configs/control/stop_focus.yaml`.
- [ ] Edit `agent_lab/_lca_paths.py:107, 110`.
- [ ] Edit `agent_lab/profile_loader.py:17, 38`.
- [ ] Edit `tests/cognition/test_convergence_grace.py:12, 63, 65`.
- [ ] Edit `tests/runtime/test_terminal_outcome_integration.py:24, 32, 34`.
- [ ] Edit `tests/runtime/test_reducer.py:13, 25, 88, 104, 170, 218, 239, 359`.
- [ ] Edit `tests/scenario/protocol/test_protocol_compliance.py:61, 198, 248`.
- [ ] Edit `tests/scenario/architecture/test_architecture_deepening.py:47, 141`.
- [ ] Edit `tests/scenario/handoff/test_handoff_strategy.py:209, 244, 207`.
- [ ] Edit `tests/scenario/refactor/test_refactor_guards.py:35`.
- [ ] Edit `tests/composer/test_composer_consumes_compiled_capability.py:217, 221, 231, 237`.
- [ ] Edit `tests/harness/test_think_guard_consumer.py:174, 175, 204, 205, 208, 214`.
- [ ] Edit `tests/harness/test_c1_phase_substeps_guard.py:187, 188, 194, 198, 213`.
- [ ] Edit `tests/harness/test_plugin_optional_fields.py:280, 281`.
- [ ] Edit `tests/composer/test_agent_assembly_runtime_bindings.py:4`.
- [ ] Edit `tests/composer/test_phase_capability_contributions.py:104`.
- [ ] Edit `tests/agent_lab/test_stop_subgraph.py`.
- [ ] Edit `tests/agent_lab/test_control_slot_graphs.py:102, 108`.
- [ ] Edit `tests/contracts/test_terminal_outcome_contract.py:287, 289`.
- [ ] Edit `tests/contracts/test_agent_state_shape.py:70`.
- [ ] Edit `tests/contracts/test_boundary_dto_frozen.py:425, 430, 437`.
- [ ] Edit `tests/scenario/contracts/test_contracts_purity.py:55`.
- [ ] Edit `tests/scenario/run_1/test_run_diagnostic.py:23, 29, 113, 151, 184`.
- [ ] Edit `tests/scenario/clean/test_clean_truths_phase_error_kind.py:17`.
- [ ] Edit `tests/declarative/test_phase_subgraph_parity.py:167`.
- [ ] Edit `tests/loop/commit/test_record_step_tool_result_failure_kind.py:4`.
- [ ] Edit `tests/plugins/concept/reflection_critique/test_reflect_observation_build_failure_kind.py:6`.
- [ ] Edit `tests/scenario/boot/test_boot_binding_completeness.py:191`.
- [ ] Edit `tests/e2e/test_declarative_long_horizon_recovery.py:71, 73`.
- [ ] Edit `tests/architecture/test_p7_region_migration.py:79`.
- [ ] Create `tests/refactor/test_no_stop_decision_residue.py`.
- [ ] Edit `docs/adr/0094-stop-policy-locality.md` (mark superseded).
- [ ] Edit `docs/adr/README.md:70`.
- [ ] Edit `docs/specs/glossary.md`.
- [ ] Edit `docs/specs/tool-failure-recovery.md:130, 132`.
- [ ] Edit `docs/specs/harness-spine-spec.md:1160, 1167`.
- [ ] Edit `docs/specs/lca-structured-cognition-guide.md:313`.
- [ ] Edit `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md:993, 3864, 3906`.
- [ ] Edit `docs/design/2026-08-21-agent-primitive-system-constitution.md:164`.
- [ ] Edit `docs/notes/implemented/seam/2026-09-12-six-phase-subgraph-cutover.md:91, 107, 108, 311`.
- [ ] Edit `docs/notes/baselines/plugin-id-grammar.json:170, 171, 199`.
- [ ] Edit `docs/notes/baselines/capability-set-web-standard-pre-pr10.json:2091, 2211, 2215, 2221, 2225`.
- [ ] Edit `docs/notes/baselines/capability-set-web-standard-recovery-pre-pr10.json:2091, 2211, 2215, 2221, 2225`.
- [ ] Edit `docs/notes/baselines/capability-set-self-improving-minimal-pre-pr10.json:2102, 2222, 2226, 2232, 2236`.
- [ ] Edit `docs/plans/2026-08-27-agent-loop-focus-governance.md:15`.
- [ ] Edit `docs/plans/2026-09-01-run-failure-rca-and-fix-plan.md`.
- [ ] Edit `CONTEXT.md:13`.

**Build.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Delete the eight retired plugin modules under `lca/plugins/loop/state/stop_policy/`, `lca/plugins/loop/phase/stop/{should_check,focus,fail}/`, `lca/plugins/loop/control/{stop_decide,stop_focus}/`, and `lca/plugins/concept/stop_should_check/{decide,focus_converge}.py`.
- [ ] Delete the three retired bundle YAMLs `bundles/stop_subgraph.yaml`, `bundles/concept/stop_should_check.yaml`, `bundles/agent/stop_turn.yaml`.
- [ ] Edit `bundles/base.yaml`, `bundles/runtime-core.yaml`, `bundles/web-app.yaml` to drop the `state.stop-policy.default` and `phase.stop.*` plugin entries.
- [ ] Edit `bundles/phase_main_outer.yaml` consumer references (none expected, PR-4 already replaced `stop.main`).
- [ ] Update `lca/contracts/__init__.py`, `lca/contracts/protocols/__init__.py`, `lca/contracts/protocols/README.md`, `lca/contracts/harness/act/effect_receipt.py`, `lca/contracts/models/core/state/state.py` to remove StopPolicy references.
- [ ] Update `lca/plugins/composer/runtime/fixture/runtime_adapter.py`, `lca/plugins/composer/perceive/perceive.py`, `lca/plugins/composer/perceive/composer.py`, `lca/plugins/composer/runtime/fixture/runtime_input.py` to drop the `stop_policy` seam.
- [ ] Update `lca/plugins/lab/control/ops.py` to drop `LcaControlStopPolicyProvider` and the CONTINUE-only fallback StopPolicy.
- [ ] Update `lca/plugins/agent/run_phase/loop.py`, `lca/plugins/act/delta/handlers_provider.py`, `lca/plugins/act/action/handlers_provider.py` to drop the now-dead stop handlers.
- [ ] Update `lca/runtime/agent_runtime/phases.py`, `lca/plugins/tools/diagnostics/debug/run.py`, `lca/infrastructure/cli/commands/journal_extra/journal_trace.py`, `scripts/lca-inspect-plan.py`, `scripts/e2e_smoke_test.py` to drop the StopPolicy references.
- [ ] Update `agent_lab/graphs/configs/control/stop_decide.yaml`, `agent_lab/graphs/configs/control/stop_focus.yaml`, `agent_lab/_lca_paths.py`, `agent_lab/profile_loader.py` to drop StopPolicy / phase.stop references.
- [ ] Update the 23 test files listed in the Files. block to drop `DefaultStopPolicy` imports, `StopDecision(should_stop=...)` constructions, and the `control.stop.*` plugin id assertions.
- [ ] Delete `tests/plugins/state/test_stop_policy.py`, `tests/plugins/state/test_stop_policy_delivery.py`, `tests/plugins/state/test_stop_policy_delivery_via_observation.py`, `tests/plugins/state/test_stop_policy_no_second_think_repro.py`, `tests/agent_lab/test_stop_focus_subgraph.py`.
- [ ] Update docs `docs/adr/0094-stop-policy-locality.md`, `docs/adr/README.md`, `docs/specs/glossary.md`, `docs/specs/tool-failure-recovery.md`, `docs/specs/harness-spine-spec.md`, `docs/specs/lca-structured-cognition-guide.md`, `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`, `docs/design/2026-08-21-agent-primitive-system-constitution.md`, `docs/notes/implemented/seam/2026-09-12-six-phase-subgraph-cutover.md`, `docs/notes/baselines/plugin-id-grammar.json`, `docs/notes/baselines/capability-set-*-pre-pr10.json`, `docs/plans/2026-08-27-agent-loop-focus-governance.md`, `docs/plans/2026-09-01-run-failure-rca-and-fix-plan.md`, `CONTEXT.md` to remove or supersede StopPolicy references.
- [ ] Update `tests/architecture/test_p7_region_migration.py` to drop the `phase:stop` region assertion.
- [ ] Add the new `tests/refactor/test_no_stop_decision_residue.py` that asserts zero hits for the retired symbols.

**You see.**

- [ ] `grep -rln "StopPolicy\|DefaultStopPolicy\|StopDecision.should_stop" lca/ bundles/ profiles/ tests/ scripts/ docs/ agent_lab/ 2>/dev/null | grep -v __pycache__` returns only the archival `docs/adr/0094-stop-policy-locality.md` and `docs/specs/glossary.md` retired-mention entries.
- [ ] `grep -rln "phase.stop\.\|stop_should_check\|stop_focus\|stop_decide\|control\.stop\." lca/plugins/ bundles/ profiles/ 2>/dev/null | grep -v __pycache__` returns zero hits.
- [ ] `python -c "from lca.plugins.loop.state.stop_policy.plugin import DefaultStopPolicy"` raises `ModuleNotFoundError`.
- [ ] `./scripts/lca-ops runs create --user-text "echo smoke" --profile web-standard --wait --json` still completes successfully (the kernel has not been broken by the deletion).

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/refactor/test_no_stop_decision_residue.py` (new file) greps the entire repo for `StopPolicy`, `DefaultStopPolicy`, `phase.stop.*`, `StopDecision.should_stop`, `control.stop.*`, `StopReason.TASK_COMPLETED`, `_delivery_satisfied_stop`, `_completed_decision`, `_budget_exhausted_decision`, `_deterministic_failure_stop`, `state.stop-policy.default`, `StopShouldCheckExecutor`, `StopFocusExecutor`, `StopFailExecutor`, `FocusStopExecutor`, `StopDecideExecutor`, `StopShouldDecideExecutor`, `StopFocusConvergeExecutor`, and asserts no production hit. Run.
- [ ] `python -m pytest tests/ -v` exits 0.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Trunk imports `DefaultStopPolicy`; head must not. Pass when `python -c "from lca.plugins.loop.state.stop_policy.plugin import DefaultStopPolicy"` raises `ModuleNotFoundError` on the head and succeeds on trunk. Save `/tmp/swarm-PR-5/worker-1/lane_1.png`.
- [ ] Lane 2. End-to-end smoke. `./scripts/lca-ops runs create --user-text "echo smoke" --profile web-standard --wait --json` exits 0 and produces a completed run. Pass when exit is 0 and the run's `terminal_outcome=completed`. Save `/tmp/swarm-PR-5/worker-2/lane_2.png`.
- [ ] Lane 3. `./scripts/lca-ops audit-plugin-shape` exits 0. Save `/tmp/swarm-PR-5/worker-3/lane_3.png`. Pass when the named command exits 0.
- [ ] Lane 4. `python -m pytest tests/ -v` exits 0 across the full repo. Save `/tmp/swarm-PR-5/worker-4/lane_4.png`. Pass when the named command exits 0.
- [ ] Lane 5. `python scripts/check_plugin_shape.py` exits 0. Save `/tmp/swarm-PR-5/worker-5/lane_5.png`. Pass when the named command exits 0.
- [ ] Lane 6. `python scripts/check_plugin_metadata.py` exits 0. Save `/tmp/swarm-PR-5/worker-6/lane_6.png`. Pass when the named command exits 0.
- [ ] Lane 7. `python scripts/check_plugin_capability.py` exits 0. Save `/tmp/swarm-PR-5/worker-7/lane_7.png`. Pass when the named command exits 0.
- [ ] Lane 8. `python scripts/check_protocol_impl.py` exits 0. Save `/tmp/swarm-PR-5/worker-8/lane_8.png`. Pass when the named command exits 0.
- [ ] Lane 9. `python scripts/check_assembly_purity.py` exits 0. Save `/tmp/swarm-PR-5/worker-9/lane_9.png`. Pass when the named command exits 0.
- [ ] Lane 10. `python scripts/check_run_debug_sync.py` exits 0. Save `/tmp/swarm-PR-5/worker-10/lane_10.png`. Pass when the named command exits 0.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Total number of plugin files under `lca/plugins/`.
- [ ] Probe. Run `find lca/plugins -name "*.py" | wc -l` at trunk and at head.
- [ ] Baseline. Record trunk file count first.
- [ ] Rule. Head file count must be at least 11 fewer than trunk (8 stop plugin files + 2 concept executors + 1 re-export barrel). Smaller reduction means a deletion was missed.

**Review gate.** None. PR-5 is deletion only. The interaction change is in PR-4 (already reviewed).

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.

## PR-6 closed-loop e2e regression suite covering every historical class

**Depends on.** PR-5.

**Files.**

- [ ] Create `tests/e2e/test_stop_decision_retirement_e2e.py`.
- [ ] Create `scripts/run_stop_retirement_e2e.py` (the verifier).
- [ ] Edit `scripts/check_run_debug_sync.py` (verify the new `lca-ops run-stop-retirement-e2e` command is registered).
- [ ] Edit `lca/infrastructure/cli/cli.py` or equivalent to register `run-stop-retirement-e2e` if not already.
- [ ] Edit `docs/debug/run-debug-guide.md` to add a new step that points at `lca-ops run-stop-retirement-e2e <run_id>` for diagnosing post-retirement stop regressions.
- [ ] Edit `docs/specs/glossary.md` to add `terminal commit` and `DeterministicToolError` entries.
- [ ] Edit `docs/adr/0094-stop-policy-locality.md` to mark `status: superseded by 2026-09-14-stop-decision-retirement.md` (PR-5 already covered the file header; this PR adds the cross-link).
- [ ] Create `docs/adr/0230-stop-decision-retirement.md` (new ADR) documenting the final shape. `decision.action_type` + Body raise + reducer commit; supersedes ADR-0094 §"StopPolicy 的 State 群局部性" content (keep the file for audit history, mark with `status: superseded`).

**Build.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] New e2e suite covers, end-to-end, the three historical regression classes plus the post-retirement correctness class. Each scenario produces a run; the verifier checks the run's `terminal_outcome` and event stream.
  - Scenario A. `run_2cd22760a828` shape (single successful tool, expectation that the loop does NOT cycle). Triggers `SPINE_BODY_DETERMINISTIC_FAIL` only if the tool returns a deterministic failure; otherwise terminates via `SPINE_TERMINAL_COMMIT`. Asserts total LLM round-trips <= 2.
  - Scenario B. `run_0d71855ae274` shape (deterministic failure, expectation that the loop terminates on first attempt via Body raise). Asserts `SPINE_BODY_DETERMINISTIC_FAIL` emitted, total LLM round-trips == 1, `terminal_outcome=failed`.
  - Scenario C. `run_def5b19c20c0` shape (use_tool + summarize). Asserts total LLM round-trips >= 2 (the second think fires), final output non-empty, `terminal_outcome=completed`.
  - Scenario D. clean RESPOND only. Asserts total LLM round-trips == 1, `terminal_outcome=completed`.
  - Scenario E. budget exhaustion. Force `state.budget.exceeded()` mid-loop. Asserts `SPINE_TERMINAL_COMMIT` with `reason=BUDGET_EXCEEDED`, `terminal_outcome=failed`.
- [ ] New CLI command `lca-ops run-stop-retirement-e2e` runs all five scenarios and prints a pass/fail table per run id + scenario name. Returns exit 0 only if all five pass.
- [ ] Add the command to `scripts/check_run_debug_sync.py` enforcement list so any future doc reference must match a real CLI registration.
- [ ] Update `docs/debug/run-debug-guide.md` with a new Step 0e that references `lca-ops run-stop-retirement-e2e` as the canonical regression-class sweep after any stop-touching code change.
- [ ] New ADR-0230 documents the final mechanism in one page. Keep it under 80 lines per the prose budget.

**You see.**

- [ ] `lca-ops run-stop-retirement-e2e` exits 0 with a 5-row pass table.
- [ ] `python scripts/check_run_debug_sync.py` exits 0.
- [ ] `python -m pytest tests/e2e/test_stop_decision_retirement_e2e.py -v` exits 0.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/unit/test_run_stop_retirement_e2e_script.py` (new file) invokes the script as a subprocess and asserts exit codes for the happy path plus a deliberately-broken fixture run. Run.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe. Each lane runs one of the five scenarios from a cold start.

- [ ] Lane 1. Scenario A on a cold VM. Pass when `terminal_outcome=completed` and LLM round-trips <= 2. Save `/tmp/swarm-PR-6/worker-1/lane_1.png`.
- [ ] Lane 2. Scenario B on a cold VM. Pass when `terminal_outcome=failed` and `SPINE_BODY_DETERMINISTIC_FAIL` appears exactly once. Save `/tmp/swarm-PR-6/worker-2/lane_2.png`.
- [ ] Lane 3. Scenario C on a cold VM. Pass when `terminal_outcome=completed`, LLM round-trips >= 2, and the second-think assistant message contains a non-empty summary. Save `/tmp/swarm-PR-6/worker-3/lane_3.png`.
- [ ] Lane 4. Scenario D on a cold VM. Pass when `terminal_outcome=completed` and LLM round-trips == 1. Save `/tmp/swarm-PR-6/worker-4/lane_4.png`.
- [ ] Lane 5. Scenario E on a cold VM. Pass when `terminal_outcome=failed` and `SPINE_TERMINAL_COMMIT` carries `reason=BUDGET_EXCEEDED`. Save `/tmp/swarm-PR-6/worker-5/lane_5.png`.
- [ ] Lane 6. `lca-ops run-stop-retirement-e2e` exits 0 on a fresh kernel. Save `/tmp/swarm-PR-6/worker-6/lane_6.png`. Pass when the named command exits 0.
- [ ] Lane 7. `python -m pytest tests/e2e/ -v` exits 0. Save `/tmp/swarm-PR-6/worker-7/lane_7.png`. Pass when the named command exits 0.
- [ ] Lane 8. `python scripts/check_run_debug_sync.py` exits 0. Save `/tmp/swarm-PR-6/worker-8/lane_8.png`. Pass when the named command exits 0.
- [ ] Lane 9. `python scripts/check_doc_layering.py` exits 0. Save `/tmp/swarm-PR-6/worker-9/lane_9.png`. Pass when the named command exits 0.
- [ ] Lane 10. `python scripts/verify_doc_slop.py` exits 0. Save `/tmp/swarm-PR-6/worker-10/lane_10.png`. Pass when the named command exits 0.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `lca-ops run-stop-retirement-e2e` on a cold kernel.
- [ ] Probe. Run at trunk (replays existing e2e suite as baseline) and at head.
- [ ] Baseline. Record trunk wall time first.
- [ ] Rule. Head wall time must be at most trunk wall time plus 30 percent. Larger regression means the new mechanism added per-scenario overhead beyond what the design budget allows.

**Review gate.** None. PR-6 is a test + docs + ADR PR; the interaction changes live in PR-4 (already reviewed).

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] This is the stack root. Operator lands the contiguous verified run bottom-up through `gh` per the Shipping playbook.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the report the autopilot-stack playbook names.

## Appendix A. Prototype evidence

Two prototypes informed the design. Both live as branches off `main` and have their SHAs recorded here for replay.

- **Prototype 1 .  `decision.action_type` driver.** Branch `proto/decision-action-type-driver`. SHA recorded at program arm. Validated that `apply_stop` accepts a `StopDecision` built directly from `Decision(action_type=RESPOND, response_text=...)` without any policy instance.
- **Prototype 2 .  Body raise path.** Branch `proto/body-deterministic-raise`. SHA recorded at program arm. Validated that `DeterministicToolError` raised from Body propagates into the outer driver and produces `terminal_outcome=failed` in one round-trip.

Two questions stay unproven before PR-1 merges.

- Whether the `BindingKind.TERMINAL_COMMIT` new binding kind collides with any existing binding kind dispatch path. PR-4 carries the load test.
- Whether the `ControlTrace.verdict_kind` extension (literal `"terminate"`) is acceptable under the `m5_event_traces` schema version. PR-2 carries the load test.

## Appendix B. Alternatives rejected

- **Patch `_delivery_satisfied_stop` with a "skip when model intended post-tool commentary" heuristic.** Rejected. Heuristics on model intent are exactly the kind of host-side speculation ADR-0196 CV4 was meant to discourage. They are also unprovable on a closed loop.
- **Add a `pending_summary` flag to `Decision`.** Rejected. Encoding a speculation about what the model will do next in the model output is a contract violation. The new mechanism lets the model emit another `Decision` instead.
- **Keep `DefaultStopPolicy` but gut `_delivery_satisfied_stop`.** Rejected. The bug is in the existence of the policy class, not in any single method. ADR-0094 already demonstrated the right pattern. Collapse the layer, not patch the layer.
- **Move stop-decision into a "model adapter" plugin.** Rejected. Adds a layer without changing the mechanism. The plan keeps the policy out and lets the model drive directly.

## Appendix C. Risks

- **Risk.** PR-4's new `terminal.commit` edge predicates depend on `result.payload.should_terminate` being stamped by the outer driver. If the driver stamping is buggy, the loop never terminates or terminates early. Owner watches, PR-4 owner. Mitigation, the swarm's ten-lane sweep on PR-4 covers this.
- **Risk.** The `BindingKind.TERMINAL_COMMIT` addition could shadow an existing binding kind's dispatch and silently break unrelated bundles. Owner watches, PR-4 owner. Mitigation, PR-4 carries a binding-dispatch table test.
- **Risk.** ADR-0094 supersession may orphan ADRs that reference it (0168, 0168.1, 0169, 0171, 0173) without picking up the cross-link. Owner watches, PR-5 owner. Mitigation, PR-5 edits those ADRs' "Builds on" lines.
- **Risk.** PR-5's deletion sweep may leave dangling references if any path bypassed the inventory. Owner watches, PR-5 owner. Mitigation, the new `test_no_stop_decision_residue.py` greps the whole repo and fails CI on any hit.
- **Risk.** PR-6's budget-exhaustion scenario depends on forcing `state.budget.exceeded()` from a test fixture, which may not match production budget accounting. Owner watches, PR-6 owner. Mitigation, Scenario E uses the same Budget class as production (`lca.contracts.models.core.policy.budget.create_budget`); if the production path uses a different code path, the test fails loud.

## Appendix D. Links and reading list

- `docs/adr/0094-stop-policy-locality.md` is the precedent for collapsing stop-decision into one deep module. This plan finishes the job.
- `docs/adr/0196-convergence-control-plane-and-prompt-surface.md` carries CV4 (`_delivery_satisfied_stop`). The regression classes it guards now move to Body and to `decision.action_type`.
- `docs/adr/0217-bundle-graph-schema-v2.md` defines the Bundle graph schema. The `terminal.commit` node is a first-class node under this schema.
- `docs/adr/0221-concept-decision-classify-parse-merge.md` performs the six-phase subgraph cutover. `stop.main` was the last node still doing "judgment" work after this ADR. PR-4 removes that.
- `docs/specs/glossary.md` is the single source of truth for the new `terminal commit` term.
- `pstack/skills/poteto-mode/playbooks/autopilot-stack.md` is the execution playbook for this plan.
- `pstack/skills/poteto-mode/playbooks/shipping.md` is read before landing the stack root.
- `pstack/skills/poteto-mode/playbooks/opening-a-pr.md` is read before opening any PR in the stack.
- `pstack/skills/how/SKILL.md` is read by the PR-4 owner before designing the new binding kind.
- `pstack/skills/interrogate/SKILL.md` is read by PR-5 owner before the deletion sweep.