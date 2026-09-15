# 2026-09-15 LCA agent loop redesign — DSH-aligned, graph-noded, first-principles

## Status

Draft, awaiting user approval. Classification: architectural.

## Problem (verified this session)

1. A tool-using run on `web-standard` profile (`run_cc39610072bf`) died with `budget_exceeded: node 'think.main' visited 3 times (max_visits=2)`. The LLM received `role=tool` content "hello" but no preceding `assistant{tool_calls=…}` message. OpenAI tool-use wire shape is broken; the model re-issues the same call.
2. The `assistant{tool_calls}` surface event is silently dropped at `_snapshot_attrs(self._cursor_provider())` in `lca/plugins/events/hooks/model_visible/adapter.py:185, 222` (cursor ContextVar unbound → entire pre/post hook block bypassed). The `tool_result` surface succeeds because it uses a different ContextVar (`current_publish_session`). Two ContextVars, two writers, two failure modes for one logical conversation-history write.
3. The conversation-history write path is held together by **two parallel mechanisms**:
   - `lca/infrastructure/session/emit/lifecycle_emit.py` (ContextVar-bound `_state()` + `current_publish_session` lookup)
   - `lca/loop/fact_gateway.py:_bound_publish_writer` (ContextVar fallback chain `session` → `current_publish_session()`, silent None return)
   - `lca/infrastructure/session/_overflow_0/bindings.py:assemble_model_history(step=)` (legacy helper wrapping the new `DefaultModelContextAssembler`)
4. `max_visits` is a graph-topology invariant (`lca/framework/graph/traversal.py:48-69`, `lca/framework/graph/interpreter.py:127-149`). 75 of 78 yaml declarations are `max_visits: 1` (decorative, no behavior); 5 actually fire (`think.reason=8`, `think.gate=8`, `think.main=2`, `act.main=2`, `think.reason.complete=3`). The mechanism kills legitimate 2+ tool-call sequences.
5. The system prompt is duplicated in `messages[0]` as `role=user` instead of going into the `system` field (`lca/infrastructure/llm_adapter/openai_compat/history/_history.py:11-13`, `chat/_chat_completions.py:199-203`, `anthropic/_anthropic_messages.py:126`). Some models treat this as a user-role instruction, which causes the `assistant` role to be silently ignored.

## User-stated scope (this turn)

> "缺失的部分 怎么对齐dsh来用插件化 图节点实现 补齐 还有业界好东西 插件化 图节点化 多一些subagent调研 自己的还有外部的"
> "目前我们走的图流程 节点过程中 那些是有问题的 有残留 多轨并行 脆弱的 可以对齐dsh 或者业界范式 来做到更加模块化 插件化 图节点化 全面一点 清理垃圾"
> "agent 一整套链路下 各种模块 流程 缺什么 怎么插件化 图节点化 一切图化"
> "我希望这一块也是对齐dsh 干掉垃圾机制"

The scope is **the entire v2 graph-flow + conversation-history write path + plugin surface**, not just the immediate bug. Single-bug patches are explicitly out of scope. First-principles cleanup, full DSH alignment, plugin / graph-node-ification throughout.

## Five-investigation census

Five parallel subagent investigations produced file:line evidence:

| Investigation | Output | Key findings |
|---|---|---|
| Fragility census (LCA) | fragility report (10 sections, 200+ file:line citations) | 5 ContextVar-driven seams, 8 dual-writer pairs, 4 silent no-op paths, 5 idempotency stateful guards, 80 yaml `max_visits:` lines, 3 boot-validation checks, system-prompt duplication, `_overflow_0/` shadow module, `PlanBlueprint.max_visits` |
| DSH full reference | DSH reference (10 sections, file:line citations) | `Session.append(<type>, data, ...surfaceOpts?)` with conditional surface opts; `SessionProjectionRegistry` replaces Reducer; no graph machine (DSH uses while-loop phase functions + verdict); surface fold = `surface.ts` with `tool_call_id` linking via `sourceEventSeqs` |
| OpenAI/Claude Agents SDK + LangGraph + Temporal + Inngest | OpenAI/Claude/LangGraph + Temporal/Inngest report | OpenAI has `drop_orphan_function_calls` (orphan + reasoning pre-flight); Claude delegates to closed-source subprocess (reject this); LangGraph has `add_messages` ID-keyed reducer + `recursion_limit` + `interrupt()/Command(resume=)`; Temporal Event History ≈ LCA Session |
| Hermes-agent (`~/.hermes/hermes-agent/`) | hermes-agent structural map | **Persist-before-execute** durability invariant (`agent/turn_tool_round.py:54-149`); `_DB_PERSISTED_MARKER` at read site; fail-closed turn break on persistence failure; classify_persistence_error; tool-call/result pairing via `coalesce_tool_call_id`; no graph machine (imperative phase functions + verdict); ContextVars for transport/scope only, explicit DI for primary deps |

The **two strongest adoptions** that resolve the LCA bug at root:
1. **Hermes-agent's persist-before-execute + fail-closed turn break** (lines 132-140 of `agent/turn_tool_round.py`): the assistant `tool_calls` row is appended to the durable journal BEFORE the tool executes; if it fails, the turn breaks with `turn_exit_reason="session_persistence_failed"` and the tool never runs from in-memory state.
2. **OpenAI's `drop_orphan_function_calls`**: orphan `tool/result` messages and dangling reasoning are dropped at every LLM-call preparation step. Pre-flight structural guarantee.

## Goal

Replace LCA's fragile dual-stream write path + max_visits ceremony + multi-ContextVar dependency seam with:

- **One Session append-only log per run** (already the SSOT per ADR-0186; expand to be the *only* write seam)
- **One writer per event type, dependency-injected, fail-loud** (no ContextVar lookup, no silent None return)
- **Persist-before-execute durability invariant** (the assistant `tool_calls` row lands in the journal before Body executes the tool)
- **OpenAI-style orphan-drop at every LLM-call preparation step** (no orphan `role=tool` ever reaches the wire)
- **DSH-aligned surface event taxonomy**: `surface/user_message`, `surface/assistant_message`, `surface/tool_result` (with `tool_call_id` linking), `surface/tool_call` (log-only pairing record)
- **Graph-node-ification of the think subgraph**: split `think.reason.complete` into three single-responsibility graph nodes: `think.history.assemble`, `think.llm.dispatch`, `think.decision.parse` (per user's "图节点化")
- **All fragile mechanisms identified in census deleted in the same wave** (no COMPAT shim)
- **Loop protection by wire-shape correctness**, not by visit-counter

## Non-goals

- Replacing the DSH reference. This is alignment, not from-scratch.
- Touching `lobehub-ui/` or `vendor/`.
- Changing the v2 subgraph driver interpretation semantics beyond removing `max_visits` + adding the persist-before-execute check.
- Changing transport (HTTP/SSE/WS) wire formats.
- Adding `MultiToolLoopBreaker` to the default `think.gate` chain (cross-checked against OpenAI/Anthropic/LangGraph/DSH — none have analogous built-in gate; cross-check confirmed `consecutive_repeat_max` fingerprint detection is LCA-internal and not a first-principles primitive; with correct wire shape the orphan cycle never starts).
- Adding multi-profile tool scoping (hermes-agent has it; LCA has only one profile concept; defer).

## Architecture: the target shape

### A. Session event taxonomy (DSH-aligned)

Replace the LCA-internal `SURFACE_USER_TYPE`, `SURFACE_ASSISTANT_TYPE`, `SURFACE_TOOL_RESULT_TYPE` constants with DSH-aligned event names:

```text
surface/user_message         # role=user, content
surface/assistant_message   # role=assistant, content|None, tool_calls[], usage?
surface/tool_result         # role=tool, tool_call_id, content, error?
log/tool_call               # NOT a surface event; pairs surface/tool_result via sourceEventSeqs
```

The closed set (`SurfaceEventType`) is enforced at type-level via DSH's pattern (`packages/core/session/src/types.ts:430-460`): `surfaceOp` and `sourceEventSeqs` are conditionally required only on `SurfaceEventType` variants. LCA's equivalent: a Pydantic discriminated union `SessionEventType` where surface variants require `surface_op` and `source_event_seqs`.

`log/tool_call` is **NOT** a surface event. It exists for replay fidelity and provenance. The Session fold derives messages by walking only surface events.

### B. One writer per event type, dependency-injected, fail-loud

Delete these (silently no-op when unbound):
- `lca/loop/fact_gateway.py:_bound_publish_writer` (`session=None, state=None` → `current_publish_session()` → None)
- `lca/loop/fact_gateway.py:append_surface_bound`, `append_catalog_bound`, `publish_ep_bound`, `fact_gateway_for_emit`
- `lca/infrastructure/session/emit/lifecycle_emit.py` entire module (dual-writer surface + catalog)
- `lca/infrastructure/session/emit/surface_emit.py` entire module (dual-writer for user + HIL)
- `lca/infrastructure/session/emit/tool_surface_emit.py` entire module
- `lca/infrastructure/session/_overflow_0/` entire module (legacy shim)

Replace with:

```python
# Injected into the LLM adapter / body executor / decision parser as a constructor dependency
# (per hermes-agent: explicit DI for primary deps; ContextVars only for transport/scope)
class RunSessionWriter:
    """Owner of the run-scoped Session. Single surface append path.

    Constructor receives the Session (from RunEventSessionBridge.inner).
    All methods fail loud if the Session is unbound.
    """

    def append_user_message(self, *, message_id: str, role: str, content: str) -> EventRef
    def append_assistant_message(self, *, turn: int, step: int, role: Literal["assistant"],
                                  content: str | None,
                                  tool_calls: list[ToolCall] | None,
                                  usage: TokenUsage | None) -> EventRef
    def append_tool_call(self, *, turn: int, step: int, call_id: CallId,
                         name: str, arguments: str) -> EventRef   # log-only pairing record
    def append_tool_result(self, *, turn: int, step: int, call_id: CallId,
                           content: str,
                           error: ToolError | None,
                           meta: JsonValue | None) -> EventRef
    def derive_messages(self) -> list[Message]                      # wire shape
    def request_header(self) -> EpochHeader | None                # for system prompt
```

Constructed at run-bind (in `lca/session/lifecycle/bind.py:bind_run_event_session_from_store`); passed via constructor injection to:
- `PromptReasoner` (reads `derive_messages()`)
- `Body.execute_tools(...)` (calls `append_tool_call`, `append_tool_result`)
- The LLM adapter hook (`adapter.complete()` / `adapter.stream()`) (calls `append_assistant_message`)
- The decision parser (no write; reads `derive_messages()` for context)

**Fail-loud**: if the writer is unbound (e.g. misuse in a test or a code path that bypasses run-bind), raise `SessionWriterUnboundError`. No silent None return. No ContextVar lookup.

### C. Persist-before-execute durability invariant

The exact order enforced in the act subgraph (per hermes-agent `agent/turn_tool_round.py:54-149`):

```python
async def dispatch_tool_call(self, *, decision: Decision, writer: RunSessionWriter) -> EffectReceipt:
    """Tool dispatch with persist-before-execute."""

    # 1. Stage the assistant(tool_calls) row in memory
    assistant_msg = {"role": "assistant", "tool_calls": [{"id": call.call_id,
                                                          "name": call.tool_name,
                                                          "arguments": call.arguments}
                                                         for call in decision.tool_calls]}

    # 2. Persist BEFORE executing
    persisted = await writer.append_assistant_message(
        turn=state.turn, step=state.step,
        role="assistant", content=None,
        tool_calls=[{"id": ..., "name": ..., "arguments": ...}],
        usage=None,
    )
    if not persisted:
        # Fail-closed: turn breaks, tool never runs from in-memory state
        return EffectReceipt(outcome="rejected", reason="session_persistence_failed",
                            tool_call_id=call.call_id)

    # 3. Now execute the tool
    observation = await self._safe_executor.execute_once(tool, call.arguments)

    # 4. Persist the tool result (with tool_call_id linking to the assistant row)
    tool_persisted = await writer.append_tool_result(
        turn=state.turn, step=state.step,
        call_id=call.call_id,
        content=observation.content,
        error=observation.error if not observation.success else None,
        meta=observation.extra if observation.extra else None,
    )
    if not tool_persisted:
        return EffectReceipt(outcome="rejected", reason="session_persistence_failed",
                            tool_call_id=call.call_id)

    return EffectReceipt(outcome="ok", observation=observation, tool_call_id=call.call_id)
```

**Why this fixes the bug**: the assistant `tool_calls` row is now in the journal before the next LLM call sees the history. The OpenAI wire shape `[user, assistant{tool_calls=[X]}, tool{X}]` is preserved at the journal level. Orphan tool results are impossible because the assistant row precedes them.

### D. Orphan-drop at LLM-call preparation (OpenAI pattern)

A new graph node `think.history.assemble` runs **immediately before** `think.llm.dispatch`:

```python
async def assemble_history(state: AgentState, writer: RunSessionWriter) -> ModelVisibleRequest:
    """Drop orphan tool/result and dangling reasoning before sending to the model.

    OpenAI Agents SDK's `drop_orphan_function_calls` pattern.
    Mirrors only the contract (orphan-drop), not the implementation details.
    """
    messages = writer.derive_messages()
    messages = _drop_orphan_tool_results(messages)
    messages = _drop_reasoning_after_dropped_calls(messages)
    system = (writer.request_header() or {}).get("system") or ""
    return ModelVisibleRequest(messages=messages, system=system, tools=writer.tools())
```

```python
def _drop_orphan_tool_results(messages: list[Message]) -> list[Message]:
    """Drop tool/result messages with tool_call_id not present in any preceding assistant message."""
    valid_call_ids = {tc["id"] for m in messages
 for m["role"] == "assistant"
 for tc in (m.get("tool_calls") or [])}
    return [m for m in messages
           if not (m["role"] == "tool" and m.get("tool_call_id") not in valid_call_ids)]
```

This catches two failure modes:
1. A tool call got cancelled but no tool result was appended (the orphan path the original bug exposed).
2. A reasoning item was emitted before a call but the call was dropped.

### E. Graph-node-ification of the think subgraph

Per the user's "图节点化", split the existing `think.reason.complete` into three single-responsibility graph nodes:

```yaml
# bundles/concept/think_subgraph.yaml (new) or think.yaml (in-place)
nodes:
  - id: think.history.assemble
    region: phase:think
    binding: node_executor
    sub_spec_ref:
      plan_ref: bundles/concept/history_assemble.yaml
      entry_node: history.derive
    inputs: [state]
    outputs: [model_visible_request]
    terminal_predicate: |
      if state.message_accepted is False: return ("continue", state)

  - id: think.llm.dispatch
    region: phase:think
    binding: node_executor
    sub_spec_ref:
      plan_ref: bundles/concept/llm_dispatch.yaml
      entry_node: llm.call
    inputs: [model_visible_request, state]
    outputs: [llm_response, usage]

  - id: think.decision.parse
    region: phase:think
    binding: node_executor
    sub_spec_ref:
      plan_ref: bundles/concept/decision_parse.yaml
      entry_node: decision.parse
    inputs: [llm_response, state]
    outputs: [decision]
    terminal_predicate: |
      if decision.action_type == "respond" or decision.action_type == "ask_user":
        return ("exit", decision)
```

The reason node (`think.reason`) becomes the orchestrator that wires these three nodes via edges. The `complete` node is **deleted**.

### F. Drop `max_visits` entirely (subtraction only)

Per the fragility census §6-§9 + DSH reference §10:

Files to delete or modify:
- `lca/contracts/protocols/graph/plan.py` — drop `PlanNode.max_visits` and `_max_visits_positive` validator
- `lca/framework/graph/traversal.py:30-68` — `PlanTraversal.visit` becomes a pure increment; no terminal flip
- `lca/framework/graph/interpreter.py:127-149` — drop the over-budget branch
- `lca/framework/graph/observation.py:170-192` — drop `max_visits` from `metadata_of`
- `lca/framework/graph/lifter.py:133,219` — drop reads
- `lca/framework/graph/plan_sdk.py:336` — drop the serializer branch
- `lca/contracts/protocols/declarative/declarative_1/declarative_graph.py:83,93-95` — drop `PhaseNode.max_visits` and PG-001's max_visits check (keep id-only check)
- `lca/contracts/observability/observation/m1_blueprint/__init__.py:23` — drop `PlanNodeSpec.max_visits`
- `lca/harness/declarative/compile/subgraph_resolver.py:200,236-242` — drop the projection
- `lca/harness/profile/plan/explain.py:43` — drop field
- `lca/infrastructure/cli/commands/profile/declarative_graph.py:28` — drop label
- `lca/infrastructure/cli/commands/profile/declarative.py:280` — drop field
- `scripts/lca-inspect-plan.py:38,46` — drop field
- `lca_kernel/boot/plan_validation/checks/max_visits_bounds.py` — delete file
- `lca_kernel/boot/plan_validation/checks/max_visits_vs_scc.py` — delete file
- `lca_kernel/boot/plan_validation/checks/self_loop.py` — delete file (purpose disappears)
- `bundles/**/*.yaml` — drop all 80 `max_visits:` keys
- `tests/lca_kernel/boot/test_max_visits_bounds_check.py` — delete file
- `tests/lca_kernel/boot/test_max_visits_vs_scc_check.py` — delete file
- ~30 test fixtures passing `max_visits=N` — drop the kwarg

**Termination signals after deletion**:
- `Decision(action_type=respond)` from `think.decision.parse` → terminates think↔act loop
- `Decision(action_type=ask_user)` from approval gate → terminates with HIL pause
- `should_terminate` from `act.observe` → terminates the run
- `AgentState.budget.max_steps=50`, `max_wall_clock_seconds=300`, `max_tokens` (when wired) — caps on cost
- For runtimes needing it: `MultiToolLoopBreaker` opt-in (kept in codebase, not in default `think.gate` chain)

### G. System prompt → `system` field (fix duplication)

Per hermes-agent `agent/system_prompt.py` + DSH `packages/core/session/src/types.ts:218-260` (`EpochHeader.system`):

Change `openai_messages_with_history(prompt, history)` to `openai_messages_with_history(system, prompt, history)`:

```python
def openai_messages_with_history(system: str | None, prompt: str, history: list[Message] | None) -> list[dict]:
    """OpenAI-compatible messages. System goes to a separate field, not messages[0]."""
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": prompt})
    return msgs
```

The OpenAI Chat Completions API accepts a top-level `"messages"` (with `role: system` allowed as a valid first message) AND a separate field is unnecessary. Per the duplication bug, we need to either:
- (a) Inject `system` as the first `role=system` message (works for both OpenAI and Anthropic; Anthropic recommends top-level `system` but accepts in-messages too).
- (b) Use the provider's native top-level system field (Anthropic: `system` outside `messages`; OpenAI Chat Completions: only `messages[]` with `role:system`).

**Decision**: option (a). Both providers accept `role:system` as the first message; this keeps a single wire path. The model reads the system prompt as a `system` message (not as a user message), which is what the model needs to see.

### H. Cleanup of dual-writer + ContextVar + shadow-helper + stateful-guard mechanism (full census removal)

Per fragility census §1-§5 + §10:

**ContextVar-driven seams to delete:**
- `_current_publish_session` (`lca/plugins/events/publishers/_session_publish.py:67-71`) → no longer needed; `RunSessionWriter` is the seam.
- `_current_cursor` (`lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:63-66`) → replaced by explicit DI; cursor is now an optional parameter on the LLM adapter hook.
- `_current_reasoner_prompt` (`lca/plugins/events/hooks/model_visible/reasoner_prompt.py:47-49`) → replaced by explicit DI.

**Dual-writer pairs to collapse:**
- `complete_model` (catalog + surface) → catalog emit goes via `Session.append_catalog_bound` (still allowed for non-model-visible facts), surface emit goes via `RunSessionWriter.append_assistant_message`.
- `accept_user_message` (catalog + surface) → split into `RunSessionWriter.append_user_message` (surface) + `Session.append_catalog_bound(MessageAccepted(...))` (catalog).
- `append_user_surface` + `append_human_answer_surface` → unified into `RunSessionWriter.append_user_message(role="user"|"human", ...)`.
- `append_tool_result_surface` + `commit_body_tool_execute_end` → unified into `RunSessionWriter.append_tool_result(call_id, content, error, meta)`.

**Idempotency stateful guards to delete:**
- `_LifecycleState.message_accepted` / `open_step` / `turn_open` / `approval_pause_emitted` (`lca/infrastructure/session/emit/lifecycle_emit.py:41-51`) → removed; idempotency comes from Session's append-only log + Reducer contract. No in-process stateful guard for "have we written this yet"; the journal is the source of truth.
- `_state()` lazy init that returns default `_LifecycleState` when ContextVar unset → no longer needed.

**Shadow / overflow modules to delete:**
- `lca/infrastructure/session/_overflow_0/` entire module (`__init__.py`, `bindings.py`)
- `tests/support/tool_history_fixtures.py` (ADR-0193 retired)
- `tests/scenario/tool_0/test_tool_conversation.py` (uses `build_tool_history`)
- `lca/runtime/loop/runtime_loop.py:191` `accept_user_message` → replaced by `RunSessionWriter.append_user_message`

**Silent no-op paths to delete or fail-loud:**
- `_bound_publish_writer` returning None → no longer exists.
- `safe_executor._execute_once` passing `session=None, state=None` to `commit_body_tool_execute_end` → replaced by `RunSessionWriter` injection.
- `_snapshot_attrs(self._cursor_provider())` returning None → cursor is no longer a ContextVar dependency.

### I. Plugin surface (LCA keeps its plugin model)

LCA's plugin model (`@plugin(id=, provides=, requires=, effects=)`) is **structurally superior** to hermes-agent's directory-based plugin discovery (per the comparison in §9.2 of the hermes-agent report). Adopt:

- **Keep** LCA's plugin Manifest with `provides`/`requires`/`effects` enforcement (`UndeclaredInteractionError`).
- **Delete** the in-source `lca_kernel/boot/plan_validation/checks/self_loop.py`; replace self-loop warnings with a `terminal_predicate`-based check at node-execution time.
- **Add** a `RunSessionWriter` plugin slot — profiles may provide a custom `RunSessionWriter` if they need a non-default backend (e.g. a remote journal).

### J. Test plan

Three new tests:
1. **`tests/integration/test_run_with_tool_use.py`** — re-runs the failing `run_cc39610072bf` user-text end to end on `web-standard`, asserts terminal outcome = success and `messages[-1].role == "assistant"` with non-empty content. **Currently fails on `main`. Passes after PR3.**
2. **`tests/integration/test_persist_before_execute.py`** — drives a Session with a failing `Session.append` between assistant-message and tool-execution; asserts the turn breaks (`Verdict(rejected, reason="session_persistence_failed")`) and the tool never runs.
3. **`tests/integration/test_orphan_tool_result_drop.py`** — drives a Session with `[user, assistant{tool_calls=[X]}, tool{call_id=Y}]` (orphan); asserts `think.history.assemble` drops the orphan `tool{Y}` before passing to the model.

Updates to existing tests:
- All 30+ test fixtures passing `max_visits=N` → drop the kwarg.
- Delete `tests/lca_kernel/boot/test_max_visits_bounds_check.py`, `test_max_visits_vs_scc_check.py`.

### K. Compatibility / migration

**No COMPAT shim.** AGENTS.md §4: "引入兼容 shim 的同一 PR 必须同时删除它". The user has been clear: garbage out, first principles in.

The migration is **one wave, three sequential PRs** (per dependency order):

1. **PR1 — subtraction only.** Delete `max_visits` from PlanNode, PhaseNode, PlanTraversal, PlanInterpreter, all yaml, all boot checks, all test fixtures. Run all tests. Behavior change: `max_visits=N` declarations become no-ops (which they already were for N=1); the over-budget terminal flip is gone. **Risk**: latent loops without a hard cap. **Mitigation in this PR**: write a regression test that asserts an agent making 5 consecutive identical tool calls terminates via `AgentState.budget` or `Decision(respond)`.

2. **PR2 — write-path refactor + persist-before-execute.** Add `RunSessionWriter` (the new dependency-injected seam). Refactor `safe_executor` + the LLM adapter hook to use it. Add `think.history.assemble` (orphan-drop) graph node. Add the `think.llm.dispatch` + `think.decision.parse` graph nodes (split `think.reason.complete`). Delete `append_surface_bound`, `_bound_publish_writer`, `assemble_model_history`, `append_tool_result_surface`, the surface branch of `complete_model`, `_overflow_0/`. Fix the system prompt duplication in `openai_messages_with_history`. Delete the three ContextVars (`_current_publish_session`, `_current_cursor`, `_current_reasoner_prompt`). Delete `_LifecycleState` stateful guards. Add the three integration tests.

3. **PR3 — DAG DSL expressive power (the "everything is graph-noded" move).** Add a `@graph_node` decorator that wraps imperative functions as typed nodes with explicit DTO inputs/outputs and `terminal_predicate`. The phase graph becomes a graph of `@graph_node`s, not Python functions in `_run_phase`-style introspection (per hermes-agent's anti-pattern of `_LoopState` 30+ fields). Convert `agent/conversation_loop.py`'s phase helpers to `@graph_node`s. This is the **real** "图节点化" deliverable — making the graph a graph, not imperative while-loops over dataclass-of-everything.

PR3 is the largest and can be split further if needed. The user's "一切图化" instruction points here.

## Sequencing rationale

PR1 has the lowest review surface (subtraction only). PR2 introduces the fix for the immediate bug + the architectural cleanup of the write path. PR3 is the "图节点化" deliverable that completes the user's vision.

## Cross-cutting decisions (recap of resolved questions)

| Question | Resolution | Source |
|---|---|---|
| Wave vs one-shot | 3 sequential PRs | user + principle-sequence-verifiable-units |
| DSH names vs LCA names | DSH names | user (DSH对齐) |
| Graph-node-ification scope | 3 nodes: `think.history.assemble`, `think.llm.dispatch`, `think.decision.parse` (per turn, in this PR); full @graph_node DSL in PR3 | user (图节点化) |
| MultiToolLoopBreaker promotion | Do not promote to default; stays opt-in | cross-check OpenAI/Anthropic/LangGraph/DSH — none have it |
| System prompt duplication | Fix in PR2 | user (对齐DSH) |
| AgentState.budget defaults | Keep `max_steps=50`, `max_wall_clock_seconds=300` | not changed |
| `~/hermes-agent` reference | Adopt persist-before-execute + `_DB_PERSISTED_MARKER` + classification + JSONL diversion | hermes-agent census §5 |
| `~/deepseek-harness` reference | Adopt Session surface taxonomy + SessionProjectionRegistry pattern (later, if LCA Reducer needs work) | DSH census §10 |

## Verification

For each PR:
- `ruff check`, `ruff format --check`
- `pytest tests/unit/ tests/integration/` — all existing tests must pass after the relevant PR
- `pytest tests/integration/test_run_with_tool_use.py` — currently fails on `main`; passes after PR2
- `pytest tests/integration/test_persist_before_execute.py` — passes after PR2
- `pytest tests/integration/test_orphan_tool_result_drop.py` — passes after PR2
- `lca-ops runs create --user-text "请用 bash 工具运行 echo hello 并把结果告诉我。" --profile web-standard` — terminal outcome = success (manual smoke test)
- `lca-ops plan tree <profile>` — no `max=` labels in the rendered graph (visual confirmation that `max_visits` is gone)

For PR3:
- New `tests/framework/graph/test_graph_node_decorator.py` — exercises `@graph_node(fn)` and the typed DTO I/O contract
- Conversion of `agent/conversation_loop.py` phase helpers — each becomes a typed `@graph_node`
- Visual smoke test: `lca-ops plan tree web-standard` renders the full phase graph as a DAG with explicit nodes + typed ports (instead of the current single-string-per-node label)