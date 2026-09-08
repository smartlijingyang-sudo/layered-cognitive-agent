# Survey: args_digest Inconsistency

Survey of digest / fingerprint computation sites in `lca/` that feed the
`step.tool_call.record` EP and the cursor `ToolCallRecord` payload. All
paths are read-only inspection of the source tree; no edits.

## Hash sites

| file:line | function | input | normalization | algo | public? |
|---|---|---|---|---|---|
| `lca/cognition/body/executor/safe_executor.py:269` | inline in `SimpleSafeExecutor.execute` | `tool.name` (string) | none — `f"tool:{tool.name}"` literal | none (label, not a hash) | no (inline) |
| `lca/cognition/body/executor/safe_executor.py:553` | `_record_tool_call_evidence` | `tool_name` (string) | none — `f"tool:{tool_name}"` literal | none (label) | no (helper) |
| `lca/cognition/body/executor/pipeline_safe_executor.py:315` | inline in `PipelineSafeExecutor.execute` | `tool.name` (string) | none — `f"tool:{tool.name}"` literal | none (label) | no (inline) |
| `lca/cognition/body/emit/tool_journal.py:137` | inline in `record_tool_started_observability` → calls `_summarize_args` (lines 177–186) | `args` dict (first 5 keys, `repr` per value, truncated to 32 chars each) | none — human-readable summary string | none (label) | `_summarize_args` is module-private (`_` prefix) |
| `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:219` | `CoordinatorAdapter.record_tool_call` → `sha256_digest` (lines 72–85) | `{"args": args_summary, "invocation_id": invocation_id}` | `json.dumps(..., sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")` | `sha256` (full 64 hex) + `"sha256:"` prefix | `sha256_digest` is module-public |
| `lca/plugins/domain/assistant/_home_layout.py:121` | `sha256_digest(path)` | file bytes (streamed, 64 KiB chunks) | none (raw bytes) | `sha256` (full 64 hex) + `"sha256:"` prefix | public (re-exported in `__all__` line 40) |
| `lca/plugins/assistant/home/_home_layout.py:121` | duplicate of above | file bytes | none | `sha256` + `"sha256:"` prefix | public |
| `lca/cognition/brain/decision_gates/loop/fingerprint.py:43` | `_fingerprint_payload` (via `sha256`) | canonical JSON of payload | `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` (line 42) | `sha256` (full hex, no prefix) | module-private |
| `lca/contracts/runtime/plan_proposal.py:165` | inline digest for plan proposal | canonical JSON of payload | `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` (line 164) | `sha256` (full hex, no prefix) | module-private (free function) |
| `lca/harness/plan.py:39, 55` | `_hash_plan_digest`, `_hash_run_digest` | canonical JSON of value/payload | `canonical_json(value)` then `sha256` | `sha256` truncated to 32 / 16 hex chars | module-private |
| `lca/cognition/brain/prompt/surface.py:46` | inline | bytes payload | none | `sha256` truncated to 16 hex | module-private |
| `lca/cognition/brain/pipeline/context_manifest.py:29` | inline | UTF-8 string | none | `sha256` truncated to 16 hex | module-private |
| `lca/harness/skills/service.py:245` | inline | canonical JSON of dataclass list | `json.dumps(..., sort_keys=True, ensure_ascii=True)` | `sha256` (full hex) | module-private |
| `lca/cognition/sensors/skill_catalog.py:26` | inline | canonical JSON of dataclass list | `json.dumps(..., sort_keys=True, ensure_ascii=True)` | `sha256` (full hex) | module-private |
| `lca/cognition/memory/semantic/compaction.py:174` | inline | `"\0".join(source_ids).encode("utf-8")` | none | `sha256` truncated to 16 hex | module-private |
| `lca/harness/declarative/compile/instrument/wrap.py:196–197` | inline | rendered string | none | `sha256` truncated to 16 hex + `"sha256:"` prefix | module-private |
| `lca/plugins/observability/spine/derivers/anomaly.py:66, 85` | inline | bytes payload | none | `sha256` (full hex) + `"sha256:"` prefix | module-private |
| `lca/harness/diagnostics/normalizer/normalizer.py:14` | inline | `repr(value).encode("utf-8")` | none | `sha256` truncated to 16 hex | module-private |
| `lca/harness/runtime/activation_ref.py:41` | inline | canonical string | `canonical.encode("utf-8")` | `sha256` (full hex) + `<namespace>:` prefix | module-private |
| `lca/harness/profile/resolve/resolve.py:104` | inline | bytes | none | `sha256` | module-private |
| `lca/plugins/session/runtime/spine/hook.py:86, 88` | inline | UTF-8 string | none | `sha256` (full hex) + `"sha256:"` prefix | module-private |
| `lca/plugins/events/hooks/model_visible/hook.py:88–108` | `_sha256_hex` / `_canonical_header_digest` | canonical encoded bytes | canonical encoder (line 108) | `sha256` (full hex) + `"sha256:"` prefix | module-private (helpers) |
| `lca/plugins/transport/device_hub/auth/auth.py:59` | inline | signing input | HMAC | `hmac.new(..., hashlib.sha256).digest()` | module-private |
| `lca/plugins/learning/review_service.py:262` | inline | event_key UTF-8 | none | `sha256` truncated to 16 hex | module-private |
| `lca/plugins/transport/webserver/handlers/runs/ingest/integrity/integrity.py:28` | inline | content bytes | none | `sha256` (full hex) | module-private |
| `lca/infrastructure/skills/disk/store.py:37` | inline | data bytes | none | `sha256` (full hex) | module-private |
| `lca/plugins/skill/auto_acquire.py:63` | inline | `f"{task_ref}\0{procedure}\0{'|'.join(evidence_refs)}".encode()` | none | `sha256` truncated to 16 hex | module-private |
| `lca/plugins/transport/webserver/handlers/runs/session/builder/builder.py:93` | inline | UTF-8 string | none | `sha256` truncated to 16 hex | module-private |
| `lca/plugins/assistant/evolve/evolve.py:411, 445` | inline | UTF-8 string | none | `sha256` (full hex) + `"sha256:"` prefix | module-private |
| `lca/plugins/transport/webserver/handlers/runs/session/index/index.py:42` | inline | payload bytes | none | `sha256` truncated to 24 hex | module-private |
| `lca/plugins/assistant/skill/overlay.py:221–223, 512` | inline | content hash | none | `sha256` (full hex) + `"sha256:"` prefix | module-private |
| `lca/infrastructure/observability/journal/engine/journal_io.py:82` | inline | material bytes | none | `sha256` truncated to 24 hex + `"evt_"` prefix | module-private |
| `lca/contracts/protocols/perceive/capability_plan.py:135` | inline | UTF-8 blob | none | `sha256` truncated to 16 hex | module-private |
| `lca/contracts/protocols/state/scope_plan.py:131` | inline | UTF-8 blob | none | `sha256` truncated to 16 hex | module-private |
| `lca/contracts/harness/journal/artifact.py:135` | inline | content bytes | none | `sha256` truncated to 16 hex | module-private |
| `lca/infrastructure/sandbox/runtime/runtime.py:67` | inline | data bytes | none | `sha256` (full hex) | module-private |
| `lca/infrastructure/computer/machine/exec.py:56` | inline | `f"{code}:{time.monotonic()}".encode()` | none | `sha256` truncated to 12 hex | module-private |
| `lca/infrastructure/computer/machine/harvest.py:101` | inline | data bytes | none | `sha256` (full hex) | module-private |
| `lca/infrastructure/state_store/sqlite_store.py:45, 80` | inline | payload bytes | none | `sha256` (full hex) | module-private |
| `lca/contracts/mechanisms/content/addressable.py:44` | inline | payload bytes | none | `sha256` (full hex) | module-private |
| `lca/infrastructure/observability/spine/sinks/file_sink.py:81` | inline | encoded bytes | none | `sha256` (full hex) | module-private |
| `lca/infrastructure/observability/loop_cursor/replay/fold_source.py:119` | `_canonical_digest` | encoded bytes | canonical encoder | `sha256` (full hex) + `"sha256:"` prefix | module-private |
| `lca/infrastructure/observability/meta_event_emit.py:88` | inline | UTF-8 body | none | `sha256` (full hex) + `"sha256:"` prefix | module-private |
| `lca/cognition/brain/reasoner/reasoner.py:54, 237` | inline (uses `sha256_digest` from elsewhere) | reasoning text | n/a | passes through to a `sha256_digest` re-export | module-private |
| `lca/contracts/protocols/assistant/skill_overlay.py:97` | protocol declaration | n/a | n/a | `sha256` + `"sha256:"` prefix | public protocol contract |

## Per-module digest computation

### `lca/cognition/body/executor/safe_executor.py`
- algorithm: no hash; literal label string
- input fields: `tool.name` only
- normalization: `f"tool:{tool.name}"` (line 269) and `f"tool:{tool_name}"` (line 553)
- length / format: variable, e.g. `"tool:activate_skill"` (20 chars)
- calls any shared utility: **no**

### `lca/cognition/body/executor/pipeline_safe_executor.py`
- algorithm: no hash; literal label string
- input fields: `tool.name` only
- normalization: `f"tool:{tool.name}"` (line 315)
- length / format: same as above
- calls any shared utility: **no**

### `lca/cognition/body/emit/tool_journal.py`
- algorithm: no hash; this is `_summarize_args` masquerading as a digest value
- input fields: `args_dict` keys (first 5) with `repr(value)[:32]` per value
- normalization: `", ".join(...)` then truncate to 200 chars + `"…"` (lines 177–186)
- length / format: ≤ 201 chars, e.g. `"skill_id='anthropics-skills-pdf'"` (35 chars)
- calls any shared utility: **no** (the comment on `cursor_record.py:79` and `safe_executor.py:50–53` acknowledges `_summarize_args` is duplicated in two modules with the same semantics; both are module-private)
- caller pattern at line 137 passes `_summarize_args(args_dict)` as the `args_digest` kwarg of `CursorRecord.try_record_tool_call`

### `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py`
- algorithm: `sha256` hex digest, full 64 chars, `"sha256:"` prefix
- input fields: `{"args": args_summary, "invocation_id": invocation_id}` (line 219)
- normalization: `json.dumps(..., sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")` (lines 78–83)
- length / format: `"sha256:"` + 64 hex = 71 chars
- calls any shared utility: **yes** — its own module-level `sha256_digest(payload)` (lines 72–85), described in the docstring as "ADR-0185 PR-4 收口后为 `sha256:<hex>` digest 形态的唯一实现" (the sole canonical implementation of the `sha256:<hex>` form after PR-4)
- note: this is a compat adapter for the legacy `StepCoordinator` `record_tool_call` path; **not** on the cursor hot path that `CursorRecord` feeds into `StdLoopCursor.record_tool_call` (which receives `args_digest` already computed upstream)

### `lca/infrastructure/observability/loop_cursor/std/std.py` (`StdLoopCursor.record_tool_call`)
- algorithm: pass-through; the cursor does not compute `args_digest` itself
- input fields: whatever the caller passed in `ToolCallRecord.args_digest`
- normalization: none — see lines 343–359; the cursor copies `payload.args_digest` straight into the event payload
- length / format: caller-defined
- calls any shared utility: **no**

### `lca/cognition/body/executor/cursor_record.py`
- algorithm: pass-through wrapper
- input fields: `args_digest: str` (kwarg, line 72) and `call_seq = hash(invocation_id) & 0x7FFFFFFF` (line 99)
- normalization: none
- length / format: caller-defined
- calls any shared utility: **no** (just hands the kwarg to `ToolCallRecord(args_digest=...)` on line 95)

### `lca/loop/commit/tool_journal.py`
- algorithm: pass-through; commits only catalog / surface / spine EP
- input fields: `tool_name`, `invocation_id`, `arguments_summary` (no digest field on `phase.tool.call.start`)
- normalization: none — see `commit_tool_phase_call_start` (lines 49–73)
- calls any shared utility: **no**

### `lca/plugins/domain/assistant/_home_layout.py` / `lca/plugins/assistant/home/_home_layout.py`
- algorithm: `sha256` (full 64 hex) + `"sha256:"` prefix (line 122 returns `f"sha256:{h.hexdigest()}"`)
- input fields: file bytes streamed at 64 KiB chunks
- normalization: none (raw bytes)
- length / format: 71 chars
- calls any shared utility: **no** — both files define their own `sha256_digest(path)`. They are byte-for-byte duplicates (verified: identical signatures at lines 121 of both files)

### Other digest sites
All other rows in the table above operate on data that does **not** flow into `step.tool_call.record`. They are cataloged for completeness only — see "Notes" below.

## Comparison table

For each pair of modules computing `args_digest` on the tool-call path, do they agree?

- `safe_executor.py:269` (inline `f"tool:{tool.name}"`) **vs** `safe_executor.py:553` (`_record_tool_call_evidence`): **same** — both produce `f"tool:{tool_name}"`. But they emit from different call sites; only `:269` is on the hot path during a normal `execute()`.
- `safe_executor.py:269` **vs** `pipeline_safe_executor.py:315`: **same algorithm**, **same input** (just `tool.name`), **same output** — `f"tool:{tool.name}"`. The two executors agree with each other.
- `safe_executor.py:269` **vs** `tool_journal.py:137` (via `_summarize_args`): **different**. safe_executor writes `"tool:activate_skill"` (label of tool name only); tool_journal writes `"skill_id='anthropics-skills-pdf'"` (human-readable summary of `args`). They are also produced by two **separate** emit sites both routed through `CursorRecord.try_record_tool_call` → `cursor.record_tool_call` → `step.tool_call.record` EP. Both reach the spine; both appear in the same run's `run_*.spine.jsonl`.
- `tool_journal.py:137` (summary string) **vs** `loop_cursor/coordinator/adapter.py:219` (`sha256:<hex>` of `{args, invocation_id}`): **different**. Different algorithms (label vs hash), different inputs, different output formats.
- `loop_cursor/coordinator/adapter.py:219` **vs** `loop_cursor/std/std.py:343` (pass-through): the std cursor does not compute; it copies whatever the caller passed. The adapter is **only** invoked from legacy `StepCoordinator.record_tool_call` paths (see compat header lines 6–32); the canonical cursor write path is `CursorRecord → StdLoopCursor.record_tool_call`.

### What the trace actually shows

For `run_2910e20390f9` (file `traces/runs/run_2910e20390f9/run_2910e20390f9.spine.jsonl`), three pairs of consecutive `step.tool_call.record` events exist (events `:90/:92`, `:198/:200`, `:307/:309`):

```
event :90  ts ...01.191  args_digest = "tool:activate_skill"           (safe_executor path)
event :92  ts ...01.192  args_digest = "skill_id='anthropics-skills-pdf'" (tool_journal path)
event :198 ts ...03.490  args_digest = "tool:activate_skill"
event :200 ts ...03.490  args_digest = "skill_id='anthropics-skills-pdf'"
event :307 ts ...06.255  args_digest = "tool:activate_skill"
event :309 ts ...06.255  args_digest = "skill_id='anthropics-skills-pdf'"
```

The two emits occur 0.3 ms apart with identical `invocation_id` and `call_seq`. Identical `arguments` and `arguments_summary` payloads; only `args_digest` differs. This is the C3 fingerprint inconsistency the task describes.

## Existing shared digest utility (if any)

- **Candidate 1**: `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:72` — `sha256_digest(payload: Any) -> str`
  - signature: `def sha256_digest(payload: Any) -> str:` returning `"sha256:" + sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()`
  - docstring (lines 73–82) declares it "ADR-0185 PR-4 收口后为 `sha256:<hex>` digest 形态的唯一实现"
  - callers (within `lca/`):
    - `CoordinatorAdapter.record_thinking` at line 194 (`content_digest`)
    - `CoordinatorAdapter.record_tool_call` at line 219 (`args_digest`)
    - `CoordinatorAdapter.record_tool_result` at line 249 (`result_digest`)
  - **note**: callers live in the same file and the helper is not imported by the body / executor modules (`CursorRecord`, `safe_executor.py`, `pipeline_safe_executor.py`, `tool_journal.py`) — confirmed by negative grep for `sha256_digest` in those files (no matches outside `loop_cursor/coordinator/adapter.py` and the unrelated `_home_layout.py` file-content digest).

- **Candidate 2**: `lca/plugins/domain/assistant/_home_layout.py:121` and the duplicate `lca/plugins/assistant/home/_home_layout.py:121`
  - signature: `def sha256_digest(path: Path) -> str:`
  - same return form `"sha256:" + full hex`
  - operates on file bytes (different domain: home manifest files). Despite identical name, this is a **different function** (input is `Path`, not `Any`).

- **Candidate 3**: `lca/cognition/brain/decision_gates/loop/fingerprint.py:43` `_fingerprint_payload`
  - signature: returns full sha256 hex (no `"sha256:"` prefix)
  - canonical JSON normalization with `(",", ":")` separators
  - not imported by any other module (no cross-module callers)

- **Candidate 4**: `lca/infrastructure/observability/loop_cursor/replay/fold_source.py:119` `_canonical_digest`
  - signature: returns `"sha256:" + sha256(encoded).hexdigest()`
  - canonical encoder is local to that file
  - module-private (`_` prefix)

There is **no shared utility for tool-arg digesting** that the body / executor layer uses. The body modules that emit `args_digest` for `step.tool_call.record` either invent their own label literal (`f"tool:{tool.name}"`) or substitute a human-readable summary string (`_summarize_args`). The one helper that *would* be the canonical `sha256:<hex>` computation (`loop_cursor/coordinator/adapter.py:72`) is not on the same call path as `CursorRecord.try_record_tool_call` — that adapter only fires from the legacy `StepCoordinator` compat path (see the COMPAT block at lines 6–32 and 88–92 of that file).

## Notes on the broader digest inventory

- **No two modules agree** on the right normalization / length:
  - full 64 hex, `"sha256:"` prefix: `_home_layout.py:121`, `loop_cursor/coordinator/adapter.py:72`, `loop_cursor/replay/fold_source.py:119`, `meta_event_emit.py:88`, `model_visible/hook.py:88`, `evolve.py:411/445`, `anomaly.py:66`, `plugin.py:402` (delegates to `_home_layout`)
  - full 64 hex, no prefix: `plan_proposal.py:165`, `fold_source.py:119` (via prefix), `decision_gates/loop/fingerprint.py:43`, `service.py:245`, `skill_catalog.py:26`, `webserver/handlers/.../integrity.py:28`, `skills/disk/store.py:37`, `state_store/sqlite_store.py:45`, `sandbox/runtime.py:67`, `harvest.py:101`, `content/addressable.py:44`, `file_sink.py:81`, `runtime.py:67`
  - truncated 32 hex: `harness/plan.py:39`
  - truncated 24 hex: `webserver/.../session/index/index.py:42`, `journal/engine/journal_io.py:82` (with `"evt_"` prefix instead of `"sha256:"`)
  - truncated 16 hex: `brain/prompt/surface.py:46`, `brain/pipeline/context_manifest.py:29`, `memory/.../compaction.py:174`, `harness/plan.py:55`, `diagnostics/normalizer/normalizer.py:14`, `wrap.py:197`, `builder/builder.py:93`, `state.py:183`, `review_service.py:262`, `auto_acquire.py:63`, `journal/artifact.py:135`, `capability_plan.py:135`, `scope_plan.py:131`
  - truncated 12 hex: `computer/machine/exec.py:56`
  - non-hash label: `safe_executor.py:269, 553`, `pipeline_safe_executor.py:315`
  - non-hash summary masquerading as digest: `tool_journal.py:137` (via `_summarize_args`)
- Most digests are inline at the call site. None of the 40+ digest sites above centralize through one public helper.
- The `loop_cursor/coordinator/adapter.py:72` helper is the closest thing to a designated SSOT for `sha256:<hex>` payload digests, but its visibility scope is limited to the legacy `StepCoordinator` bridge, not the body / executor layer.

## Recommendation (factual, no proposal)

- distinct algorithms found: **at least 5 distinct "digest" shapes** flow into the `step.tool_call.record` event path:
  1. `"tool:<tool_name>"` literal — produced at `safe_executor.py:269`, `safe_executor.py:553`, `pipeline_safe_executor.py:315`.
  2. Human-readable summary string — produced at `tool_journal.py:137` (via `_summarize_args`).
  3. `"sha256:<hex>"` of `{args: summary, invocation_id: ...}` — produced at `loop_cursor/coordinator/adapter.py:219` (legacy compat path only).
  4. The full payload dict `arguments` — passed through `CursorRecord.try_record_tool_call` (`cursor_record.py:73–108`) without hashing, as the new "rich arguments" field per the 2026-09-03 SSOT 收口 comment on `cursor_record.py:27–36`.
  5. Caller-supplied `arguments_summary: str` — same path, passed through verbatim to `ToolCallRecord.arguments_summary`.
- the two algorithms seen in run_2910e20390f9 are computed at:
  - `"tool:activate_skill"` → `lca/cognition/body/executor/safe_executor.py:269` (and its mirror at `pipeline_safe_executor.py:315`).
  - `"skill_id='anthropics-skills-pdf'"` → `lca/cognition/body/emit/tool_journal.py:137`, via the module-private helper `_summarize_args` defined at `tool_journal.py:177–186`.
- to unify, callers should reference:
  - the canonical `sha256_digest(payload)` at `lca/infrastructure/observability/loop_cursor/coordinator/adapter.py:72–85` — currently the only function in the codebase whose docstring explicitly claims to be the canonical `sha256:<hex>` digest form. Importing it from body / executor modules is not currently done; verified by negative grep across `lca/cognition/body/**` and `lca/contracts/**`. Its domain (`sha256` of canonical JSON) is the algorithm used at `loop_cursor/coordinator/adapter.py:219` and is consistent with the broader repo convention for "content digests" emitted on the spine (see `meta_event_emit.py:88`, `fold_source.py:119`, `anomaly.py:85`, `model_visible/hook.py:88`, `_home_layout.py:127`).
  - alternatively, treat the `arguments` and `arguments_summary` fields already present on `step.tool_call.record` (per `loop_cursor_payloads.py:78–87` and `std.py:347–358`) as the canonical human-readable replacement for any `args_digest` value, matching the docstring deprecation note at `loop_cursor_payloads.py:63–73` ("deprecated(ADR-0185 spec §2.5 P5); delete-when: 下个 minor 版本,或所有 caller 迁完").

## Session.append canonical invocation pattern for `step.tool_call.record`

The canonical producer chain for a `step.tool_call.record` EP is:

1. Caller builds a frozen `ToolCallRecord` dataclass — see `lca/contracts/observability/cursor/loop_cursor_payloads.py:77–87`. Required fields: `tool_name: str`, `call_seq: int`. Optional rich fields: `arguments: dict | None`, `arguments_summary: str = ""`, `invocation_id: str = ""`. Compat-only fields (deprecated, slated for deletion per ADR-0185 §2.5 P5): `args_digest: str = ""`, `args_payload_path: str | None = None`.
2. Caller invokes `CursorRecord.try_record_tool_call(...)` — see `lca/cognition/body/executor/cursor_record.py:68–115`. Pass `tool_name`, `invocation_id`, `args_digest`, optionally `arguments` and `arguments_summary`.
3. `CursorRecord.try_record_tool_call` resolves the bound cursor via `get_current_cursor()` (`cursor_record.py:40–43` → `loop_cursor/coordinator/adapter.py:94–97`) and calls `cursor.record_tool_call(ToolCallRecord(...))` (line 93).
4. `StdLoopCursor.record_tool_call` (`lca/infrastructure/observability/loop_cursor/std/std.py:333–360`) writes the spine EP `step.tool_call.record` via `self._append(execution_point="step.tool_call.record", payload=event_payload)`.
5. The payload published on the spine (`std.py:344–359`) is the flat dict:
   ```
   {
     "tool_name": payload.tool_name,                     # required
     "args_digest": payload.args_digest,                 # compat, deprecated
     "args_payload_path": payload.args_payload_path,     # compat, deprecated
     "call_seq": payload.call_seq,                       # required
     "incarnation": self._state.incarnation.incarnation_seq,
     "plan_ref": self._state.incarnation.plan_ref,
     "step_index": self._state.step_index,
     "arguments": payload.arguments,                     # when not None
     "arguments_summary": payload.arguments_summary,     # when truthy
     "invocation_id": payload.invocation_id,             # when truthy
   }
   ```
6. The EP then routes through `FactGateway.publish_ep` → `Session.append(...)`. The writer side is `lca/loop/fact_gateway.py:149–164` (`DefaultFactGateway.publish_ep`); on the bus facade / bridge path it calls `publish_writer.append(spine, producer=...)` (line 159), otherwise it falls back to `self._catalog_session.append(spine.category.value, data, actor=actor)` (line 162). The catalog-session writer is unwrapped from the publish writer via `_catalog_session_for` (`fact_gateway.py:104–111`).

Required fields on the payload for `step.tool_call.record` (per `loop_cursor_payloads.py:77–87` and `std.py:344–359`): `tool_name` and `call_seq`. Everything else is optional or compat-only.

The two redundant emit sites (safe_executor at line 269 and tool_journal at line 137) both pass through `CursorRecord.try_record_tool_call`, so a single fix point exists at that wrapper if the goal is to make both sites agree on a digest algorithm.
