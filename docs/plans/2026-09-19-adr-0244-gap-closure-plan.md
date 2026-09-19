# ADR-0244 gap closure program

Close the five remaining ADR-0244 gaps. The legacy conversation fallback channel, the H7 heuristic, the dead memory retrieval node, the placeholder workspace service, the missing procedural-memory curator, and the missing token budget on the frontend gateway. Each PR is one change with its own evidence. PR-1 through PR-6 implement, PR-7 marks the ADR implemented.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. The operator reviews and lands the stack. PR-6 is the operator's review item and stops at merge-ready for review.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on her explicit go.
- [ ] On her go, arm a `/goal` with this exact text. "Run docs/plans/2026-09-19-adr-0244-gap-closure-plan.md. Implement PR-1 through PR-7 in order. Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The operator reviews and lands the stack. Done when PR-7 is merge-ready."
- [ ] Read these from trunk at program start. Re-read them at every tick.
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `git show origin/main:pstack/skills/swarm/SKILL.md`
  - [ ] `git show origin/main:.agents/skills/lca-pre-push-checks/SKILL.md`
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `git show origin/main:docs/AGENTS.md`
- [ ] Arm the 30-minute audit tick. In a local session, a real terminal `/loop`. In a cloud root, a cloud-sleeper wake chain. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from trunk and the armed /goal. Audit the operation against both and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then send the operator a status message, whether or not anything changed, with the queue table of PR, owner, state, and head SHA, the verdicts since the last tick, what merged, open operator gates, and blockers."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the execution playbook names.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges, or base it on the parent branch when the execution playbook stacks.
  - [ ] PR-1, PR-2, PR-3, PR-4, PR-5, and PR-6 are independent and first. All branch from `main`.
  - [ ] PR-7 after PR-1, PR-2, PR-3, PR-4, PR-5, and PR-6.
- [ ] Hold the file boundaries. PR-1 touches only `lca/runtime/loop/runtime_loop.py`, `lca/contracts/models/core/conversation/conversation.py`, and `tests/runtime/loop/`. PR-2 touches only `lca/plugins/transport/webserver/doctor/step_check.py` and `tests/plugins/transport/webserver/doctor/`. PR-3 touches only `lca/contracts/protocols/memory/`, `lca/cognition/memory/`, `lca/infrastructure/memory/`, `lca/nodes/perceive/`, `bundles/perceive/`, and `tests/integration/`. PR-4 touches only `lca/infrastructure/workspace/`, `lca/plugins/memory/`, and `tests/infrastructure/workspace/`. PR-5 touches only `lca/plugins/assistant/`, `bundles/assistant-runtime.yaml`, `lca/contracts/observability/closure/`, and `tests/plugins/assistant/`. PR-6 touches only `deploy/lobehub/patches/runtime/lcaGateway/` and `deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py`. PR-7 touches only `docs/adr/`, `docs/adr/README.md`, and `docs/notes/`.
- [ ] Hold the review gate. PR-6 changes an interaction. It waits for the operator's review in chat with screenshots and a video before merge.

### PR mechanics, for every PR

- [ ] Resolve the forge once. `gh` is available and `gt` is not. Use `gh pr create` for every PR operation. Never require `gt`.
- [ ] Open the PR ready, never draft, with `gh pr create --base <base-branch>`.
- [ ] Run the repo's lint and typecheck once before the PR-facing push. Push with hooks on.
- [ ] Run `/deslop` before each commit and `/no-comments` before review.
- [ ] Triage every Bugbot and security-reviewer comment per `../references/bugbot-triage.md`.
- [ ] Rebase onto current trunk before babysit and again before the merge-ready report.

### Verdict and merge, for every PR

- [ ] At the merge-ready head SHA, run the swarm per `pstack/skills/swarm/SKILL.md`. One gates lane. The ten live lanes from the PR's `Verify, live` block. The perf lane from its `Verify, perf` block. One audit lane that reads the diff and the receipts and distrusts the PR body.
- [ ] Clean only when every lane is `PASS`. Findings go back to the owner. A new head gets a fresh swarm and a fresh verdict.
- [ ] Append the PR to the one linear base-branch stack per `playbooks/autopilot-stack.md`, with the patch-id rule from `playbooks/shipping.md`.

### Boot recipe, for every live lane

Each live lane runs on its own cloud VM at the PR head. Drive through `control-cli` from `cursor-team-kit`.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] Start the backend with `./scripts/lca-ops kernel-restart` and the web profile. Wait for ready.
- [ ] Deliver input only through the control skill's commands. Name the read-only diagnostics.
- [ ] Save every screenshot to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.png` and return the paths with the report.

## Retire the prior-conversation fallback channel (PR-1)

**Depends on.** None.

**Files.**

- [ ] Edit `lca/runtime/loop/runtime_loop.py`.
- [ ] Edit `lca/contracts/models/core/conversation/conversation.py`.
- [ ] Create `tests/runtime/loop/test_runtime_loop_prior_turns.py`.

**Build.**

- [ ] Remove the `PRIOR_CONVERSATION_WM_KEY` import and the fallback branch in `runtime_loop.py` so `prior_turns = ctx.prior_turns` is the only source.
- [ ] Delete the `PRIOR_CONVERSATION_WM_KEY` constant from `conversation.py` when no consumer remains.

**You see.**

- [ ] `rg PRIOR_CONVERSATION_WM_KEY lca` returns no matches.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_runtime_loop_prior_turns.py` gains `test_extra_fallback_channel_is_ignored` and `test_prior_turns_seed_via_session_writer`. Run `uv run pytest tests/runtime/loop/test_runtime_loop_prior_turns.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `uv run pytest tests/runtime/session/test_seed_prior_turns.py -v` at trunk and head. Save `pr1-lane1.png`. Pass when both suites pass.
- [ ] Lane 2. Boot `profiles/web-assistant.yaml` and create a run with `--user-text "hello"`. Save `pr1-lane2.png`. Pass when the run completes.
- [ ] Lane 3. Start a run whose carrier context carries `extra["prior_conversation"]`. Save `pr1-lane3.png`. Pass when the journal contains no `historical` events from the fallback channel.
- [ ] Lane 4. Start a run with two prior turns in `ctx.prior_turns`. Save `pr1-lane4.png`. Pass when the first `llm.request.header` message chain contains both prior turns.
- [ ] Lane 5. Replay the seeded run journal. Save `pr1-lane5.png`. Pass when `lca-ops journal replay` shows the historical messages.
- [ ] Lane 6. Run `uv run pytest tests/runtime/ -v`. Save `pr1-lane6.png`. Pass when the runtime suite passes.
- [ ] Lane 7. Run `uv run pytest tests/plugins/session/ -v`. Save `pr1-lane7.png`. Pass when the session suite passes.
- [ ] Lane 8. Run `uv run ruff check lca/runtime/loop lca/contracts/models/core/conversation`. Save `pr1-lane8.png`. Pass when ruff reports no errors.
- [ ] Lane 9. Run `uv run mypy lca/runtime/loop/runtime_loop.py`. Save `pr1-lane9.png`. Pass when mypy exits 0.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr1-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Run startup wall time from `kernel-restart` to `status --json` healthy.
- [ ] Probe. Run `time ./scripts/lca-ops kernel-restart` at trunk and head, interleaved.
- [ ] Baseline. Record the trunk startup time first.
- [ ] Rule. Head startup time must not exceed trunk by more than 500 ms.

**Review gate.** None. PR-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Remove the H7 heuristic fallback (PR-2)

**Depends on.** None.

**Files.**

- [ ] Edit `lca/plugins/transport/webserver/doctor/step_check.py`.
- [ ] Edit `tests/plugins/transport/webserver/doctor/test_doctor_h7_reconciliation.py`.

**Build.**

- [ ] Delete the `forked = scan.total_steps == scan.tool_total < spine_total` fallback branch in `_hop_h7`.
- [ ] Keep the `journal_invs` versus `spine_invs` set reconciliation as the only mismatch detector.

**You see.**

- [ ] `rg "total_steps == scan.tool_total" lca` returns no matches.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_doctor_h7_reconciliation.py` gains `test_h7_uses_set_reconciliation_when_step_info_missing`. Run `uv run pytest tests/plugins/transport/webserver/doctor/test_doctor_h7_reconciliation.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the doctor H7 suite at trunk and head. Save `pr2-lane1.png`. Pass when both suites pass.
- [ ] Lane 2. Boot the kernel and run a text-only run. Save `pr2-lane2.png`. Pass when `doctor` reports `broken_hop=None`.
- [ ] Lane 3. Run a run with four concurrent `exportFile` calls. Save `pr2-lane3.png`. Pass when H7 reports ok and the journal holds all four invocation ids.
- [ ] Lane 4. Run `uv run pytest tests/plugins/transport/webserver/doctor/ -v`. Save `pr2-lane4.png`. Pass when the doctor suite passes.
- [ ] Lane 5. Run `uv run pytest tests/contracts/models/observability/ -v`. Save `pr2-lane5.png`. Pass when the journal model suite passes.
- [ ] Lane 6. Run `uv run ruff check lca/plugins/transport/webserver/doctor`. Save `pr2-lane6.png`. Pass when ruff reports no errors.
- [ ] Lane 7. Run `uv run mypy lca/plugins/transport/webserver/doctor/step_check.py`. Save `pr2-lane7.png`. Pass when mypy exits 0.
- [ ] Lane 8. Run `./scripts/lca-ops debug-run $(ls -1t traces/runs | head -1)`. Save `pr2-lane8.png`. Pass when the debug output shows no H7 false positive.
- [ ] Lane 9. Run `uv run pytest tests/integration/ -v`. Save `pr2-lane9.png`. Pass when the integration suite passes.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr2-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `_hop_h7` wall time on a run with 200 steps.
- [ ] Probe. Run `uv run python -m cProfile -s cumtime -m pytest tests/plugins/transport/webserver/doctor/test_doctor_h7_reconciliation.py` at trunk and head, interleaved.
- [ ] Baseline. Record the trunk `_hop_h7` cumulative time first.
- [ ] Rule. Head time must not exceed trunk by more than 10%.

**Review gate.** None. PR-2 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Wire memory retrieval to a live provider (PR-3)

**Depends on.** None.

**Files.**

- [ ] Edit `lca/contracts/protocols/memory/memory.py`.
- [ ] Edit `lca/cognition/memory/simple/memory.py`.
- [ ] Edit `lca/cognition/memory/temporal/memory.py`.
- [ ] Edit `lca/infrastructure/memory/assistant_memory.py`.
- [ ] Edit `lca/nodes/perceive/memory_retrieve/memory_retrieve.py`.
- [ ] Edit `lca/nodes/perceive/fold/fold.py`.
- [ ] Edit `bundles/perceive/perceive_subgraph.yaml`.
- [ ] Edit `tests/integration/test_memory_and_procedural_distillation.py`.

**Build.**

- [ ] Add `async def retrieve(self, manifest) -> list[MemoryRecord]` to the `MemorySystem` protocol.
- [ ] Implement `retrieve` in `SimpleMemorySystem`, `TemporalMemorySystem`, and `AssistantMemory`.
- [ ] Change `memory_retrieve.py` to resolve `runtime.get("memory")` first and keep `memory_provider` as a test-only fallback.
- [ ] Change `fold.py` to declare `memories` in `declared_inputs` and merge them into the manifest as `ContextItem(kind="memory", payload=list(memories), provenance="memory.retrieve")`.
- [ ] Change `perceive_subgraph.yaml` so `phase.perceive.fold` declares `inputs: [manifest, memories]`.

**You see.**

- [ ] `uv run pytest tests/integration/test_memory_and_procedural_distillation.py -v` passes with a `runtime={"memory": ...}` case and a fold-merge assertion.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_memory_and_procedural_distillation.py` gains `test_fold_merges_retrieved_memories_into_manifest` and `test_memory_retrieve_resolves_canonical_memory`. Run `uv run pytest tests/integration/test_memory_and_procedural_distillation.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the memory and procedural distillation suite at trunk and head. Save `pr3-lane1.png`. Pass when both suites pass.
- [ ] Lane 2. Boot `profiles/web-assistant.yaml` and create an assistant from a role card. Save `pr3-lane2.png`. Pass when creation writes `{home}/memory/` and `{home}/workspace/`.
- [ ] Lane 3. Write a memory file into `{home}/memory/semantic.json`, then start a run. Save `pr3-lane3.png`. Pass when the first `llm.request.header` context manifest contains a `memory` item.
- [ ] Lane 4. Start a run with no memory file. Save `pr3-lane4.png`. Pass when the run completes and the manifest has no memory item, with no error.
- [ ] Lane 5. Replay the run journal. Save `pr3-lane5.png`. Pass when `lca-ops journal replay` shows the memory context item.
- [ ] Lane 6. Run `uv run pytest tests/contracts/protocols/ -v`. Save `pr3-lane6.png`. Pass when the protocol suite passes.
- [ ] Lane 7. Run `uv run pytest tests/cognition/ -v`. Save `pr3-lane7.png`. Pass when the cognition suite passes.
- [ ] Lane 8. Run `uv run ruff check --fix && uv run ruff format`. Save `pr3-lane8.png`. Pass when ruff reports no errors.
- [ ] Lane 9. Run `uv run mypy lca/contracts/protocols/memory lca/cognition/memory lca/nodes/perceive`. Save `pr3-lane9.png`. Pass when mypy exits 0.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr3-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `retrieve` latency on a 200-record memory file.
- [ ] Probe. Run `uv run python -m pytest tests/integration/test_memory_and_procedural_distillation.py -k retrieve` at trunk and head, interleaved.
- [ ] Baseline. Record the trunk `retrieve` wall time first.
- [ ] Rule. Head `retrieve` must complete under 10 ms for a 200-record file and under 2 ms for an empty file.

**Review gate.** None. PR-3 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Implement the persistent assistant workspace (PR-4)

**Depends on.** None.

**Files.**

- [ ] Create `lca/infrastructure/workspace/persistent_workspace.py`.
- [ ] Edit `lca/infrastructure/workspace/__init__.py`.
- [ ] Edit `lca/plugins/memory/store/workspace_provider.py`.
- [ ] Create `tests/infrastructure/workspace/test_persistent_workspace.py`.

**Build.**

- [ ] Implement `WorkspaceService` and `PersistentWorkspace` rooted at `{home}/workspace/` with `open`, `read`, `write`, and `list`, following the `AssistantMemory` plain-file pattern.
- [ ] Replace the placeholder `pass` in `workspace_provider.py` with `ctx.require("workspace").register("local", WorkspaceService())`.
- [ ] Remove the "does not yet exist" docstring in `workspace_provider.py`.

**You see.**

- [ ] Creating an assistant yields a `{home}/workspace/` directory that a service can read and write without touching the manifest digest.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_persistent_workspace.py` covers create, write, read, list, cross-assistant isolation, and digest non-participation. Run `uv run pytest tests/infrastructure/workspace/test_persistent_workspace.py tests/plugins/assistant/test_workspace.py tests/plugins/assistant/test_assistant_memory.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the assistant home and workspace suites at trunk and head. Save `pr4-lane1.png`. Pass when both suites pass.
- [ ] Lane 2. Boot `profiles/web-assistant.yaml` and create an assistant. Save `pr4-lane2.png`. Pass when `{home}/workspace/` exists and is empty.
- [ ] Lane 3. Write a file into the workspace through the service, then read it back. Save `pr4-lane3.png`. Pass when the content round-trips.
- [ ] Lane 4. Run `uv run pytest tests/integration/test_assistant_e2e.py -v`. Save `pr4-lane4.png`. Pass when the E2E suite passes.
- [ ] Lane 5. Run `uv run pytest tests/architecture/test_assistant_runtime_invariants.py tests/architecture/test_assistant_catalog_invariants.py -v`. Save `pr4-lane5.png`. Pass when the invariants hold.
- [ ] Lane 6. Run `uv run ruff check lca/infrastructure/workspace lca/plugins/memory/store/workspace_provider.py`. Save `pr4-lane6.png`. Pass when ruff reports no errors.
- [ ] Lane 7. Run `uv run mypy lca/infrastructure/workspace`. Save `pr4-lane7.png`. Pass when mypy exits 0.
- [ ] Lane 8. Run `uv run python -m deploy.lobehub.patch_lobehub verify`. Save `pr4-lane8.png`. Pass when the patch markers are intact.
- [ ] Lane 9. Run `uv run pytest tests/plugins/assistant/ -v`. Save `pr4-lane9.png`. Pass when the assistant plugin suite passes.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr4-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `WorkspaceService.write` latency for a 1 MB file.
- [ ] Probe. Run the workspace write benchmark at trunk and head, interleaved.
- [ ] Baseline. Record the trunk write time first.
- [ ] Rule. Head write must complete under 50 ms for a 1 MB file and must not exceed trunk by more than 10%.

**Review gate.** None. PR-4 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Add the procedural-memory curator (PR-5)

**Depends on.** None.

**Files.**

- [ ] Create `lca/plugins/assistant/curator/curator.py`.
- [ ] Edit `bundles/assistant-runtime.yaml`.
- [ ] Edit `lca/contracts/observability/closure/assistant_ep_closure.py`.
- [ ] Create `tests/plugins/assistant/test_curator.py`.

**Build.**

- [ ] Implement a `RuntimeLifecycleSubscriber` plugin registered through `RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY`.
- [ ] Read the `ProceduralMemoryCandidate` from run evidence via the journal reader keyed by `state_ref` or `journal_sequence`.
- [ ] Write a proposal to `{home}/.evolve/pending/` on candidate detection, defaulting to `experiment`.
- [ ] On user confirmation, call `create_assistant_skill` through the assistant skill overlay.
- [ ] Add any new event point to `ASSISTANT_EVENT_POINTS`.
- [ ] Register the plugin in `bundles/assistant-runtime.yaml`.

**You see.**

- [ ] A run with a multi-step tool chain produces a pending proposal file, and confirming it installs a skill under `{home}/skills/`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_curator.py` covers subscriber registration, candidate read, proposal write, confirmation install, and idempotency. Run `uv run pytest tests/plugins/assistant/test_curator.py tests/architecture/test_assistant_evolve_jobs_invariants.py tests/architecture/test_learning_review_lifecycle.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the assistant evolve and jobs suites at trunk and head. Save `pr5-lane1.png`. Pass when both suites pass.
- [ ] Lane 2. Boot `profiles/web-assistant.yaml` and run a two-step tool task. Save `pr5-lane2.png`. Pass when a `.evolve/pending/` proposal appears after the run.
- [ ] Lane 3. Confirm the proposal through the curator API. Save `pr5-lane3.png`. Pass when `{home}/skills/` contains the new skill.
- [ ] Lane 4. Run the same task twice. Save `pr5-lane4.png`. Pass when only one skill is installed and no duplicate proposal is written.
- [ ] Lane 5. Run a text-only run. Save `pr5-lane5.png`. Pass when no proposal is written.
- [ ] Lane 6. Run `uv run pytest tests/plugins/assistant/test_skill_overlay.py tests/plugins/assistant/test_evolve.py tests/plugins/assistant/test_jobs.py -v`. Save `pr5-lane6.png`. Pass when the suite passes.
- [ ] Lane 7. Run `uv run ruff check lca/plugins/assistant/curator`. Save `pr5-lane7.png`. Pass when ruff reports no errors.
- [ ] Lane 8. Run `uv run mypy lca/plugins/assistant/curator`. Save `pr5-lane8.png`. Pass when mypy exits 0.
- [ ] Lane 9. Run `./scripts/lca-ops audit-plugin-shape`. Save `pr5-lane9.png`. Pass when the curator plugin shape is valid.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr5-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Curator subscriber overhead on run terminalization.
- [ ] Probe. Measure `finalize_run` wall time at trunk and head, interleaved.
- [ ] Baseline. Record the trunk terminalize time first.
- [ ] Rule. Head terminalize must not exceed trunk by more than 50 ms.

**Review gate.** None. PR-5 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Slice gateway messages by token budget (PR-6)

**Depends on.** None.

**Files.**

- [ ] Edit `deploy/lobehub/patches/runtime/lcaGateway/executeGatewayRun.ts`.
- [ ] Create `deploy/lobehub/patches/runtime/lcaGateway/executeGatewayRun.test.ts`.
- [ ] Edit `deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py`.

**Build.**

- [ ] Filter assistant placeholder rows with empty content, `...`, or `LOADING_FLAT` before building `wireMessages`.
- [ ] Compute the model context window from `agentRow.model` and `agentRow.provider` through `modelContextWindowTokens`.
- [ ] Slice history with `getSlicedMessages` and `countContextTokens` from `@lobechat/context-engine`, reserving budget for the current turn and tools.
- [ ] Keep the original `params.messages` array for `resolveAssistantMessageId` and use the sliced array only for `wireMessages`.
- [ ] Add `executeGatewayRun.test.ts` to `_NEW_FILES` in `lca_runtime_agent_gateway.py`.

**You see.**

- [ ] `bunx vitest run src/store/chat/agents/transports/lcaGateway/executeGatewayRun.test.ts` passes and `uv run python -m deploy.lobehub.patch_lobehub verify` reports all markers intact.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `executeGatewayRun.test.ts` covers placeholder filtering, budget truncation, attachment retention on the current turn, and empty-message fallback. Run `cd lobehub-ui && bunx vitest run src/store/chat/agents/transports/lcaGateway/executeGatewayRun.test.ts`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the existing `lcaGateway` vitest files at trunk and head. Save `pr6-lane1.png`. Pass when both runs pass.
- [ ] Lane 2. Open the LobeHub UI and send a short message. Save `pr6-lane2.png`. Pass when the assistant replies and the wire messages match the input.
- [ ] Lane 3. Send a long multi-turn conversation. Save `pr6-lane3.png`. Pass when the backend receives a budget-truncated message list and the assistant answers.
- [ ] Lane 4. Send a message with an uploaded file. Save `pr6-lane4.png`. Pass when the file stays attached to its originating user turn in `wireMessages`.
- [ ] Lane 5. Send a message while the assistant placeholder is still visible. Save `pr6-lane5.png`. Pass when no `...` placeholder row reaches the backend.
- [ ] Lane 6. Run `uv run python -m deploy.lobehub.patch_lobehub doctor`. Save `pr6-lane6.png`. Pass when the doctor reports no drift.
- [ ] Lane 7. Run `uv run python -m deploy.lobehub.patch_lobehub drift`. Save `pr6-lane7.png`. Pass when drift reports no unregistered edits.
- [ ] Lane 8. Run the full `lcaGateway` vitest suite. Save `pr6-lane8.png`. Pass when all gateway tests pass.
- [ ] Lane 9. Boot the kernel and start a run through the UI with `assistant_id` set. Save `pr6-lane9.png`. Pass when the run completes and the journal contains the current turn.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr6-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `lcaExecuteGatewayRun` message-build wall time on a 200-message conversation.
- [ ] Probe. Run the vitest benchmark at trunk and head, interleaved.
- [ ] Baseline. Record the trunk build time first.
- [ ] Rule. Head build must complete under 20 ms for a 200-message conversation.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 and lane 4 screenshots into `docs/plans/media/pr6-review-*.png`.
- [ ] Record a 30 to 60 second video of the change on a lane VM. Save it as `docs/plans/media/pr6-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Mark ADR-0244 implemented (PR-7)

**Depends on.** PR-1, PR-2, PR-3, PR-4, PR-5, PR-6.

**Files.**

- [ ] Edit `docs/adr/0244-cognitive-memory-closed-loop-and-sandbox-convergence.md`.
- [ ] Edit `docs/adr/README.md`.
- [ ] Create `docs/notes/implemented/<class>/2026-09-19-adr-0244-implemented.md`.

**Build.**

- [ ] Flip the ADR status from Proposed to Accepted.
- [ ] Update the status cell for ADR-0244 in `docs/adr/README.md`.
- [ ] Write an implemented note per the `lca-write-note` skill conventions.

**You see.**

- [ ] `grep -l 'ADR-0244' docs/notes/implemented/**/*.md` returns the new note and `docs/adr/README.md` lists ADR-0244 as Accepted.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `uv run pytest tests/test_refactor_guards.py::test_adr_index_matches_filesystem -v`.
- [ ] Run `./scripts/lca-ops notes-check`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the ADR index guard at trunk and head. Save `pr7-lane1.png`. Pass when both pass.
- [ ] Lane 2. Run `./scripts/lca-ops notes-check`. Save `pr7-lane2.png`. Pass when no note defect is reported.
- [ ] Lane 3. Run `./scripts/check_notes_tree.py`. Save `pr7-lane3.png`. Pass when the notes tree is valid.
- [ ] Lane 4. Run `uv run pytest tests/test_refactor_guards.py -v`. Save `pr7-lane4.png`. Pass when the guard suite passes.
- [ ] Lane 5. Run `./scripts/verify_doc_slop.py docs/adr/0244-cognitive-memory-closed-loop-and-sandbox-convergence.md docs/notes/implemented`. Save `pr7-lane5.png`. Pass when no slop is reported.
- [ ] Lane 6. Run `git diff --check`. Save `pr7-lane6.png`. Pass when no whitespace errors are reported.
- [ ] Lane 7. Run `uv run pytest tests/architecture/ -v`. Save `pr7-lane7.png`. Pass when the architecture suite passes.
- [ ] Lane 8. Run `uv run ruff check docs`. Save `pr7-lane8.png`. Pass when ruff reports no errors.
- [ ] Lane 9. Run `grep -c 'Proposed' docs/adr/README.md`. Save `pr7-lane9.png`. Pass when the ADR-0244 row is not in the Proposed set.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr7-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Docs check wall time.
- [ ] Probe. Run `time ./scripts/lca-ops notes-check` at trunk and head, interleaved.
- [ ] Baseline. Record the trunk notes-check time first.
- [ ] Rule. Head notes-check must complete under 10 seconds.

**Review gate.** None. PR-7 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the report the execution playbook names.

## Appendix A. Prototype evidence

No prototypes were run. The open questions were settled by read-only exploration of the real code. The memory provider key is `memory`, not `memory_provider`, and `kind="memory"` already flows through prompt assembly. The workspace directory is already scaffolded at assistant creation. The sanctioned post-run hook is `RuntimeLifecycleSubscriber`. The context engine exports `getSlicedMessages` and `countContextTokens`. These findings are cited in the PR sections.

The sandbox two-tier sync, mapping `{home}/workspace/` into the Onlyboxes guest, stays unproven. PR-4 delivers the service and the local mapping seam. The Onlyboxes staging and harvest path is a follow-up risk.

## Appendix B. Alternatives rejected

Add a new `memory.retrieved` kind to the `ItemKind` allowlist. Rejected because the closed set already has `memory`, and the prompt renderer already consumes it. A new kind would touch every kind-based consumer for no prompt benefit.

Register a separate `memory_provider` canonical capability in `project_runtime_phase_capabilities`. Rejected because it would alias the composed `MemorySystem` and violate the no-parallel-mechanism rule.

Build a custom scheduler loop for the curator. Rejected because assistant plugins are statically barred from `asyncio.create_task` and timers. The passive `RuntimeLifecycleSubscriber` is the sanctioned pattern.

## Appendix C. Risks

Onlyboxes workspace sync lands in PR-4 only partially. The host-side service and local adapter mapping are real, but the guest staging and harvest loop for Docker sandboxes is deferred. The owner watches `tests/scenario/sandbox_*` for regressions.

The frontend budget logic depends on `@lobechat/context-engine` internals. PR-6 pins the import to the two exported functions and keeps a fallback that forwards all messages when the context window is unknown.

The curator reads run evidence after terminalization. PR-5 uses the journal reader and must tolerate the lifecycle event being payload-free.

## Appendix D. Links and reading list

Read `docs/plans/2026-09-19-adr-0244-implementation-plan.md` before editing. Read `docs/adr/0244-cognitive-memory-closed-loop-and-sandbox-convergence.md` before PR-7. Read `pstack/skills/how/SKILL.md` and `pstack/skills/interrogate/SKILL.md` for PR-3 and PR-5. The trail per `pstack/skills/show-me-your-work/SKILL.md` lives in each owner's `decisions.tsv`.