# Agent Note: Session write-path collapse + persist-before-execute — PR2

Status: implemented

## Problem

The conversation-history write path is held together by two parallel mechanisms (`lca.infrastructure.session.emit.lifecycle_emit` with `_LifecycleState` + `lca.loop.fact_gateway._bound_publish_writer`), bound by separate ContextVars (`_current_publish_session`, `_current_cursor`, `_current_reasoner_prompt`). The model-visible hook at `adapter.py:185, 222` silently drops the `assistant{tool_calls}` surface event when the cursor ContextVar returns `None`; the `tool_result` surface succeeds because it uses a different ContextVar. The system prompt is duplicated as `messages[0]={'role': 'user', …}` instead of going into a `system` field. The legacy `_overflow_0/bindings.py:assemble_model_history(step=)` shim short-circuits to `[]` when unbound. Run `cc39610072bf` (the symptom the user filed) died on a `role=tool` message with no preceding `assistant{tool_calls}` row — the OpenAI wire shape was broken at the journal level.

## Decision

PR2 collapses the dual-stream write path to one DI'd writer (`RunSessionWriter`) per run, persists the assistant `tool_calls` row before executing any tool (per hermes-agent `agent/turn_tool_round.py:54-149`), and drops orphan `tool` results at every LLM-call preparation step (per OpenAI Agents SDK's `drop_orphan_function_calls`):

- `RunSessionWriter` is constructed at run-bind and injected into the LLM adapter hook, `Body.execute_tools`, the decision parser, and `PromptReasoner`. It owns `append_user_message` / `append_assistant_message` / `append_tool_call` (log-only) / `append_tool_result` / `derive_messages` / `request_header`. Unbound state raises `SessionWriterUnboundError` — no silent None.
- The act subgraph persists the assistant `tool_calls` row before tool execution; on persistence failure the turn breaks with `EffectReceipt(rejected, reason="session_persistence_failed")` and the tool never runs from in-memory state.
- `openai_messages_with_history(prompt, history)` becomes `openai_messages_with_history(system, prompt, history)`; the system prompt lands as a `role=system` message at index 0.
- `think.reason.complete` is replaced by three single-responsibility graph nodes: `think.history.assemble` (orphan-drop + history + system), `think.llm.dispatch`, `think.decision.parse`.
- Deleted (no COMPAT): `_bound_publish_writer`, `append_surface_bound`, `append_tool_result_surface`, `assemble_model_history`, `_overflow_0/`, `_LifecycleState`, the three ContextVars (`_current_publish_session`, `_current_cursor`, `_current_reasoner_prompt`), `lifecycle_emit.py`, `surface_emit.py`, `tool_surface_emit.py`.

## Alternatives considered

- **Keep dual-writer + add orphan-drop only** — rejected: dual-writer is the root cause; fixing symptoms while keeping the cause invites the next regression. With persist-before-execute the orphan path never starts.
- **`RunSessionWriter` as a Protocol with multiple impls (in-memory, jsonl, remote)** — rejected: one concrete impl fits the spec; the plugin slot can land in PR3 alongside the `@graph_node` DSL. A Protocol-with-one-impl is speculative abstraction per AGENTS.md §3 modularity.
- **Orphan-drop at the LLM adapter hook** — rejected: orphan-drop belongs to the journal-fold step that produces `messages[]`. An adapter-side check re-introduces context-bound rescue logic.
- **Persist assistant `tool_calls` in-memory only, flush at end of turn** — rejected: this is the in-memory failure mode the original bug exposes. A mid-turn crash leaves the journal without the assistant row and the next resume re-issues the same call. Durability must be at the journal level.
- **Add `MultiToolLoopBreaker` to the default `think.gate` chain** — rejected: cross-checked against OpenAI / Anthropic / LangGraph / DSH — none have an analogous built-in gate. With correct wire shape the orphan cycle never starts; the breaker becomes a complex fingerprint detector guarding against an event that no longer occurs.

## Consequences

- The orphan cycle that motivated fingerprint detection (`run_cc39610072bf`) never starts: persist-before-execute keeps the wire shape correct at the journal level, and orphan-drop at `think.history.assemble` catches any pre-existing orphan rows.
- `Session` is the single SSOT for conversation history per ADR-0186; the dual-stream surface branch is gone. `MultiToolLoopBreaker` stays opt-in.
- The ContextVar mechanism shrinks to its valid use case (transport / scope plumbing); primary dependencies are DI'd. `_LifecycleState` stateful guards are gone; idempotency comes from the append-only journal + Reducer contract.
- Surface event taxonomy aligns with DSH: `surface/user_message`, `surface/assistant_message`, `surface/tool_result`, `log/tool_call` (non-surface pairing record).
- New integration tests: `tests/integration/test_run_with_tool_use.py` (re-runs `run_cc39610072bf` end to end), `tests/integration/test_persist_before_execute.py` (failing `Session.append` → `Verdict(rejected, "session_persistence_failed")`), `tests/integration/test_orphan_tool_result_drop.py` (orphan `tool{Y}` row dropped before LLM dispatch).

## Cross-references

- ADR: [docs/adr/0226-session-write-path-collapse.md](../../../adr/0226-session-write-path-collapse.md)
- Spec: [docs/superpowers/specs/2026-09-15-session-write-path-design.md](../../../superpowers/specs/2026-09-15-session-write-path-design.md) §A-§K
- Plan: [docs/superpowers/plans/2026-09-15-pr1-remove-max-visits.md](../../../superpowers/plans/2026-09-15-pr1-remove-max-visits.md) (PR1; this note covers PR2)
- Prior ADR (PR1): [docs/adr/0225-drop-max-visits-graph-invariant.md](../../../adr/0225-drop-max-visits-graph-invariant.md)
- Prior note (PR1): [docs/notes/implemented/seam/2026-09-15-pr1-drop-max-visits.md](../seam/2026-09-15-pr1-drop-max-visits.md)
