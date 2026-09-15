# ADR-0226: Session write-path collapse + persist-before-execute

## Status

Proposed → Implemented in the same PR (PR2 of the session-write-path redesign; PR1 dropped `max_visits` per ADR-0225)

## Context

A tool-using run on the `web-standard` profile (`run_cc39610072bf`) terminated with `budget_exceeded: node 'think.main' visited 3 times (max_visits=2)`. The LLM received a `role=tool` message with content `"hello"` but no preceding `assistant{tool_calls=…}` row. The OpenAI tool-use wire shape was broken at the journal level; the model re-issued the same call and burned through `max_visits`. PR1 (ADR-0225) removed the counter; this ADR removes the cause of the broken wire shape.

A five-investigation census (fragility census §1-§5; DSH §10; OpenAI/Claude/LangGraph/Temporal/Inngest; hermes-agent §5) localized the defect to one design choice — **two parallel mechanisms** for what is logically one conversation-history write:

| Mechanism | Site | Failure mode |
|---|---|---|
| `lca.infrastructure.session.emit.lifecycle_emit` + `_LifecycleState` | `lifecycle_emit.py:39-89` | `_LifecycleState.message_accepted`, `open_step`, `turn_open`, `approval_pause_emitted` are stateful guards layered on top of the journal; idempotency should come from the journal itself |
| `lca.loop.fact_gateway._bound_publish_writer` | `fact_gateway.py:172-188` | Returns `None` silently when both `session` and `current_publish_session()` are unset; the entire `append_surface_bound` / `append_tool_result_surface` chain becomes a no-op |

The two mechanisms are bound by separate ContextVars (`_current_publish_session` for surface, `current_publish_session` for catalog; `_current_cursor` for the observability cursor; `_current_reasoner_prompt` for the system prompt). The model-visible hook at `lca/plugins/events/hooks/model_visible/adapter.py:185, 222` walks the cursor ContextVar; if it returns `None` the entire pre/post hook block is bypassed and the `assistant{tool_calls}` surface event is silently dropped. The `tool_result` surface succeeds because it uses a different ContextVar. Two ContextVars, two writers, two failure modes for one logical conversation-history write.

Cross-cutting symptoms:

- `lca/infrastructure/session/_overflow_0/` shadow module (`bindings.py`, `__init__.py`) re-exports the legacy `assemble_model_history(step=)` helper alongside the new `DefaultModelContextAssembler`. The new assembler is the SSOT; the legacy helper is a shim that short-circuits to `[]` when the ContextVar is unbound (`assemble_model_history` `tests/_probe/test_assemble_history_growth.py:113`).
- The system prompt is duplicated as `messages[0]={'role': 'user', 'content': prompt}` instead of going into a `system` field (`lca/infrastructure/llm_adapter/openai_compat/history/_history.py:11-13`). Some models treat the duplicated prompt as a user-role instruction, which suppresses the `assistant` role and produces the orphan cycle.
- `accept_user_message` in `lca/runtime/loop/runtime_loop.py:191` reaches into the dual-writer surface; the catalog and surface branches share no fail-loud boundary.

Cross-checked against DSH (`packages/core/session/src/types.ts:430-460`), OpenAI Agents SDK (`drop_orphan_function_calls`), and hermes-agent (`agent/turn_tool_round.py:54-149`):

- **DSH** uses one `Session.append(<type>, data, …surfaceOpts?)` with conditional surface opts — a single seam, fail-loud.
- **OpenAI** runs `drop_orphan_function_calls` before every LLM dispatch — orphan `tool` results with no preceding `assistant{tool_calls}` row are pruned.
- **hermes-agent** persists the assistant `tool_calls` row **before** executing the tool; on persistence failure the turn breaks with `turn_exit_reason="session_persistence_failed"` and the tool never runs from in-memory state. The persist-before-execute invariant makes orphan tool results impossible at the journal level.

AGENTS.md §3 C1 classifies this as a change to core event semantics (new `Session` event names + a new wire-shape guarantee), which mandates an ADR before code.

## Decision

Collapse the dual-stream write path to one DI'd writer per run; persist the assistant `tool_calls` row before executing any tool; drop orphan `tool` results at every LLM-call preparation step; delete every fragile mechanism identified in the census. **No COMPAT shim.** AGENTS.md §4: shim-without-delete-when = 红灯; the owner is PR2 itself.

### 1. `RunSessionWriter` — the only surface-write seam

Add `lca/runtime/session/run_session_writer.py` with a concrete class (no Protocol yet; the spec lists one implementation, PR3 adds the plugin slot):

```python
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

Constructed at run-bind in `lca/session/lifecycle/bind.py:bind_run_event_session_from_store`; passed via constructor injection to:

- `PromptReasoner` (reads `derive_messages()`)
- `Body.execute_tools(...)` (calls `append_tool_call`, `append_tool_result`)
- The LLM adapter hook (`adapter.complete()` / `adapter.stream()`) (calls `append_assistant_message`)
- The decision parser (no write; reads `derive_messages()` for context)

Fail-loud: if the writer is unbound (e.g. misuse in a test or a code path that bypasses run-bind), raise `SessionWriterUnboundError`. **No silent None return. No ContextVar lookup.**

### 2. Persist-before-execute durability invariant

Enforced in the act subgraph, per hermes-agent `agent/turn_tool_round.py:54-149`:

```python
async def dispatch_tool_call(self, *, decision: Decision, writer: RunSessionWriter) -> EffectReceipt:
    # 1. Stage the assistant(tool_calls) row in memory
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
```

The OpenAI wire shape `[user, assistant{tool_calls=[X]}, tool{X}]` is now preserved at the journal level. Orphan tool results are impossible because the assistant row precedes them.

### 3. Drop the surface branch of `complete_model`; split `think.reason.complete`

- `complete_model` in the LLM adapter hook stops emitting `append_surface_bound`. The catalog branch (when present) goes via `Session.append_catalog_bound`; the surface emit goes via `RunSessionWriter.append_assistant_message` injected into the adapter.
- `think.reason.complete` is replaced by three single-responsibility graph nodes:
  - `think.history.assemble` (orphan-drop + history + system; reads `writer.derive_messages()` + `writer.request_header()`)
  - `think.llm.dispatch` (single LLM call)
  - `think.decision.parse` (parse the response into a `Decision`)
- The reason node (`think.reason`) wires these three via edges. `complete` is deleted.

### 4. Fix system-prompt duplication

Change `openai_messages_with_history(prompt, history)` to `openai_messages_with_history(system, prompt, history)`:

```python
def openai_messages_with_history(system: str | None, prompt: str, history: list[Message] | None) -> list[dict]:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": prompt})
    return msgs
```

Both providers accept `role:system` as the first message; this keeps a single wire path. `anthropic_messages_with_history` receives the same signature for symmetry (Anthropic accepts `role:system` in-messages).

### 5. Delete (no COMPAT) — every site enumerated in the consumer-site inventory

- `_bound_publish_writer` (`lca/loop/fact_gateway.py:172-188`)
- `append_surface_bound` (`lca/loop/fact_gateway.py:209`), `append_catalog_bound`, `publish_ep_bound`, `fact_gateway_for_emit`
- `append_tool_result_surface` (`lca/infrastructure/session/emit/tool_surface_emit.py:14-49`) and the entire `tool_surface_emit.py` module
- `assemble_model_history` (`lca/infrastructure/session/_overflow_0/bindings.py:106`)
- `lca/infrastructure/session/_overflow_0/` entire module (`__init__.py`, `bindings.py`)
- `accept_user_message` (`lca/infrastructure/session/emit/lifecycle_emit.py:89`, `lca/runtime/loop/runtime_loop.py:191`) — replaced by `RunSessionWriter.append_user_message`
- `_LifecycleState` (`lca/infrastructure/session/emit/lifecycle_emit.py:46-89`) — stateful guards deleted; idempotency comes from Session's append-only log + Reducer contract
- `lca/infrastructure/session/emit/lifecycle_emit.py` entire module
- `lca/infrastructure/session/emit/surface_emit.py` entire module
- The three ContextVars:
  - `_current_publish_session` (`lca/plugins/events/publishers/_session_publish.py`)
  - `_current_cursor` (`lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:65`)
  - `_current_reasoner_prompt` (`lca/plugins/events/hooks/model_visible/reasoner_prompt.py:47`)

Every consumer site listed in the inventory is migrated to the writer or deleted; no `if contextvar is not None` fallback is introduced.

### 6. Orphan-drop at LLM-call preparation (OpenAI pattern)

A new graph node `think.history.assemble` runs **immediately before** `think.llm.dispatch`:

```python
async def assemble_history(state: AgentState, writer: RunSessionWriter) -> ModelVisibleRequest:
    messages = writer.derive_messages()
    messages = _drop_orphan_tool_results(messages)
    messages = _drop_reasoning_after_dropped_calls(messages)
    system = (writer.request_header() or {}).get("system") or ""
    return ModelVisibleRequest(messages=messages, system=system, tools=writer.tools())
```

```python
def _drop_orphan_tool_results(messages: list[Message]) -> list[Message]:
    valid_call_ids = {tc["id"] for m in messages if m["role"] == "assistant"
                      for tc in (m.get("tool_calls") or [])}
    return [m for m in messages
            if not (m["role"] == "tool" and m.get("tool_call_id") not in valid_call_ids)]
```

This catches two failure modes:

1. A tool call was cancelled but no tool result was appended (the orphan path the original bug exposed).
2. A reasoning item was emitted before a call but the call was dropped.

`MultiToolLoopBreaker` remains available for runtimes that need fingerprint-based loop detection; PR2 does **not** add it to the default `think.gate` chain (cross-checked against OpenAI/Anthropic/LangGraph/DSH — none have an analogous built-in gate).

### 7. Surface event taxonomy (DSH-aligned)

Replace `SURFACE_USER_TYPE`, `SURFACE_ASSISTANT_TYPE`, `SURFACE_TOOL_RESULT_TYPE` with DSH-aligned names:

```text
surface/user_message         # role=user, content
surface/assistant_message   # role=assistant, content|None, tool_calls[], usage?
surface/tool_result         # role=tool, tool_call_id, content, error?
log/tool_call               # NOT a surface event; pairs surface/tool_result via sourceEventSeqs
```

Closed set (`SurfaceEventType`) enforced at type-level via DSH's pattern (`packages/core/session/src/types.ts:430-460`): `surface_op` and `source_event_seqs` are conditionally required only on `SurfaceEventType` variants. LCA's equivalent: a Pydantic discriminated union `SessionEventType` where surface variants require `surface_op` and `source_event_seqs`. `log/tool_call` is **not** a surface event; the Session fold derives messages by walking only surface events.

## Consequences

- The orphan cycle that motivated fingerprint detection in `MultiToolLoopBreaker` never starts: persist-before-execute keeps the wire shape correct at the journal level, and orphan-drop at `think.history.assemble` catches any pre-existing orphan rows.
- `Session` becomes the single SSOT for conversation history per ADR-0186; the dual-stream surface branch is gone.
- The ContextVar mechanism shrinks to its valid use case (transport / scope plumbing per the OpenAI/Claude SDK pattern), not as a stand-in for primary dependency injection.
- `_LifecycleState` stateful guards are gone; idempotency comes from the append-only journal + Reducer contract (per C9 / C12).
- The system prompt reaches the model as a `system` message, not as a user-role instruction.
- Tests added in `tests/integration/`: `test_run_with_tool_use.py` (the `run_cc39610072bf` regression), `test_persist_before_execute.py`, `test_orphan_tool_result_drop.py`.
- Plugin slot for `RunSessionWriter` is **deferred to PR3** (the `@graph_node` DSL wave). The spec lists a single concrete class; multi-backend support is a plugin concern, not a write-path concern.

## Alternatives considered

- **Keep the dual-writer + add `drop_orphan_function_calls` only.** Rejected: the dual-writer is the root cause (two ContextVars, two failure modes, one logical conversation write). Fixing the symptom (orphan-drop) while keeping the cause is permanent debt; the next regression will be a different orphan path that orphan-drop also fails to catch.
- **Make `RunSessionWriter` a Protocol with multiple impls (in-memory, jsonl, remote).** Rejected: the spec lists a single concrete class; the plugin slot can be added in PR3 once the `@graph_node` DSL provides a typed way to express the seam. A Protocol-with-one-impl is speculative abstraction.
- **Move orphan-drop to the LLM adapter hook.** Rejected: the LLM adapter is the wrong layer. Orphan-drop belongs to the journal-fold step that produces `messages[]`, not to a side-effecting adapter. An adapter-side check would re-introduce a context-bound, adapter-specific rescue path.
- **Persist assistant `tool_calls` row in-memory only; flush at end of turn.** Rejected: this is the in-memory failure mode the original bug exposes. A crash mid-turn leaves the journal without the assistant row and the next resume re-issues the same call. Durability must be at the journal level, not at the in-memory adapter.
- **Add `MultiToolLoopBreaker` to the default `think.gate` chain.** Rejected: cross-checked against OpenAI / Anthropic / LangGraph / DSH — none have an analogous built-in gate. With correct wire shape the orphan cycle never starts; the breaker becomes a complex fingerprint detector guarding against an event that no longer occurs.
- **Introduce a Protocol for `RunSessionWriter` and ship both the default + a jsonl impl in this PR.** Rejected: AGENTS.md §3 modularity — "Plugin points are real only when at least two implementations exist or are concrete enough to imagine". One impl + a Protocol-with-no-second-impl is speculative abstraction; PR3 adds the slot.
