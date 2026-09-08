# Survey: Direct Emit Sites

Read-only survey of LCA codebase enumerating every code site that **directly produces** a spine/journal event bypassing `Session.append`. The architecture mandates `Session.append` is the sole production entry (ADR-0186/0191/0194, C3, C11).

---

## Session.append — sole production entry

- **definition**: `lca/session/append.py:139` — `Session.append`
- **signature**:

```python
def append(
    self,
    event_type: str,
    data: Mapping[str, Any],
    *,
    actor: str | None = None,
    visibility: str = "model",
    ignorable: bool = False,
    surface_op: Any | None = None,
    source_event_seqs: tuple[int, ...] | None = None,
) -> SessionEvent:
```

- **class definition**: `lca/session/append.py:59` — `class Session(SessionProtocol)`
- **Protocol declarations** (alternate entry points referenced from FactGateway):
  - `lca/contracts/protocols/loop/fact_gateway.py:32` — `class FactGateway(Protocol)` with methods `append_catalog`, `publish_ep`, `append_surface`, `append_diagnostic`.
  - `lca/contracts/protocols/loop/fact_gateway.py:27` — `class AppendReceipt`.

The fact path: every fact goes through one of:
1. `Session.append` directly (typed catalog/surface nodes).
2. `DefaultFactGateway` (`lca/loop/fact_gateway.py:115`) → which routes to `Session.append` via `_catalog_session.append(...)` (`lca/loop/fact_gateway.py:127-167`).
3. `RunEventSessionBridge.append` (`lca/session/lifecycle/bind.py:107`) → which calls `self._session.append(event_type, data)` (`lca/session/lifecycle/bind.py:120`).
4. `SpineWritePortAdapter.append` (`lca/plugins/session/runtime/cursor/port.py:88`) → which calls `self._session.append(execution_point, data)` (or via bridge).

---

## Spine / journal whitelist (from `lca_kernel/events/config/observability/spine.yaml`)

All categories listed in the closed-set whitelist `lca_kernel/events/config/observability/spine.yaml`:

| Category | Line | Publisher |
|---|---|---|
| `spine.cognition.brain.perceive.start` | :20 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.brain.perceive.end` | :30 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.brain.think.start` | :38 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.brain.think.end` | :48 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.think.gate.start` | :57 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.think.gate.end` | :67 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.critic.eval.start` | :76 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.critic.eval.end` | :86 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.reasoner.reason.start` | :95 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.reasoner.reason.end` | :105 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.prompt_assembler.assemble.start` | :114 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.prompt_assembler.assemble.end` | :124 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.synthesizer.merge` | :137 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.skill_router.route` | :145 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.memory.read` | :154 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.cognition.memory.write` | :164 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.body.tool.execute.start` | :176 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.body.tool.execute.end` | :186 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.body.tool.retry` | :204 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.body.sandbox.enter` | :217 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.body.sandbox.exit` | :227 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.lifecycle.finally` | :237 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.llm.call.start` | :246 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.llm.call.end` | :259 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.llm.stream.token` | :268 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.llm.stream.stall` | :281 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.llm.request.header` | :295 | `events.model_visible.publisher` |
| `spine.llm.request.header.assistant` | :307 | `events.model_visible.publisher` |
| `spine.exception.caught` | :325 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.exception.finally` | :335 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.runtime.reducer.apply` | :347 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.runtime.checkpoint.create` | :357 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.runtime.resume.start` | :367 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.runtime.resume.end` | :377 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.runtime.event_publisher.publish` | :388 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.transport.route.enter` | :402 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.transport.route.exit` | :412 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.transport.sse.publish` | :423 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.kernel.boot.start` | :436 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.kernel.boot.completed` | :446 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.kernel.run.start` | :454 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.kernel.run.stop` | :464 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.kernel.run.cancelled` | :474 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.agent_loop.iteration.start` | :486 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.agent_loop.iteration.end` | :496 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.loop.fork` | :512 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.agent.spawn` | :520 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.agent.iteration` | :531 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.agent.final` | :543 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.writable.step.start` | :557 | `events.spine.writable_matrix` |
| `spine.writable.step.end` | :567 | `events.spine.writable_matrix` |
| `spine.writable.segment.start` | :577 | `events.spine.writable_matrix` |
| `spine.writable.segment.end` | :587 | `events.spine.writable_matrix` |
| `spine.writable.iteration.halt` | :601 | `events.spine.writable_matrix` |
| `spine.writable.iteration.closing` | :611 | `events.spine.writable_matrix` |
| `spine.writable.iteration.close` | :620 | `events.spine.writable_matrix` |
| `spine.step.thinking.record` | :627 | `events.spine.loop_cursor` |
| `spine.step.tool_call.record` | :636 | `events.spine.loop_cursor` |
| `spine.step.tool_result.record` | :645 | `events.spine.loop_cursor` |
| `spine.step.reflect.record` | :656 | `events.spine.loop_cursor` |
| `spine.step.span.record` | :666 | `events.spine.loop_cursor` |
| `spine.i17.rejected` | :673 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.producer.failure` | :681 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.perceive.phase.fold` | :689 | `events.spine.loop_cursor` |
| `spine.phase.perceive.fold` | :699 | `events.spine.loop_cursor` |
| `spine.phase.think.fold` | :709 | `events.spine.loop_cursor` |
| `spine.phase.remember.fold` | :722 | `events.spine.loop_cursor` |
| `spine.phase.stop.fold` | :732 | `events.spine.loop_cursor` |
| `spine.phase.reflect.fold` | :743 | `events.spine.loop_cursor` |
| `spine.phase.act.fold.start` | :755 | `events.spine.loop_cursor` |
| `spine.phase.act.fold.end` | :765 | `events.spine.loop_cursor` |
| `spine.phase.act.fold` | :777 | `events.spine.loop_cursor` |
| `spine.phase.tool.call.start` | :788 | `events.spine.loop_cursor` |
| `spine.phase.tool.call.end` | :798 | `events.spine.loop_cursor` |
| `spine.phase.tool.denied` | :813 | `events.spine.loop_cursor` |
| `spine.phase_graph.node.start` | :825 | `events.spine.loop_cursor` |
| `spine.phase_graph.node.end` | :834 | `events.spine.loop_cursor` |
| `spine.phase_graph.edge.transit` | :846 | `events.spine.loop_cursor` |
| `spine.phase_graph.instrument.coverage` | :857 | `events.spine.loop_cursor` |
| `spine.team.casting.started` | :865 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.team.casting.completed` | :876 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.team.casting.failed` | :887 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.team.delegation.issued` | :898 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.team.delegation.completed` | :909 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.team.delegation.cache_hit` | :925 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.team.message.published` | :938 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.perception.observe` | :948 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.perception.attention.focus` | :958 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.perception.attention.blur` | :968 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.perception.signal.detected` | :978 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.perception.fused` | :988 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.perception.artifact.built` | :998 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.dispatch` | :1013 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.invoke` | :1023 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.signal` | :1033 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.approve.request` | :1043 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.approve.response` | :1053 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.deny` | :1064 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.revoke` | :1077 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.pause` | :1087 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.resume` | :1098 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.stop` | :1109 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.control.accept` | :1118 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.boot.profile.resolved` | :1128 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.boot.plugin.fiber.spawned` | :1138 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.boot.observability.assembled` | :1148 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.runtime.observed` | :1158 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.runtime.diagnostic` | :1169 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.phase.fact` | :1185 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.phase.evidence` | :1197 | `lca.loop.fact_gateway.DefaultFactGateway` |
| `spine.effect.receipt` | :1207 | `lca.loop.fact_gateway.DefaultFactGateway` |

---

## Direct emit sites (bypassing `Session.append`)

After exhaustive search of `lca/cognition/body/`, `lca/infrastructure/session/`, `lca/infrastructure/observability/`, `lca/contracts/observability/`, `lca/loop/`, `lca_kernel/events/`, the only **direct write site** to the session log is `Session.append` itself plus its bridges (`RunEventSessionBridge.append` at `lca/session/lifecycle/bind.py:107`, `SpineWritePortAdapter.append` at `lca/plugins/session/runtime/cursor/port.py:88`). All other business-path writes route through `DefaultFactGateway` (`lca/loop/fact_gateway.py:115`).

There are **0 sites that bypass `Session.append`** in the strict sense — every fact goes either directly to `Session.append` (raw call) or through the bridge façade, which itself calls `Session.append`.

However, there are multiple **observability-only / advisory** sites that publish spine EPs *outside* of the canonical single-track via the legacy `LoopCursor.record_*` path (which writes to `<run_id>.spine.jsonl` via `spine_port_append` at `lca/infrastructure/observability/loop_cursor/spine/_spine_port.py:128`):

| file | line | function | EP emitted | mechanism |
|---|---|---|---|---|
| `lca/cognition/body/executor/cursor_record.py` | 93 | `CursorRecord.try_record_tool_call` | `spine.step.tool_call.record` | `cursor.record_tool_call(ToolCallRecord)` → `StdLoopCursor._append` → `WritePort.append` → `write_port_append` (`lca/infrastructure/observability/loop_cursor/std/std.py:103`) → `SpineWritePortAdapter.append` (`lca/plugins/session/runtime/cursor/port.py:88`) → `Session.append` (via bridge) |
| `lca/cognition/body/executor/cursor_record.py` | 156 | `CursorRecord.try_record_tool_result` | `spine.step.tool_result.record` | same path as above |
| `lca/cognition/body/emit/tool_journal.py` | 134 | `record_tool_started_observability` (calls `CursorRecord.try_record_tool_call`) | `spine.step.tool_call.record` | indirect via cursor |
| `lca/cognition/body/emit/tool_journal.py` | 201 | `record_tool_denied_observability` (calls `CursorRecord.try_record_tool_result`) | `spine.step.tool_result.record` | indirect via cursor |
| `lca/cognition/body/emit/tool_journal.py` | 300 | `record_tool_invoked_observability` (calls `CursorRecord.try_record_tool_result`) | `spine.step.tool_result.record` | indirect via cursor |
| `lca/cognition/body/executor/safe_executor.py` | 266 | `SimpleSafeExecutor.execute` (calls `CursorRecord.try_record_tool_call`) | `spine.step.tool_call.record` | indirect via cursor |
| `lca/cognition/body/executor/safe_executor.py` | 318 | `SimpleSafeExecutor.execute` (calls `CursorRecord.try_record_tool_result`) | `spine.step.tool_result.record` | indirect via cursor |
| `lca/cognition/body/executor/safe_executor.py` | 334 | `SimpleSafeExecutor.execute` (exception handler; calls `CursorRecord.try_record_tool_result`) | `spine.step.tool_result.record` | indirect via cursor |
| `lca/cognition/body/executor/safe_executor.py` | 550 | `_record_tool_call_evidence` | `spine.step.tool_call.record` | indirect via cursor |
| `lca/cognition/body/executor/safe_executor.py` | 586 | `_record_tool_result_evidence` | `spine.step.tool_result.record` | indirect via cursor |
| `lca/cognition/body/executor/pipeline_safe_executor.py` | 312 | `PipelineSafeExecutor.execute` (calls `CursorRecord.try_record_tool_call`) | `spine.step.tool_call.record` | indirect via cursor |
| `lca/cognition/body/executor/pipeline_safe_executor.py` | 339 | `PipelineSafeExecutor.execute` (success; calls `CursorRecord.try_record_tool_result`) | `spine.step.tool_result.record` | indirect via cursor |
| `lca/cognition/body/executor/pipeline_safe_executor.py` | 359 | `PipelineSafeExecutor.execute` (failure; calls `CursorRecord.try_record_tool_result`) | `spine.step.tool_result.record` | indirect via cursor |
| `lca/cognition/body/executor/pipeline_safe_executor.py` | 369 | `PipelineSafeExecutor.execute` (exception; calls `CursorRecord.try_record_tool_result`) | `spine.step.tool_result.record` | indirect via cursor |
| `lca/infrastructure/observability/loop_cursor/std/std.py` | 308 | `StdLoopCursor.record_thinking` (via `_append`) | `spine.step.thinking.record` | `_append` → WritePort → spine hook → bridge → `Session.append` |
| `lca/infrastructure/observability/loop_cursor/std/std.py` | 333 | `StdLoopCursor.record_tool_call` (via `_append`) | `spine.step.tool_call.record` | same as above |
| `lca/infrastructure/observability/loop_cursor/std/std.py` | 361 | `StdLoopCursor.record_tool_result` (via `_append`) | `spine.step.tool_result.record` | same as above |
| `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py` | 192 | `CoordinatorAdapter.record_thinking` (delegates to `cursor.record_thinking`) | `spine.step.thinking.record` | indirect via cursor |
| `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py` | 216 | `CoordinatorAdapter.record_tool_call` (delegates to `cursor.record_tool_call`) | `spine.step.tool_call.record` | indirect via cursor |
| `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py` | 246 | `CoordinatorAdapter.record_tool_result` (delegates to `cursor.record_tool_result`) | `spine.step.tool_result.record` | indirect via cursor |

These `CursorRecord` / `cursor.record_*` paths are **second-track**: they reach the spine (and ultimately `Session.append`) through a different seam than the canonical `publish_ep_bound` → `DefaultFactGateway.publish_ep` → `Session.append`. The dual-track path exists because cursor's `WritePort` was the legacy SSOT before ADR-0186/0191/0194 unified to `Session.append`. ADR-0169 task-25 / PR-21~24 still tracks the business-path migration; the COMPAT block in `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:34-41` documents the dual-write migration.

---

## Per-module analysis (the 11 files above)

### `lca/cognition/body/emit/tool_journal.py`

- **public functions**:
  - `prepare_state_evidence` (`lca/cognition/body/emit/tool_journal.py:46`) — writes to `EvidenceStore` (separate from spine), returns `EvidenceRef | None`.
  - `prepare_tool_started` (`lca/cognition/body/emit/tool_journal.py:89`) — produces a `ToolJournalReceipt` (catalog event), no direct spine write.
  - `record_tool_started_observability` (`lca/cognition/body/emit/tool_journal.py:116`) — emits diagnostic + `CursorRecord.try_record_tool_call` (line 134).
  - `emit_tool_started` (`lca/cognition/body/emit/tool_journal.py:148`) — convenience wrapper calling `prepare_tool_started` + `record_tool_started_observability`.
  - `_summarize_args` (`lca/cognition/body/emit/tool_journal.py:177`) — local helper for `arguments_summary`.
  - `prepare_tool_denied` (`lca/cognition/body/emit/tool_journal.py:189`) — produces `ToolJournalReceipt`.
  - `record_tool_denied_observability` (`lca/cognition/body/emit/tool_journal.py:193`) — emits diagnostic + `CursorRecord.try_record_tool_result` (line 201).
  - `emit_tool_denied` (`lca/cognition/body/emit/tool_journal.py:209`) — wrapper.
  - `prepare_tool_invoked` (`lca/cognition/body/emit/tool_journal.py:217`) — produces `ToolJournalReceipt`.
  - `record_tool_invoked_observability` (`lca/cognition/body/emit/tool_journal.py:268`) — emits diagnostic + `CursorRecord.try_record_tool_result` (line 300).
  - `emit_tool_invoked` (`lca/cognition/body/emit/tool_journal.py:315`) — wrapper.
- **emits**: `spine.runtime.diagnostic` (via `emit_diagnostic` at lines 125, 195, 280), `spine.step.tool_call.record` (via `CursorRecord` at line 134), `spine.step.tool_result.record` (via `CursorRecord` at lines 201, 300).
- **via Session.append**: **partial** — diagnostics go through `emit_diagnostic` → `publish_ep_bound` → `DefaultFactGateway.publish_ep` → `Session.append`. Tool call/result EPs go through `CursorRecord` → `cursor.record_*` → `WritePort` → `spine_port_append` → Session hook (`bind_session_append_hook`) → `bridge.append(SpineEventPayload)` → `Session.append`. The latter is **second-track** with the documented COMPAT delete-when.
- **owns invocation_id**: **no** — invocation_id is passed in as a parameter from caller (`SimpleSafeExecutor.execute` or `PipelineSafeExecutor.execute`).
- **owns args_digest**: **yes** — `_summarize_args` at line 177 (also called from line 137, 139).
- **migration status**: **partial** — diagnostic track is on `publish_ep_bound` (single-track); cursor track still routes through `WritePort` (compat).

### `lca/cognition/body/executor/cursor_record.py`

- **public class**: `CursorRecord` (`lca/cognition/body/executor/cursor_record.py:19`).
- **public methods**:
  - `CursorRecord.get()` (line 39) — returns `LoopCursor | None` from `get_current_cursor()` ContextVar.
  - `CursorRecord.try_advance(target, *, action_type)` (line 51) — calls `cursor.advance(target)`.
  - `CursorRecord.try_record_tool_call(*, tool_name, invocation_id, args_digest, arguments, arguments_summary)` (line 68) — calls `cursor.record_tool_call(ToolCallRecord(...))`.
  - `CursorRecord.try_record_tool_result(*, tool_name, result_digest, outcome, ok, ...)` (line 114) — calls `cursor.record_tool_result(ToolResultRecord(...))`.
- **emits**: `spine.step.tool_call.record` (line 93), `spine.step.tool_result.record` (line 156). Note: `try_advance` does **not** emit a spine EP itself; it controls the cursor's phase window.
- **via Session.append**: **partial** — yes, ultimately through the spine hook → bridge → `Session.append`, but the path is `cursor.record_*` → `_append` → `WritePort.append` → `write_port_append` → `spine_port_append` → Session runtime hook (`bind_session_append_hook`) → `bridge.append(SpineEventPayload)` → `Session.append`. Not via `publish_ep_bound`/`DefaultFactGateway`.
- **owns invocation_id**: **no** — passed in by callers (`safe_executor.py:266`, `safe_executor.py:550`, `pipeline_safe_executor.py:312`, `tool_journal.py:134`).
- **owns args_digest**: **no** — passed in by callers (e.g., `tool_journal.py:137` → `_summarize_args`; `safe_executor.py:269` → `f"tool:{tool.name}"`).
- **migration status**: **partial** — SSOT consolidation helper (R2) but on the legacy cursor track.

### `lca/cognition/body/executor/pipeline_safe_executor.py`

- **public class**: `PipelineSafeExecutor(SafeExecutor)` (`lca/cognition/body/executor/pipeline_safe_executor.py:64`).
- **public methods**:
  - `__init__(permission_manifest)` (line 76).
  - `_pipeline_for(tool, retry_policy, cache_config)` (line 86).
  - `_pre_execute_check(tool)` (line 109).
  - `_check_permission_and_args(tool, args)` (line 117).
  - `_execute_with_retry(...)` (line 138).
  - `execute(tool, args, retry_policy, cache_config, invocation_id)` (line 237).
  - `_execute_once(tool, args, attempt)` (line 379).
  - `_validate_args(tool, args)` (line 414) — static.
  - `_record_invoked(...)` (line 425) — static, delegates to `_commit_tool_invoked` from `safe_executor.py`.
- **emits**: `spine.step.tool_call.record` (line 312), `spine.step.tool_result.record` (lines 339, 359, 369). Also delegates to `safe_executor._commit_tool_denied`/`_commit_tool_invoked` which call `commit_tool_journal_receipt` / `commit_tool_phase_denied` etc., which go through `publish_ep_bound` and `append_catalog_bound` → `DefaultFactGateway` → `Session.append`.
- **via Session.append**: **partial** — journal commits go through `DefaultFactGateway` (single-track); cursor calls go through `CursorRecord` → cursor track.
- **owns invocation_id**: **yes** — `invocation_id = invocation_id.strip() or new_id("inv")` at `lca/cognition/body/executor/pipeline_safe_executor.py:249`.
- **owns args_digest**: **no** — `args_digest=f"tool:{tool.name}"` at line 315 (placeholder, not a real digest).
- **migration status**: **partial** — has both catalog commit (single-track) and cursor call (second-track).

### `lca/cognition/body/executor/safe_executor.py`

- **public class**: `SimpleSafeExecutor(SafeExecutor)` (`lca/cognition/body/executor/safe_executor.py:221`).
- **module-level public helpers**:
  - `_commit_tool_denied(tool, reason)` (line 118) — calls `emit_tool_denied` → `commit_tool_journal_receipt` + `commit_tool_phase_denied`.
  - `_commit_tool_started(tool, args, invocation_id, ...)` (line 130) — calls `prepare_tool_started` + `record_tool_started_observability` + `commit_tool_journal_receipt` + `commit_tool_phase_call_start`.
  - `_commit_tool_invoked(tool, args, obs, ...)` (line 160) — calls `emit_tool_invoked` + `commit_tool_journal_receipt` + `commit_tool_phase_call_end`.
  - `_commit_approval_requested(tool, invocation_id)` (line 198) — calls `approval_requested_receipt` + `commit_act_journal_receipt`.
  - `_resolve_evidence_pair()` (line 207).
- **class methods**:
  - `SimpleSafeExecutor.__init__(permission_manifest)` (line 224).
  - `SimpleSafeExecutor.execute(tool, args, retry_policy, cache_config, invocation_id)` (line 239).
  - `SimpleSafeExecutor._execute_with_retry(...)` (line 344).
  - `SimpleSafeExecutor._record_invoked(...)` (line 439) — static.
  - `SimpleSafeExecutor._execute_once(...)` (line 460).
  - `SimpleSafeExecutor._validate_args(...)` (line 533) — static.
- **module-level helpers**:
  - `_record_tool_call_evidence(tool_name, invocation_id)` (line 540) — `CursorRecord.try_record_tool_call`.
  - `_record_tool_result_evidence(...)` (line 557) — `CursorRecord.try_record_tool_result`.
- **emits**: catalog events (`ToolStartedCommitted`, `ToolInvokedCommitted`, `ToolDeniedCommitted`, `ApprovalRequestedCommitted`) via `commit_tool_journal_receipt` and `commit_act_journal_receipt`; spine EPs `phase.tool.call.start` (line 152), `phase.tool.call.end` (line 188), `phase.tool.denied` (line 124 via `_commit_tool_denied`), `body.sandbox.enter` (line 300), `body.sandbox.exit` (line 314), `body.tool.execute.start` (line 472), `body.tool.execute.end` (line 521), `body.tool.retry` (line 414); cursor track `spine.step.tool_call.record` (line 266), `spine.step.tool_result.record` (lines 318, 334).
- **via Session.append**: **partial** — catalog/phase/body commits go through `publish_ep_bound` / `append_catalog_bound` → `DefaultFactGateway` → `Session.append`. Cursor track calls go through `CursorRecord` (second-track).
- **owns invocation_id**: **yes** — `invocation_id = invocation_id.strip() or new_id("inv")` at `lca/cognition/body/executor/safe_executor.py:257`.
- **owns args_digest**: **no** — uses `args_digest=f"tool:{tool.name}"` (lines 269, 553) (placeholder).
- **owns arguments_summary**: **yes** — `_summarize_args_for_cursor` at line 47 (used at lines 155, 271).
- **migration status**: **partial** — catalog body commits are single-track; cursor track is second-track.

### `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py`

- **public functions**:
  - `sha256_digest(payload)` (`lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:72`) — pure helper, no emit.
  - `get_current_cursor()` (line 96) — ContextVar accessor.
  - `bind_current_cursor(cursor)` (line 101) — ContextVar setter.
  - `reset_current_cursor(token)` (line 104) — ContextVar resetter.
  - `current_cursor()` (line 108) — alias for `get_current_cursor`.
- **public class**: `CoordinatorAdapter` (line 118).
- **class methods**:
  - `__init__(*, cursor, coord)` (line 137).
  - `cursor` property (line 142).
  - `coord` property (line 147).
  - `begin_step(phase, **ctx)` (line 154) — calls `coord.begin_step` + `cursor.advance(phase)` if phase differs.
  - `end_step(outcome, *, error)` (line 167) — calls `coord.end_step`.
  - `record_thinking(trace)` (line 178) — calls `cursor.record_thinking(ThinkingRecord(...))`.
  - `record_tool_call(call)` (line 201) — calls `cursor.record_tool_call(ToolCallRecord(...))`.
  - `record_tool_result(result)` (line 228) — calls `cursor.record_tool_result(ToolResultRecord(...))`.
  - `close(reason)` (line 265) — calls `cursor.close(reason)`.
  - `__enter__` (line 279), `__exit__` (line 282) — delegate to coord.
  - `run_id` property (line 287), `trace_id` property (line 291) — delegate.
  - `__getattr__(name)` (line 294) — duck-type passthrough.
- **emits**: `spine.step.thinking.record` (line 192 via `cursor.record_thinking`), `spine.step.tool_call.record` (line 216), `spine.step.tool_result.record` (line 246). Also `cursor.advance(phase)` controls phase window but does not emit a spine EP by itself.
- **via Session.append**: **partial** — yes, indirectly, via `cursor.record_*` → `_append` → `WritePort` → spine hook → bridge → `Session.append`. Not via `DefaultFactGateway.publish_ep`. Documented as COMPAT (delete-when PR-21~24).
- **owns invocation_id**: **no** — pulled from `LegacyToolCallRecord.invocation_id` (line 207) or empty.
- **owns args_digest**: **yes** — `sha256_digest(...)` at lines 187, 217, 248 (helper at line 72).
- **migration status**: **partial** — adapter docstring says "本适配器**不是新控制面**,而是把 `StepCoordinator` 旧 API 翻译成 cursor 新 API 的薄壳"; docstring at lines 7-31 explicitly describes the dual-write behavior. COMPAT block at lines 34-41.

### `lca/infrastructure/session/emit/tool_surface_emit.py`

- **public functions**:
  - `append_tool_result_surface(*, tool_name, invocation_id, attempt, outcome, observation, latency_ms, session, actor, enriched_fields)` (`lca/infrastructure/session/emit/tool_surface_emit.py:13`).
- **emits**: model-visible surface node `SURFACE_TOOL_RESULT_TYPE` (from `lca_kernel.events.fold.fold`) — passed through `append_surface_bound` (line 40).
- **via Session.append**: **yes** — `append_surface_bound` → `DefaultFactGateway.append_surface` → `_catalog_session.append(event_type, dict(data), ...)` (`lca/loop/fact_gateway.py:130-145`). Single-track.
- **owns invocation_id**: **no** — passed in (line 21, 27, 33).
- **owns args_digest**: **no** — N/A for surface node.
- **migration status**: **already migrated** — on `DefaultFactGateway` single-track.

### `lca/infrastructure/session/projections/tool_result_message.py`

- **public functions**:
  - `clip_tool_result_content(text, *, limit)` (`lca/infrastructure/session/projections/tool_result_message.py:14`).
  - `observation_tool_result_content(observation)` (line 24).
  - `build_openai_tool_result_message(*, tool_call_id, content)` (line 46).
  - `build_tool_surface_data(*, tool_name, invocation_id, attempt, outcome, observation, latency_ms, ok)` (line 60).
- **emits**: **none directly** — pure projection/builders returning `dict[str, Any]` consumed by `tool_surface_emit.append_tool_result_surface` (which is the actual emit point).
- **via Session.append**: **n/a** (this module does not emit).
- **owns invocation_id**: **no** — passed in (line 65, 82).
- **owns args_digest**: **no** — N/A.
- **migration status**: **n/a (projection helper)** — not an emit site.

### `lca/loop/commit/tool_journal.py`

- **public functions**:
  - `_phase_tool_context()` (`lca/loop/commit/tool_journal.py:19`) — pulls `(step, run_id)` from `current_run_ambit` / `get_current_run_scope`.
  - `commit_tool_journal_receipt(receipt, *, state, session)` (line 33) — calls `append_catalog_bound(receipt.catalog_event, ...)`.
  - `commit_tool_phase_call_start(*, tool_name, invocation_id, arguments_summary, ...)` (line 48) — `publish_ep_bound("phase.tool.call.start", ...)`.
  - `commit_tool_phase_call_end(*, tool_name, invocation_id, outcome, ok, latency_ms, ...)` (line 76) — `publish_ep_bound("phase.tool.call.end", ...)`.
  - `commit_tool_phase_denied(*, tool_name, reason, ...)` (line 109) — `publish_ep_bound("phase.tool.denied", ...)`.
  - `commit_body_tool_execute_start(*, tool_name, invocation_id, attempt, ...)` (line 133) — `publish_ep_bound("body.tool.execute.start", ...)`.
  - `commit_body_tool_execute_end(*, tool_name, invocation_id, attempt, outcome, latency_ms, observation, ok, ...)` (line 156) — calls `append_tool_result_surface` via `enrich_ep_payload`.
  - `commit_body_tool_decision_start(*, tool_name, invocation_id, ...)` (line 206) — `publish_ep_bound("body.tool.execute.start", {"wrapper": "decision", ...})`.
  - `commit_body_tool_decision_end(*, tool_name, invocation_id, outcome, ...)` (line 229) — `publish_ep_bound("body.tool.execute.end", {"wrapper": "decision", ...})`.
  - `commit_body_tool_retry(*, tool_name, invocation_id, attempt, reason, ...)` (line 254) — `publish_ep_bound("body.tool.retry", ...)`.
  - `commit_body_sandbox_enter(*, invocation_id, tool_name, ...)` (line 280) — `publish_ep_bound("body.sandbox.enter", ...)`.
  - `commit_body_sandbox_exit(*, invocation_id, tool_name, outcome, ...)` (line 301) — `publish_ep_bound("body.sandbox.exit", ...)`.
- **emits**:
  - `append_catalog_bound` (catalog events: `ToolStartedCommitted`, `ToolInvokedCommitted`, `ToolDeniedCommitted`).
  - `publish_ep_bound` for `phase.tool.call.start`, `phase.tool.call.end`, `phase.tool.denied`, `body.tool.execute.start`, `body.tool.execute.end`, `body.tool.retry`, `body.sandbox.enter`, `body.sandbox.exit`.
  - `append_tool_result_surface` for `SURFACE_TOOL_RESULT_TYPE` (model-visible).
- **via Session.append**: **yes** — all paths go through `publish_ep_bound`/`append_catalog_bound` → `DefaultFactGateway` → `Session.append`. Single-track.
- **owns invocation_id**: **no** — passed in.
- **owns args_digest**: **no** — N/A; only carries `arguments_summary` (passed in).
- **migration status**: **already migrated** — single-track via `DefaultFactGateway`.

### `lca/contracts/observability/cursor/loop_cursor_payloads.py`

- **public dataclasses** (typed payload contracts):
  - `ThinkingRecord` (`lca/contracts/observability/cursor/loop_cursor_payloads.py:26`).
  - `ToolCallRecord` (line 58) — fields: `tool_name`, `call_seq`, `args_digest` (deprecated), `args_payload_path` (deprecated), `arguments`, `arguments_summary`, `invocation_id`.
  - `ToolResultRecord` (line 89) — fields: `tool_name`, `result_digest`, `result_path`, `outcome`, `ok` (mandatory, no default), `invocation_id`, `latency_ms`, `stdout_head`, `stdout_chars_total`, `stdout_truncated`, `stderr`, `files_created`, `error`, `delta_summary`.
  - `RequestHeader` (line 115).
  - `ToolSchema` (line 135) with `to_openai_dict`, `from_openai`, `from_any`, `from_manifest` static methods.
  - `PhaseFoldPayload` (line 240).
- **emits**: **none directly** — pure typed contracts. Consumers (`StdLoopCursor`, `CoordinatorAdapter`) wrap these into spine EPs.
- **via Session.append**: **n/a** (no emit).
- **owns invocation_id**: **no** — field provided by caller.
- **owns args_digest**: **no** — field provided by caller (deprecated; lines 79-82).
- **migration status**: **n/a (type contract)**.

### `lca_kernel/events/fold/binding_engine.py`

- **public class**: `JournalBindingEngine` (`lca_kernel/events/fold/binding_engine.py:99`).
- **public functions**:
  - `extract_from_payload(payload, source)` (line 42).
  - `extract_mapping(payload, rule)` (line 68).
  - `match_rules(rules, execution_point, payload)` (line 79).
  - `merge_strategy_for_rules(rules)` (line 95).
  - `header_model_from_payload(payload)` (line 229).
- **public methods of JournalBindingEngine**:
  - `__init__(plan)` (line 100) — accepts a compiled observability plan.
  - `merge_for_ep(execution_point, payload)` (line 108).
  - `apply_tool_call(existing, payload, execution_point)` (line 112) — returns merged `ToolCallRecord`.
  - `apply_tool_result(existing, payload, execution_point, *, ok_default)` (line 134) — returns merged `ToolResult`; raises `FoldConsistencyError` if `ok=True` and `error` non-empty.
  - `apply_thinking_patch(existing, payload, execution_point, *, frame_model)` (line 177).
- **public class**: `FoldConsistencyError(RuntimeError)` (line 27).
- **emits**: **none directly** — pure fold/binding logic over already-emitted spine payloads. This is a **deriver**, not a producer.
- **via Session.append**: **n/a** (no emit; fold consumes payload from spine).
- **owns invocation_id**: **no** — extracted from payload via `extract_from_payload`.
- **owns args_digest**: **no** — extracted from payload via `extract_from_payload`.
- **migration status**: **n/a (deriver; read-only on spine)**.

---

## Summary

### Findings

The LCA codebase enforces `Session.append` as the sole production entry through **two facades**:

1. **`DefaultFactGateway`** (`lca/loop/fact_gateway.py:115`) — the canonical "single-track" entry for cognition-side durable facts. It exposes three public methods (`append_catalog`, `publish_ep`, `append_surface`), each of which calls `_catalog_session.append(...)` (line 127, 137, 163) — i.e., `Session.append` directly.

2. **`SpineWritePortAdapter`** (`lca/plugins/session/runtime/cursor/port.py:88`) — the WritePort adapter used by `StdLoopCursor` (`lca/infrastructure/observability/loop_cursor/std/std.py:103`) for spine EP emission. When a `RunEventSessionBridge` is wired, this routes through `bridge.append(SpineEventPayload)` (`lca/plugins/session/runtime/cursor/port.py:115`), which then calls `Session.append` (`lca/session/lifecycle/bind.py:120`). Without a bridge, it falls back to `self._session.append(execution_point, data)` (`lca/plugins/session/runtime/cursor/port.py:122`).

Both paths land in `Session.append`. There are **zero raw `spine.publish` / `journal_backend.append` / direct journal-backend mutations** in the cognition or session layers; `journal_backend` is only referenced in **config schema** (`lca/infrastructure/observability/facade/settings/settings.py:76`) — not as a runtime emit site.

### Modules that bypass single-track (second-track via cursor)

**Total modules still on the cursor / WritePort track (not yet unified to `DefaultFactGateway`):**

| Module | Lines | Status |
|---|---|---|
| `lca/cognition/body/emit/tool_journal.py` | 134, 201, 300 | partial — diagnostic via single-track; cursor calls via second-track |
| `lca/cognition/body/executor/cursor_record.py` | 93, 156 | second-track (sole purpose: cursor) |
| `lca/cognition/body/executor/safe_executor.py` | 266, 318, 334, 550, 586 | partial — body commits via single-track; cursor calls via second-track |
| `lca/cognition/body/executor/pipeline_safe_executor.py` | 312, 339, 359, 369 | partial — body commits via single-track; cursor calls via second-track |
| `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py` | 192, 216, 246 | second-track (adapter for cursor) |
| `lca/infrastructure/observability/loop_cursor/std/std.py` | 308, 333, 361 (via `_append`) | second-track (cursor core) |

### Modules already on single-track (already migrated)

| Module | Mechanism |
|---|---|
| `lca/loop/commit/tool_journal.py` | `publish_ep_bound` / `append_catalog_bound` → `DefaultFactGateway` |
| `lca/loop/commit/act_journal.py` | `append_catalog_bound` → `DefaultFactGateway` |
| `lca/infrastructure/session/emit/tool_surface_emit.py` | `append_surface_bound` → `DefaultFactGateway` |
| `lca/infrastructure/session/emit/surface_emit.py` | `append_surface_bound` → `DefaultFactGateway` |
| `lca/infrastructure/session/emit/cognitive_emit.py` | `append_catalog_bound` / `publish_ep_bound` → `DefaultFactGateway` |
| `lca/infrastructure/session/emit/runtime_emit.py` | `publish_ep_bound` → `DefaultFactGateway` |
| `lca/infrastructure/session/emit/lifecycle_emit.py` | `append_catalog_bound` / `append_surface_bound` → `DefaultFactGateway` |
| `lca/infrastructure/session/emit/convergence_emit.py` | `append_catalog_bound` → `DefaultFactGateway` |
| `lca/infrastructure/session/commit/fact_committer.py` | `append_catalog_bound` / `publish_ep_bound` → `DefaultFactGateway` |
| `lca/infrastructure/session/commit/spine_envelope.py` | `publish_ep_bound` → `DefaultFactGateway` |
| `lca/infrastructure/observability/spine/exception/emit.py` | `publish_ep_bound` → `DefaultFactGateway` |
| `lca/infrastructure/observability/meta_event_emit.py` | `append_catalog_bound` / `publish_ep_bound` → `DefaultFactGateway` |
| `lca/infrastructure/observability/domain_event_publish.py` | `publish_ep_bound` → `DefaultFactGateway` |
| `lca/loop/commit/phase_spine.py` | `publish_ep_bound` → `DefaultFactGateway` |
| `lca/loop/commit/memory_journal.py` | `append_catalog_bound` / `publish_ep_bound` → `DefaultFactGateway` |
| `lca/loop/commit/delegation_journal.py` | `publish_ep_bound` → `DefaultFactGateway` |
| `lca/loop/emit/spine/ep.py` | `publish_ep_bound` → `DefaultFactGateway` |
| `lca/loop/emit/cognitive/reasoner.py` | `publish_ep_bound` → `DefaultFactGateway` |

### Counts

- **total direct emit sites** (cursor-track calls): **20** — across 6 modules
  - `lca/cognition/body/executor/cursor_record.py`: 2 (lines 93, 156)
  - `lca/cognition/body/emit/tool_journal.py`: 3 (lines 134, 201, 300)
  - `lca/cognition/body/executor/safe_executor.py`: 5 (lines 266, 318, 334, 550, 586)
  - `lca/cognition/body/executor/pipeline_safe_executor.py`: 4 (lines 312, 339, 359, 369)
  - `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py`: 3 (lines 192, 216, 246)
  - `lca/infrastructure/observability/loop_cursor/std/std.py`: 3 (lines 308, 333, 361)
- **total modules violating single-track** (still on cursor/WritePort second-track): **6**
- **modules that need conversion to `Session.append` narrow wrapper**: **0** (every cursor call ultimately lands in `Session.append` via the bridge/WritePort path; the question is whether the **business path** should be migrated from `CursorRecord.try_record_*` to direct `publish_ep_bound` / a `Session.append` narrow wrapper).

The COMPAT delete-when block at `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:34-41` and the docstring of `CursorRecord` (lines 7-15 of `cursor_record.py`) document that business-path migration to `Session.append` direct (narrow wrapper) is the open migration:

> "**2026-09-03 观测面 SSOT 收口**(根 note `observation-ssot-registry`)"

The 6 modules listed above (`tool_journal.py`, `cursor_record.py`, `safe_executor.py`, `pipeline_safe_executor.py`, `coordinator/adapter.py`, `std/std.py`) are the migration targets; the unification plan collapses `CursorRecord.try_record_*` calls into a single `Session.append` narrow wrapper that produces `spine.step.tool_call.record` / `spine.step.tool_result.record` EPs directly.

### `invocation_id` ownership (current state)

| Module | Owns invocation_id? | Where |
|---|---|---|
| `lca/cognition/body/executor/safe_executor.py` | **yes** | `lca/cognition/body/executor/safe_executor.py:257` (`new_id("inv")`) |
| `lca/cognition/body/executor/pipeline_safe_executor.py` | **yes** | `lca/cognition/body/executor/pipeline_safe_executor.py:249` (`new_id("inv")`) |
| `lca/cognition/body/emit/tool_journal.py` | **no** — passes through | — |
| `lca/cognition/body/executor/cursor_record.py` | **no** — passes through | — |
| `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py` | **no** — pulled from `LegacyToolCallRecord.invocation_id` (line 207) | — |
| `lca/contracts/observability/cursor/loop_cursor_payloads.py` | **no** — field in `ToolCallRecord` / `ToolResultRecord` (lines 86, 107) | — |
| `lca/infrastructure/session/emit/tool_surface_emit.py` | **no** — passed in | — |
| `lca/infrastructure/session/projections/tool_result_message.py` | **no** — passed in | — |
| `lca/loop/commit/tool_journal.py` | **no** — passed in | — |
| `lca_kernel/events/fold/binding_engine.py` | **no** — extracted from payload | — |

### `args_digest` ownership (current state)

| Module | Owns args_digest? | Where |
|---|---|---|
| `lca/cognition/body/emit/tool_journal.py` | **yes** | `_summarize_args` at line 177 (called at line 137) |
| `lca/cognition/body/executor/safe_executor.py` | **partial** — only `f"tool:{tool.name}"` placeholder at lines 269, 553 (also has `_summarize_args_for_cursor` at line 47 for `arguments_summary`) | — |
| `lca/cognition/body/executor/pipeline_safe_executor.py` | **partial** — `f"tool:{tool.name}"` placeholder at line 315 | — |
| `lca/cognition/body/executor/cursor_record.py` | **no** — passes through | — |
| `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py` | **yes** — `sha256_digest(...)` helper at line 72 (used at lines 187, 217, 248) | — |
| `lca/contracts/observability/cursor/loop_cursor_payloads.py` | **no** — field in `ToolCallRecord` (line 79, deprecated) | — |
| `lca/infrastructure/session/emit/tool_surface_emit.py` | **no** — N/A for surface node | — |
| `lca/infrastructure/session/projections/tool_result_message.py` | **no** — N/A | — |
| `lca/loop/commit/tool_journal.py` | **no** — only carries `arguments_summary` (not `args_digest`) | — |
| `lca_kernel/events/fold/binding_engine.py` | **no** — extracted from payload | — |

**Two implementations of `args_digest`-like computation exist today:**
- `lca/cognition/body/emit/tool_journal.py:177` — `_summarize_args` (plain text 200-char summary, NOT a digest).
- `lca/cognition/body/executor/safe_executor.py:47` — `_summarize_args_for_cursor` (separate copy of `_summarize_args`).
- `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:72` — `sha256_digest` (real SHA256 digest).

Three distinct semantics (`f"tool:{tool.name}"`, `_summarize_args` text, `sha256_digest`) co-exist as `args_digest` producers across `safe_executor.py:269`, `safe_executor.py:553`, `pipeline_safe_executor.py:315`, `tool_journal.py:137`, `coordinator/adapter.py:217`.

### Migration status overall

- **Single-track (already migrated)** — `lca/loop/commit/tool_journal.py`, `lca/loop/commit/act_journal.py`, all of `lca/infrastructure/session/emit/`, `lca/infrastructure/observability/*` (excluding `loop_cursor/`), `lca/infrastructure/session/commit/fact_committer.py`.
- **Partial / dual-track** — `lca/cognition/body/executor/safe_executor.py`, `lca/cognition/body/executor/pipeline_safe_executor.py`, `lca/cognition/body/emit/tool_journal.py`.
- **Second-track only (violating single-track)** — `lca/cognition/body/executor/cursor_record.py`, `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py`, `lca/infrastructure/observability/loop_cursor/std/std.py`.

The migration target is to convert the **20 direct cursor-track emit sites** (the second-track calls) to a `Session.append` narrow wrapper (likely a `tool_journal_fact` or `step.tool_call.record` / `step.tool_result.record` typed catalog helper exposed by `lca/infrastructure/session/emit/`), at which point `CursorRecord`, `CoordinatorAdapter`, and the `StdLoopCursor` record_* methods can be retired (with the COMPAT delete-when gates in `coordinator/adapter.py:34-41` cleared).