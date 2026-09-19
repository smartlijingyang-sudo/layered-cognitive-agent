# Assistant Self-Management Closure plan

Close the assistant self-management loop. The agent knows its Home, can install skills and edit its own persona through governed tools, persists and retrieves real memory, stops looping on repeated successful searches, and the dead and half-implemented paths from prior ADRs are removed. For the user, the assistant finally remembers "叫我老板" across sessions and carries it into its prompt. For the next engineer, every planned ADR item is either live with a test or deleted. The program enforces one rule. A PR is verified only when its unit, live, and perf boxes are all checked. PR order is PR-1, PR-2, PR-3, PR-4, PR-5, PR-6, with the existing `adr-0244/pr-*` stack as the memory foundation.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. The root builds the stack and swarm-verifies each head; the operator reviews the review-gated PRs and lands the stack bottom-up.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on her explicit go.
- [ ] On her go, arm a `/goal` with this exact text. "Run docs/plans/2026-09-19-assistant-self-management-closure.md. Implement PR-1 through PR-6 in order, after verifying and landing the existing adr-0244/pr-1 through adr-0244/pr-7 stack. Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The operator reviews and lands the stack. Done when PR-6 is merge-ready and the end-to-end assistant memory loop is verified live."
- [ ] Read these from trunk at program start. Re-read them at every tick.
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `git show origin/main:pstack/skills/swarm/SKILL.md`
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `git show origin/main:pstack/skills/lca-pre-push-checks/SKILL.md`
  - [ ] `git show origin/main:docs/AGENTS.md`
- [ ] Arm the 30-minute audit tick. In a local session, a real terminal `/loop`. In a cloud root, a cloud-sleeper wake chain. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from trunk and the armed /goal. Audit the operation against both and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then send the operator a status message, whether or not anything changed, with the queue table of PR, owner, state, and head SHA, the verdicts since the last tick, what merged, open operator gates, and blockers."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the execution playbook names.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges, or base it on the parent branch when the execution playbook stacks.
  - [ ] PR-1, PR-5, and PR-6 are independent and first. All branch from `main`.
  - [ ] PR-2 after PR-1.
  - [ ] PR-3 after PR-1 and after `adr-0244/pr-3-memory-retrieve-live` lands.
  - [ ] PR-4 after PR-3.
- [ ] Hold the file boundaries. PR-1 touches only `lca/infrastructure/cli/` and `tests/infrastructure/cli/`. PR-2 touches only `lca/plugins/domain/tools/` and `lca/infrastructure/tools/assistant/`. PR-3 touches only `lca/plugins/prompts/`, `lca/plugins/assistant/persona/`, `bundles/`, and `docs/notes/`. PR-4 touches only `lca/nodes/remember/`, `lca/nodes/reflect/`, `lca/nodes/concept/effect/`, `lca/harness/declarative/`, `lca/infrastructure/memory/`, `lca/contracts/models/`, and `tests/`. PR-5 touches only `lca/cognition/brain/`, `lca/plugins/gate/`, and `bundles/`. PR-6 touches only `lca/plugins/transport/webserver/routes_1/`, `lca/infrastructure/tools/skills/`, `docs/adr/`, and `docs/plans/`.
- [ ] Hold the review gate. PR-2 and PR-3 change agent-facing interaction. They wait for the operator's review in chat with screenshots and a video before merge.

### PR mechanics, for every PR

- [ ] Resolve the forge once. Default to `gh`; if `command -v origin` succeeds and Origin can resolve the repository, use `origin pr` for every PR operation. Record any fallback to `gh`. Never require `gt`.
- [ ] Open the PR ready, never draft, with `origin pr create --status open --base <base-branch>` or `gh pr create --base <base-branch>` according to the resolved forge. A stack child targets its parent branch.
- [ ] Run the repo's lint and typecheck once before the PR-facing push. Push with hooks on.
- [ ] Run `/deslop` before each commit and `/no-comments` before review.
- [ ] Triage every Bugbot and security-reviewer comment per `../references/bugbot-triage.md`.
- [ ] Rebase onto current trunk before babysit and again before the merge-ready report.

### Verdict and merge, for every PR

- [ ] At the merge-ready head SHA, run the swarm per `pstack/skills/swarm/SKILL.md`. One gates lane. The ten live lanes from the PR's **Verify, live** block. The perf lane from its **Verify, perf** block. One audit lane that reads the diff and the receipts and distrusts the PR body.
- [ ] Clean only when every lane is `PASS`. Findings go back to the owner. A new head gets a fresh swarm and a fresh verdict.
- [ ] Append the PR to the one linear base-branch stack per `playbooks/autopilot-stack.md`, with the patch-id rule from `playbooks/shipping.md`.

### Boot recipe, for every live lane

Each live lane runs on its own local worktree at the PR head. Drive through `control-cli` from `cursor-team-kit` for CLI lanes and `control-ui` for browser lanes.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] Start the backend with `./scripts/lca-ops kernel-restart`. Wait until `./scripts/lca-ops status --json` reports the kernel healthy.
- [ ] Create a fresh test assistant once per lane VM with `curl -X POST http://127.0.0.1:8765/v1/assistants -H 'Content-Type: application/json' -d '{"name":"验证助理","from_role":"marketing/marketing-kuaishou-strategist"}'` and record the returned `assistant_id`.
- [ ] Deliver input through `./scripts/lca-ops runs create --user-text "<input>" --assistant-id <assistant_id>` (PR-1 and later) or through the LobeHub UI at `http://localhost:3010` for browser lanes. Name the read-only diagnostics. They are `lca-ops journal replay`, `lca-ops debug-run`, `lca-ops timeline`, `cat ~/.lca/assistants/<id>/memory/*.json`, `cat ~/.lca/assistants/<id>/SOUL.md`, `cat ~/.lca/assistants/<id>/USER.md`, `ls ~/.lca/assistants/<id>/skills/`.
- [ ] Save every screenshot to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.png` with `import -window root` and return the paths with the report.

## Bind assistant runs in the CLI (PR-1)

**Depends on.** None.

**Files.**

- [ ] Edit `lca/infrastructure/cli/commands/runs/runs.py`.
- [ ] Create `tests/infrastructure/cli/commands/runs/test_assistant_binding.py`.

**Build.**

- [ ] Add a `--assistant-id` option to `runs create` and forward it in the `POST /runs` body as `assistant_id`.
- [ ] Pass `assistant_id` through the facade path too, replacing the hardcoded `None` at `runs.py`.
- [ ] When `--agent` is given without `--assistant-id`, resolve the agent row to its `assistant_id` through the assistant catalog when a mapping exists.

**You see.**

- [ ] `./scripts/lca-ops runs create --help` lists `--assistant-id`.
- [ ] A run created with `--assistant-id asst_...` carries that id in its session and loads the assistant Home.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_assistant_binding.py` gains `test_assistant_id_in_body`, `test_facade_forwards_assistant_id`, and `test_agent_resolves_to_assistant`. Run `uv run pytest tests/infrastructure/cli/commands/runs/test_assistant_binding.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `uv run pytest tests/infrastructure/cli/ -v` at trunk and head. Save `pr1-lane1.png`. Pass when both suites pass.
- [ ] Lane 2. Create a run with `--assistant-id <id>` and read the manifest. Save `pr1-lane2.png`. Pass when the manifest's session carries the assistant id.
- [ ] Lane 3. Create a run with `--agent agt_...` that maps to an assistant. Save `pr1-lane3.png`. Pass when the run resolves to the assistant Home.
- [ ] Lane 4. Create a run without any binding option. Save `pr1-lane4.png`. Pass when the run completes and stays unbound.
- [ ] Lane 5. Run `uv run pytest tests/infrastructure/ -v`. Save `pr1-lane5.png`. Pass when the suite passes.
- [ ] Lane 6. Run `uv run ruff check lca/infrastructure/cli`. Save `pr1-lane6.png`. Pass when ruff reports no errors.
- [ ] Lane 7. Run `uv run mypy lca/infrastructure/cli/commands/runs/runs.py`. Save `pr1-lane7.png`. Pass when mypy exits 0.
- [ ] Lane 8. Run `./scripts/lca-ops runs create --help`. Save `pr1-lane8.png`. Pass when the help text lists `--assistant-id`.
- [ ] Lane 9. Run `./scripts/lca-ops status --json`. Save `pr1-lane9.png`. Pass when the kernel reports healthy.
- [ ] Lane 10. Run `git diff --check`. Save `pr1-lane10.png`. Pass when the diff has no whitespace errors.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. CLI startup to receipt for `runs create --assistant-id`.
- [ ] Probe. Run `time ./scripts/lca-ops runs create --user-text "hi" --assistant-id <id>` at trunk and head, interleaved.
- [ ] Baseline. Record the trunk value first.
- [ ] Rule. Head must not exceed trunk by more than 200 ms.

**Review gate.** None. PR-1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Expose self-management tools to bound runs (PR-2)

**Depends on.** PR-1.

**Files.**

- [ ] Edit `lca/plugins/domain/tools/assistant_tools/plugin.py`.
- [ ] Edit `lca/infrastructure/tools/assistant/self_manage_tools.py`.
- [ ] Edit `lca/infrastructure/tools/assistant/create_skill_tool.py`.
- [ ] Create `tests/plugins/domain/tools/assistant_tools/test_self_manage_exposure.py`.

**Build.**

- [ ] Verify the gating in `assistant_self_manage_tools_from_run` and `assistant_create_skill_tool_from_run` materializes the full self-management tool family whenever `current_assistant_id()` is non-empty.
- [ ] Fix any gating path that returns an empty catalog for a bound run.
- [ ] Assert the exposed tool names. They are `create_assistant_skill`, `list_assistant_skills`, `delete_assistant_skill`, `edit_assistant_skill`, `update_assistant_soul`, `update_assistant_profile`, `update_assistant_grants`, `list_assistant_tools`, `create_assistant_tool`, `update_assistant_tool`, `delete_assistant_tool`.

**You see.**

- [ ] A bound run's tool catalog contains the self-management family.
- [ ] `import_skill` and `search_skill` stay present alongside them.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_self_manage_exposure.py` gains `test_bound_run_has_full_family` and `test_unbound_run_has_no_self_manage_tools`. Run `uv run pytest tests/plugins/domain/tools/assistant_tools/test_self_manage_exposure.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the same bound-run tool catalog check at trunk and head. Save `pr2-lane1.png`. Pass when head lists the family and trunk does not.
- [ ] Lane 2. Create a bound run and read the tool schemas from the replay. Save `pr2-lane2.png`. Pass when `create_assistant_skill` and `update_assistant_soul` appear.
- [ ] Lane 3. Have the assistant call `create_assistant_skill` with a name, title, description, and body. Save `pr2-lane3.png`. Pass when `{home}/skills/<name>/SKILL.md` exists and the manifest index lists it.
- [ ] Lane 4. Have the assistant call `update_assistant_soul` to set a tone. Save `pr2-lane4.png`. Pass when `{home}/SOUL.md` changes and `revision_seq` increments.
- [ ] Lane 5. Have the assistant call `list_assistant_skills`. Save `pr2-lane5.png`. Pass when the result lists the Home skills.
- [ ] Lane 6. Have the assistant call `update_assistant_profile` to change its emoji. Save `pr2-lane6.png`. Pass when `{home}/profile.json` reflects the change.
- [ ] Lane 7. Run `uv run pytest tests/plugins/domain/tools/ -v`. Save `pr2-lane7.png`. Pass when the suite passes.
- [ ] Lane 8. Run `uv run ruff check lca/plugins/domain/tools lca/infrastructure/tools/assistant`. Save `pr2-lane8.png`. Pass when ruff reports no errors.
- [ ] Lane 9. Run `uv run mypy lca/infrastructure/tools/assistant`. Save `pr2-lane9.png`. Pass when mypy exits 0.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr2-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Tool catalog assembly time for a bound run.
- [ ] Probe. Run `time ./scripts/lca-ops runs create --user-text "list tools" --assistant-id <id>` at trunk and head, interleaved.
- [ ] Baseline. Record the trunk value first.
- [ ] Rule. Head must not exceed trunk by more than 300 ms.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 3 and lane 4 screenshots into `docs/plans/media/pr2-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of the assistant creating a skill and updating its soul on a lane VM. Save it as `docs/plans/media/pr2-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Inject Home path and memory snapshot into the prompt (PR-3)

**Depends on.** PR-1 and the existing open branch `adr-0244/pr-3-memory-retrieve-live`.

**Files.**

- [ ] Edit `lca/plugins/prompts/sections.py`.
- [ ] Edit `lca/plugins/assistant/persona/persona.py`.
- [ ] Create `docs/notes/implemented/seam/2026-09-19-home-memory-prompt-section.md`.
- [ ] Create `tests/plugins/prompts/test_home_memory_sections.py`.

**Build.**

- [ ] Add a `home` prompt section that renders `~/.lca/assistants/<assistant_id>/`, the `memory/` path, the `skills/` path, and the `workspace/` path when `assistant_id` is bound.
- [ ] Register the `home` section in the section closure list and record the closure change in the Agent Note.
- [ ] Verify retrieved memory items from `phase.perceive.fold` render through `render_context_lines` into the `CONTEXT` block, and add the `memory` kind to the rendered set if it is excluded.
- [ ] Render a frozen memory snapshot block when the manifest carries memory items.

**You see.**

- [ ] A bound run's system prompt contains the Home path and the memory snapshot.
- [ ] An unbound run's prompt stays unchanged.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_home_memory_sections.py` gains `test_home_section_renders_paths`, `test_memory_items_render_in_context`, and `test_unbound_prompt_unchanged`. Run `uv run pytest tests/plugins/prompts/test_home_memory_sections.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the same bound-run prompt dump at trunk and head. Save `pr3-lane1.png`. Pass when head shows the Home path and trunk does not.
- [ ] Lane 2. Write a memory file into `{home}/memory/semantic.json`, then start a bound run. Save `pr3-lane2.png`. Pass when the first `llm.request.header` system prompt contains the memory content.
- [ ] Lane 3. Start a bound run with an empty memory dir. Save `pr3-lane3.png`. Pass when the prompt has no memory block and the run completes.
- [ ] Lane 4. Ask the assistant "你的目录在哪". Save `pr3-lane4.png`. Pass when the assistant answers with its Home path without searching.
- [ ] Lane 5. Replay the run journal. Save `pr3-lane5.png`. Pass when `lca-ops journal replay` shows the Home section in the system prompt.
- [ ] Lane 6. Run `uv run pytest tests/plugins/prompts/ -v`. Save `pr3-lane6.png`. Pass when the suite passes.
- [ ] Lane 7. Run `uv run pytest tests/integration/ -v`. Save `pr3-lane7.png`. Pass when the integration suite passes.
- [ ] Lane 8. Run `uv run ruff check lca/plugins/prompts lca/plugins/assistant/persona`. Save `pr3-lane8.png`. Pass when ruff reports no errors.
- [ ] Lane 9. Run `uv run mypy lca/plugins/prompts`. Save `pr3-lane9.png`. Pass when mypy exits 0.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr3-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Prompt assembly time with the Home section and a 200-record memory file.
- [ ] Probe. Run `time ./scripts/lca-ops runs create --user-text "hi" --assistant-id <id>` at trunk and head, interleaved.
- [ ] Baseline. Record the trunk value first.
- [ ] Rule. Head must not exceed trunk by more than 250 ms.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 and lane 4 screenshots into `docs/plans/media/pr3-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of the assistant answering "你的目录在哪" on a lane VM. Save it as `docs/plans/media/pr3-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Close the memory write loop with semantic candidates (PR-4)

**Depends on.** PR-3 and the existing open branch `adr-0244/pr-3-memory-retrieve-live`.

**Files.**

- [ ] Edit `lca/nodes/remember/write/write.py`.
- [ ] Edit `lca/harness/declarative/execute/dispatch.py`.
- [ ] Edit `lca/nodes/reflect/score/score.py`.
- [ ] Edit `lca/nodes/remember/admit/admit.py`.
- [ ] Edit `lca/infrastructure/memory/assistant_memory.py`.
- [ ] Edit `lca/contracts/models/cognition/boundary.py`.
- [ ] Create `tests/integration/test_semantic_memory_candidate.py`.

**Build.**

- [ ] Change `phase.remember.write` to dispatch through the production effect gateway's `execute` method, and add a `dispatch` alias on `RegistryEffectDispatcher` that delegates to `execute` so both call sites stay valid.
- [ ] Pass `state` into `phase.reflect.score` from the runtime so `_extract_procedural_candidate` sees the real tool sequence.
- [ ] Add a semantic candidate extractor that recognizes explicit user preference and persona directives from the current user turn, with source `user` and high confidence, without hardcoding business keywords.
- [ ] Make `AssistantMemory.update` persist the user directive content, the source turn, and the timestamp, not the step summary.
- [ ] Extend `MemoryRecord` and the memory JSON schema with a `source_turn` field when needed.

**You see.**

- [ ] A run where the user says "以后叫我老板" writes a semantic memory record into `{home}/memory/semantic.json`.
- [ ] The next run's prompt contains that record.
- [ ] No `AttributeError` on `dispatch` when a candidate is admitted.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_semantic_memory_candidate.py` gains `test_user_preference_persists`, `test_remember_write_dispatches_via_execute`, and `test_assistant_memory_stores_content`. Run `uv run pytest tests/integration/test_semantic_memory_candidate.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the same "以后叫我老板" persistence scenario at trunk and head. Save `pr4-lane1.png`. Pass when head writes `semantic.json` and trunk does not.
- [ ] Lane 2. Run 1 says "以后叫我老板". Save `pr4-lane2.png`. Pass when `{home}/memory/semantic.json` contains the directive.
- [ ] Lane 3. Run 2 asks "你该叫我什么". Save `pr4-lane3.png`. Pass when the assistant answers "老板" and the prompt contains the memory record.
- [ ] Lane 4. Run a multi-step tool task and check the procedural candidate path. Save `pr4-lane4.png`. Pass when `{home}/memory/working.json` gains a record with the tool sequence.
- [ ] Lane 5. Replay the journal of run 1. Save `pr4-lane5.png`. Pass when `phase.remember.write` emits a non-null `memory_receipt`.
- [ ] Lane 6. Run `uv run pytest tests/integration/ -v`. Save `pr4-lane6.png`. Pass when the integration suite passes.
- [ ] Lane 7. Run `uv run pytest tests/nodes/ -v`. Save `pr4-lane7.png`. Pass when the nodes suite passes.
- [ ] Lane 8. Run `uv run ruff check lca/nodes/remember lca/nodes/reflect lca/infrastructure/memory lca/harness/declarative`. Save `pr4-lane8.png`. Pass when ruff reports no errors.
- [ ] Lane 9. Run `uv run mypy lca/nodes/remember lca/nodes/reflect lca/infrastructure/memory`. Save `pr4-lane9.png`. Pass when mypy exits 0.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr4-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. End-to-end time for a two-run preference persistence cycle.
- [ ] Probe. Run the two-run scenario from lanes 2 and 3 at trunk and head, interleaved.
- [ ] Baseline. Record the trunk value first.
- [ ] Rule. Head must not exceed trunk by more than 1 second.

**Review gate.** None. PR-4 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Wire the tool loop breaker into the runtime brain (PR-5)

**Depends on.** None.

**Files.**

- [ ] Edit `lca/cognition/brain/pipeline/default_factory.py`.
- [ ] Edit `lca/cognition/brain/pipeline/_standard_factory.py`.
- [ ] Edit `lca/plugins/gate/tool_loop_breaker/plugin.py`.
- [ ] Create `tests/cognition/brain/test_agent_gates_wired.py`.

**Build.**

- [ ] Pass an `agent_gate_factory` into `SimpleBrainFactory` so the assembled `ModularBrain` exposes a non-null `agent_gates`.
- [ ] Compose the gate chain that includes `ToolLoopBreakerGate` with its stalled-success branch (`break_stalled=3`).
- [ ] Keep the factory fail-soft so profiles without gates keep the current behavior.

**You see.**

- [ ] `runtime.brain.agent_gates` is non-null in a web-assistant run.
- [ ] A run that repeats the same successful tool call stalls after three repeats and the gate rewrites `USE_TOOL` to `RESPOND`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_agent_gates_wired.py` gains `test_brain_exposes_agent_gates` and `test_stalled_success_breaks_loop`. Run `uv run pytest tests/cognition/brain/test_agent_gates_wired.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the same stalled-tool scenario at trunk and head. Save `pr5-lane1.png`. Pass when head stops after three repeats and trunk loops.
- [ ] Lane 2. Start a run whose prompt forces repeated `listFiles` on the same path. Save `pr5-lane2.png`. Pass when the run records at most three identical calls before the gate fires.
- [ ] Lane 3. Start a normal text run. Save `pr5-lane3.png`. Pass when the run completes with one LLM call and no gate interference.
- [ ] Lane 4. Run `uv run pytest tests/cognition/ -v`. Save `pr5-lane4.png`. Pass when the cognition suite passes.
- [ ] Lane 5. Run `uv run pytest tests/plugins/gate/ -v`. Save `pr5-lane5.png`. Pass when the gate suite passes.
- [ ] Lane 6. Run `uv run ruff check lca/cognition/brain lca/plugins/gate`. Save `pr5-lane6.png`. Pass when ruff reports no errors.
- [ ] Lane 7. Run `uv run mypy lca/cognition/brain`. Save `pr5-lane7.png`. Pass when mypy exits 0.
- [ ] Lane 8. Run `./scripts/lca-ops debug-run $(ls -1t traces/runs | head -1)`. Save `pr5-lane8.png`. Pass when the debug output shows no loop.
- [ ] Lane 9. Run `uv run pytest tests/integration/ -v`. Save `pr5-lane9.png`. Pass when the integration suite passes.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr5-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Per-turn gate overhead on a normal text run.
- [ ] Probe. Run `time ./scripts/lca-ops runs create --user-text "hi"` at trunk and head, interleaved.
- [ ] Baseline. Record the trunk value first.
- [ ] Rule. Head must not exceed trunk by more than 100 ms.

**Review gate.** None. PR-5 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Clean up dead and half-implemented paths (PR-6)

**Depends on.** None.

**Files.**

- [ ] Edit `lca/plugins/transport/webserver/routes_1/routes_assistants.py`.
- [ ] Edit `lca/infrastructure/tools/skills/importer/import_tool.py`.
- [ ] Edit `docs/adr/0245-hermes-self-evolution-and-skill-auto-generation.md`.
- [ ] Delete `docs/plans/2026-09-19-adr-0244-gap-closure-plan.md` if PR-3 in the existing stack has not already removed it.
- [ ] Create `tests/plugins/transport/webserver/routes_1/test_profile_route.py`.

**Build.**

- [ ] Implement `PATCH /v1/assistants/{assistant_id}/profile` by calling `catalog.revise_profile`, replacing the 501 stub.
- [ ] Fix the `import_skill` description so it no longer references `create_assistant_skill` when that tool is absent from the catalog.
- [ ] Correct ADR-0245. Mark `memory` and `skill_manage` as the production Hermes mechanisms and `self_evolution` as an unwired experiment.
- [ ] Remove the superseded gap-closure plan file when no PR still references it.

**You see.**

- [ ] `PATCH /v1/assistants/{id}/profile` returns 200 and updates the profile.
- [ ] `import_skill` no longer advertises a missing tool.
- [ ] `rg self_evolution docs/adr/0245` shows the corrected classification.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_profile_route.py` gains `test_patch_profile_revises` and `test_patch_profile_missing_assistant_404`. Run `uv run pytest tests/plugins/transport/webserver/routes_1/test_profile_route.py -v`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the same profile patch request at trunk and head. Save `pr6-lane1.png`. Pass when head returns 200 and trunk returns 501.
- [ ] Lane 2. Send `PATCH /v1/assistants/<id>/profile` with a `description` change. Save `pr6-lane2.png`. Pass when the response is 200 and `profile.json` changes.
- [ ] Lane 3. Send `PATCH` for a missing assistant. Save `pr6-lane3.png`. Pass when the response is 404.
- [ ] Lane 4. Read the `import_skill` tool schema from a bound run. Save `pr6-lane4.png`. Pass when the description no longer references `create_assistant_skill`.
- [ ] Lane 5. Run `rg self_evolution docs/adr/0245-hermes-self-evolution-and-skill-auto-generation.md`. Save `pr6-lane5.png`. Pass when the file classifies it as an unwired experiment.
- [ ] Lane 6. Run `uv run pytest tests/plugins/transport/webserver/ -v`. Save `pr6-lane6.png`. Pass when the suite passes.
- [ ] Lane 7. Run `uv run ruff check lca/plugins/transport/webserver/routes_1 lca/infrastructure/tools/skills`. Save `pr6-lane7.png`. Pass when ruff reports no errors.
- [ ] Lane 8. Run `uv run mypy lca/plugins/transport/webserver/routes_1/routes_assistants.py`. Save `pr6-lane8.png`. Pass when mypy exits 0.
- [ ] Lane 9. Run `git diff --check`. Save `pr6-lane9.png`. Pass when the diff has no whitespace errors.
- [ ] Lane 10. Run `./scripts/lca-ops status --json`. Save `pr6-lane10.png`. Pass when the kernel reports healthy.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Profile patch latency on a warm catalog.
- [ ] Probe. Run the lane 2 patch request at trunk and head, interleaved.
- [ ] Baseline. Record the trunk value first.
- [ ] Rule. Head must not exceed trunk by more than 200 ms.

**Review gate.** None. PR-6 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The owner squash-merges its own PR, or the root appends it to the base-branch stack and the operator lands it bottom-up.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the report the execution playbook names.

## Appendix A. Prototype evidence

- [ ] The existing open branches `adr-0244/pr-1` through `adr-0244/pr-7` are prototypes for the memory foundation. Record their head SHAs and PR numbers here when verified.
- [ ] The two observed runs `run_8d1073a20ff7` and `run_968fd5b560d6` are the reproduction evidence for the whole program. Their journal replays stay in `traces/runs/`.
- [ ] The question of whether the frontend gateway sends `assistant_id` was answered by reading `executeGatewayRun.ts`, which forwards `agencyConfig.lcaAssistantId`. No prototype was needed.

## Appendix B. Alternatives rejected

- [ ] Copying the Hermes file-lock memory store directly. Rejected because it bypasses the Effect/C10 narrow gate and the existing `MemorySystem` protocol.
- [ ] Making the agent write files into its Home through the raw sandbox. Rejected because it bypasses `revise_profile` and the manifest digest.
- [ ] Adding a regex detector for "叫我老板" style phrases in the graph. Rejected because it violates the no-hardcoded-business-keywords rule in ADR-0244.

## Appendix C. Risks

- [ ] PR-4 changes the effect dispatcher surface. The owner watches for callers of `dispatch` versus `execute` and runs the full effect test suite.
- [ ] PR-3 changes the 16-section prompt closure. The owner records the closure change in the Agent Note and re-runs prompt snapshot tests.
- [ ] PR-5 changes brain assembly. The owner watches profiles without gates to confirm fail-soft behavior.
- [ ] Live lanes run on local worktrees instead of cloud VMs because no cloud fleet is available. The screenshots are terminal captures. The operator should treat browser-adjacent lanes as best-effort.

## Appendix D. Links and reading list

- [ ] Read `docs/adr/0242-assistant-creation-home-runtime.md` before PR-2 and PR-3.
- [ ] Read `docs/adr/0243-assistant-skill-tool-isolation-config.md` before PR-2.
- [ ] Read `docs/adr/0244-cognitive-memory-closed-loop-and-sandbox-convergence.md` before PR-3 and PR-4.
- [ ] Read `docs/adr/0245-hermes-self-evolution-and-skill-auto-generation.md` before PR-6.
- [ ] Read `lca/plugins/prompts/sections.py` before PR-3.
- [ ] Read `lca/harness/declarative/execute/dispatch.py` before PR-4.
- [ ] PR-2 and PR-3 get `pstack/skills/how/SKILL.md`. PR-4 gets `pstack/skills/interrogate/SKILL.md` before shipping.