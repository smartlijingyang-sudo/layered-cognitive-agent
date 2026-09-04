# DSH Alignment Remaining Gap Audit (excl. PR-4 in-flight)

Status: read-only audit, 2026-09-04.
Scope: gap between LCA current state and deepseek-harness alignment targets
on the ADR-0183 / 0184 / 0185 lineage. PR-4 deletion work (ADR-0185 PR-4
bypass-file removal) is in flight elsewhere and excluded from this audit.

## 0. Methodology

For each candidate gap:

- Source ADRs / Notes (ADR-0183, ADR-0184, ADR-0185 + notes
  `2026-09-03-{1,2,3,4}-*` and `2026-09-04-{model-visible-bus-alignment,
  plugin-universe-single-entry, pr8-skip}`) state the target.
- Repo evidence (`rg`, file reads) shows the current landing status.
- DSH alignment target names the reference point
  (`deepseek-harness/packages/core/session/src/request-header.ts`,
  `.../agent-loop/src/agent.ts:498-517`, `session-persistence-jsonl/...`,
  `SessionEventMap` discriminated union).
- Priority / parallel / PR-4 dependency columns drive the action plan.

## 1. Status of referenced ADR-PR matrix (already landed vs remaining)

| ADR | Title | PRs landed | PRs remaining |
|---|---|---|---|
| ADR-0183 | event bus framework + SSOT | PR-1 ~ PR-12 (Accepted, 12-PR sequence merged) | None in flight |
| ADR-0184 | event lifecycle managed delivery | PR-A (counters / EventRef.persisted / `events-delivery` / NotificationBus.sync), PR-B (xfail regression lock in `tests/scenarios/test_event_delivery_e2e.py`) | PR-C (apply_pipeline boot switch + I1 assembly + shared write instance + `strict=True` flip), PR-D (cursor → bus entry), PR-E (writable.step.* explicit contract + window_signal), PR-F (EmitPipeline follow-up) |
| ADR-0185 | model-visible event-bus alignment | PR-0 (fold module `lca_kernel/events/fold.py`), PR-1 (typed payload + yaml registered), PR-2 (publisher plugin + hook implemented), PR-3 (fold path wired into `StandardCursor` + `fold_source.py` + `ModelVisibleFoldSource`) | PR-3.1 (handlers / `lca-ops` / webserver trajectory migration to fold — **not done**), PR-4 (bypass-file deletion — in flight elsewhere, excluded) |

## 2. Gap table (priority / parallel / PR-4 dependency)

| # | Gap | DSH alignment target | Priority | Parallel? | Depends on PR-4? | Evidence / repo pointers |
|---|---|---|---|---|---|---|
| G1 | **PR-3.1 handler migration**: webserver trajectory / `lca-ops explain` / doctor `tool_schema_count` still hit `<run_dir>/model_visible/*.json`; only `StandardCursor.at()` uses `fold_source`. | dsh `requestHeader()` rebuilt purely from session log via `foldRequestHeader`; UI / semantic-inspect layers never touch filesystem. | **P0** — PR-3 already merged the fold path; leaving two parallel paths is the worst shape (dual SSOT in practice). | Yes with G2/G3; partial overlap with G5. | Yes for cleanup; fold-preferred path can ship independently. | `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py:177-189` reads `<run_dir>/model_visible/…/tools.json`; `lca/plugins/transport/webserver/handlers/runs/doctor/models.py:119` `tool_schema_count` field still hardcodes sidecar; `rg "fold_model_visible\|foldRequestHeader" lca/plugins/transport` returns 0; `lca/infrastructure/cli/commands/journal_step.py:14` docstring still says "PR-3: 路径优先 spine, 回退 model_visible/" — implementation not migrated. |
| G2 | **`FsyncProtocol` not in `lca/contracts/observability/ssot.py`**: worker-side `FsyncPolicy` lives at `lca_kernel/events/persistence.py:46` (private enum); FileSink still has 3 fds with implicit fsync semantics; `_FORCE_OFFLOAD_EPS` + sidecar label still in `lca/infrastructure/observability/spine/sinks/file_sink.py`; `TracingFileSink._fallback_fd` no fsync. | dsh `session-persistence-jsonl/src/index.ts` calls `handle.sync()` (fsync) per write, with `truncate(before)` rollback; dsh `atomic-write` separates cross-process lock from fsync; protocol documented. | **P1** — current implementation is BATCH by default; correctness-equivalence with dsh requires the protocol enum on the contract side per note 2 (`2026-09-03-2-seam-fsync-semantics.md`). | Yes with G3/G4. | No. | `rg "FsyncProtocol" lca/ lca/contracts = 0`; `lca/infrastructure/observability/spine/sinks/file_sink.py:267-299` 3 fds × implicit semantics; `lca/infrastructure/observability/spine/sinks/tracing_file_sink.py:63` `fsync_batch=...` no `PER_WRITE` enforcement. ADR-0179 referenced by note 2 is **not yet drafted**. |
| G3 | **Observation L1 SSOT residual**: 30+ Status enum literal sites still bypass `RunLifecycleStatus`; `_capture_io.to_jsonable` + `projector.to_jsonable` double; `seam_key: str` not migrated to `CapabilityKey`; `kernel_log_path` / `exceptions_path` / `profile_snapshot_path` not on `RunLocator`. | dsh uses one `Status` enum and one `Jsonable` mapper per event type. | **P1** — entry point of `2026-09-03-1-architecture-1-convergence-contract.md` (note 1); A/B/C PRs in the note not split into commits yet. | Yes; pure refactor. | No. | `rg '"paused"' lca/ scripts/ tests/ | wc -l > 30` (per note 1 §Problem); `rg "def to_jsonable" lca/` returns 2; `rg "seam_key: str" lca/contracts/` > 0. |
| G4 | **Observation L4 single-emitter cleanup**: `runtime_loop.py:281/296` still passes 4-key naked dict to `reflectors.runtime.emit_exception_caught`; `EnvelopeEmitter.emit_exception_caught` Protocol still has the 4-str signature; `asyncio.CancelledError` branch hardcodes `"asyncio.CancelledError"` instead of binding `type(exc).__qualname__`. | dsh: one typed payload dataclass per EP, no naked dict on hot path; reflection-style 4-key emitters do not exist. | **P1** — single-emitter note `2026-09-03-3-seam-emit-single-entry.md` PR-1/PR-2/PR-3 not landed. | Yes; pure refactor of runtime_loop. | No. | `rg "emit_exception_caught" lca/` = 16 (target: 1 in `exception_emit.py`); `lca/contracts/protocols/runtime/envelope_emitter.py:88` and `lca/plugins/observability/spine/reflectors/runtime.py` still emit 4-str; `lca/runtime/runtime_loop.py:281` `"asyncio.CancelledError"` literal. |
| G5 | **Assistant payload reconstruction outside `fold_source`**: only `StandardCursor.at()` exposes assistant content via fold; webserver trajectory handler / `lca-ops explain` / `journal replay` still read old `model_visible/step_N/` sidecar for assistant content (no separate assistant sidecar; assistant was never in the 6-tuple, hence the BUG). | dsh semantic-inspect layer rebuilds assistant from session log fold (`ui-conversation/contract/request-inspection.ts:54-87`). | **P0** — required to actually demonstrate "journal 自含 + assistant 重建" target from ADR-0185 §3.2 / Note `2026-09-04-model-visible-bus-alignment.md`. | Yes with G1 (same wiring path). | Yes for full cleanup. | `lca/infrastructure/observability/replay/fold_source.py:183-197` extracts assistant payload; `lca/infrastructure/observability/replay/cursor.py:79` uses folded.assistant only in `at()`; webserver explain handlers do not import fold. |
| G6 | **EventBus NotificationBus `subscribe_pull` is a skeleton, not wired to `SpineReader`**: `lca_kernel/events/notification.py:75` pushes onto `asyncio.Queue`; docstring explicitly says "PR-3 替换为 SpineReader seek-by-seq 实现"; no caller exists; `delivery_queue.aiter()` is the same pattern. | dsh exposes async iterator readers (`session.read()` async iterator) for derivers; subscribers are pull, not just push. | **P2** — current sync fanout covers the I-FW-BUS-1/2 contract; pull is the migration path for deriver reconnection and backpressure-friendly consumers. | Yes; pure addition. | No. | `rg "subscribe_pull" lca/ lca_kernel/ tests/` returns 5 hits, 0 callers; `lca_kernel/events/queue.py:44` `aiter() 留给 PR-2`; `delivery_snapshot` reads from sync `_dispatch_sinks`. |
| G7 | **`writable.step.{start,end}` not emitted by `cursor.record_request_header` / `cursor.advance("stop")`**: ADR-0184 PR-E §D6 is unlanded; `step_tree_accumulator` falls back to implicit `brain.think.start` window (ADR-0176 D1). | dsh emits an explicit `step.start` / `step.end` boundary per reasoning segment; journal self-derives steps without implicit signal. | **P1** — closes the explicit-vs-implicit window ambiguity; required for "journal 自含 + step 边界可查" target. | Yes; minimal cursor touch. | No. | `tests/scenarios/test_event_delivery_e2e.py:50-55` lists `writable.step.start` in `REQUIRED_LEDGER_EPS` but test is `xfail(strict=True)`; `JournalStep.extra` has no `window_signal` field. |
| G8 | **Plugin-universe residual after PR-1/PR-2**: ~~`lca/agent/orchestration_strategies/` strategy classes~~ closed — 7 策略类归位 `lca/plugins/strategies/` 与消费插件同文件，旧目录删除（note `2026-09-04-plugin-universe-single-entry.md` PR-3 (a) delete-when `rg "lca.agent.orchestration_strategies" lca/` = 0 已满足）；~~7 @plugin position-escapees~~ closed — `audit-plugin-shape` plugin_location 维度 = 0（`lca_kernel/events/manifest.py` kernel 元插件位置合法）；residual: 6 dead `scenario-*` / `researcher-*-tools` bundles; 4 orphan `@plugin` (null_critic / null_synthesizer / sub_composers / coding_agent_tools.py); id grammar `lca-` 148 sites still in baseline. | dsh `cordis.patch.yml` row + npm package name as the single activation truth; no `@plugin` outside `lca/plugins/` equivalent; one id grammar. | **P2** — gate hygiene; does not block DSH semantic alignment. | Yes; mechanically independent. | No (PR-3 of note is purely deletion + import update). | `rg "orchestration_strategies" lca/ tests/ scripts/ bundles/ profiles/` = 0; `./scripts/lca-ops audit-plugin-shape` plugin_location = 0; `docs/notes/baselines/plugin-id-grammar.json` exists but id count > 0; `bundles/scenario-*.yaml` dead `$module` not removed. |
| G9 | **Event yaml + Pipeline yaml still class-path, not id-referenced**: `spine.yaml` 101/101 + `team.yaml` publisher / consumer tokens are class paths; `pipeline_loader.py` `plugin:` field declared but not enforced; `verify_yaml_id_authority.py` not written. | dsh: id (npm package) is the only activation reference; yaml equivalent contains package names, not module class paths. | **P2** — gate hygiene; same shape as PR-5 of plugin-universe note. | Yes. | No. | `rg "lca\.plugins\..*\.[A-Z][A-Za-z]+$" lca_kernel/events/config profiles/event-pipeline` returns > 0; `EventRegistry._resolve_tokens` accepts class-path form; `lca_kernel/events/registry.py:582` docs warn default is `strict=True` but production boot flips to `False`. |
| G10 | **Authoritative emitter for model-visible is not enforced**: `rg "publish.*spine\.llm\.request\.header" lca/` returns multiple hits including `spine_reflector_body_llm/plugin.py:386` (still references the category but no longer the registered publisher after PR-1) and the model-visible publisher; I-MV-1 architectural test not yet present in `tests/architecture/test_event_bus_invariants.py`. | dsh: category → producer mapping is a one-way registry; multiple emitters for the same category are a hard error. | **P2** — semantics already correct after PR-2 (yaml registration single-publisher); architecture test codifies it. | Yes with G1. | Yes for cleanup. | `rg "publish.*spine\.llm\.request\.header" lca/` shows publisher.py + hook.py + reflector_body_llm/plugin.py (stale string); `tests/architecture/test_event_bus_invariants.py` exists but lacks `test_i_mv_1` … `test_i_mv_5`. |
| G11 | **Payload contract L2 typing not at runtime**: ADR-0183 PR-3 says "type-hint 21 publisher payload classes inherit EventPayload"; current code has `EventPayload` base + `FieldType` enum but `bus.publish` schema-validation is yaml-fields only; no pydantic / dataclass runtime check on emit. | dsh: discriminated-union + compile-time check; runtime schema validation per EP. | **P2** — type safety; `2026-09-03-4-contract-payload-schema-typing.md` proposes pydantic v2 selective validation, not landed. | Yes; contract-layer work. | No. | `rg "class .*Payload(EventPayload)" lca_kernel/events/payloads/ lca_kernel/events/payloads_model_visible.py` returns 21; no `parse_obj` / `model_validate` in `lca_kernel/events/bus.py publish` path; `EventSpec.fields` is still `dict[str, str]` per ADR-0183 §1.7 #6. |
| G12 | **EmitPipeline still uses `phase_graph` direct sink write**: ADR-0184 PR-F (follow-up) explicitly says "EmitPipeline (`lca/plugins/observability/spine/emit_pipeline.py`, `phase_graph` family)迁总线 + `write_port_append` 调用方清零" — startup condition only, no body yet. | dsh: phase_graph emits ride the same bus as everything else. | **P3** — long-tail cleanup; ADR-0184 acknowledges "启动条件为 PR-D/E 验收通过". | Yes; pure addition. | No (PR-D/E dependency). | `lca/plugins/observability/spine/emit_pipeline.py` exists; `rg "phase_graph" lca_kernel/events/config/observability/spine.yaml` returns 4 categories; no PR-F body in `docs/notes/proposed/`. |
| G13 | **payload typing for `spine.tool.*` / `spine.body.*` / `spine.runtime.*` still string-dict**: 101 categories all in yaml; only model-visible and team.delegation have typed payload classes; `payload_class:` field is mandatory but most categories still point at `EventPayload` base. | dsh: typed discriminated union per EP. | **P3** — bulk typing work. | Yes. | No. | `rg "payload_class: lca_kernel.events.payloads.EventPayload\b" lca_kernel/events/config/` returns > 90; note `2026-09-03-4-contract-payload-schema-typing.md` not yet implemented. |
| G14 | **`lca-ops events-delivery --policy` reads from `PersistenceWorker.default()` only when available**: `lca/infrastructure/cli/commands/events_delivery.py:48-49` falls back to "PersistenceWorker not loaded (PR-2 not merged yet)" — i.e. the cli command shipped without the worker being wired into `EventBus._dispatch_sinks`; PR-D of ADR-0184 is the wiring PR. | dsh: a single CLI surfaces unified fsync policy + counters. | **P1** — the cli exists; the wire-up that makes its `--policy` output non-trivial is what makes "投递黑洞可定位" real. | Yes with G7. | No. | Same source line in `events_delivery.py:48-49`; PR-D of ADR-0184 PR sequence (`docs/adr/0184-event-lifecycle-managed-delivery.md` §5) not yet executed. |
| G15 | **Auth matrix consumer-side still has class-path residual**: `JournalSink` 1/101 authorization ratio still in `spine.yaml` (per ADR-0183 PR-4 delete-list); `SpineChainSink` / `SpineStepTreeAccumulator` may have zero `subscribe()` calls; `tests/architecture/test_event_bus_authority_consistency.py` not written. | dsh: yaml 授权 ⟺ producer/consumer 代码 ⟺ runtime subscribe 三向一致. | **P2** — plugin-universe PR-6 is the closure. | Yes with G8/G9. | No. | ADR-0183 §1.7 #3 + plugin-universe note PR-6 description; `rg "sinks.journal" lca/` > 0; `JournalSink` plugin still on disk. |

## 3. Top 10 actionable gaps (with rationale)

The following ordering ranks by **DSH alignment value + risk of leaving
non-aligned parallel paths in production**, then by **parallelizability**:

| Rank | Gap | Why this rank | Parallel? | Depends on PR-4? |
|---|---|---|---|---|
| 1 | **G1 — webserver trajectory / `lca-ops explain` / doctor tool_schema_count 仍读 `<run_dir>/model_visible/*.json`** | Two parallel SSOTs in production today (fold path in `StandardCursor` + sidecar path in doctor / CLI). Highest semantic drift vs ADR-0185 §3.2 target "journal 自含". | Yes with G5 | Cleanup yes; fold-preferred path no |
| 2 | **G5 — assistant payload 重建未走 webserver / `lca-ops explain` 路径** | Without G5, "assistant 不可重建" BUG persists in production viewer even though the fold module can reconstruct it. Direct dependency on ADR-0185 §3.2 / Note `2026-09-04-model-visible-bus-alignment.md` BUG-fix promise. | Yes with G1 | Yes |
| 3 | **G14 — `lca-ops events-delivery --policy` + `PersistenceWorker.default()` 与 EventBus 不共享 queue** | ADR-0184 D2 / D4 wiring is half-done: cli exists, counters exist, but PR-D (cursor → bus entry) and PR-C `apply_pipeline` boot switch are not executed. Without them `dropped == 0` is not enforceable on live runs. | Yes with G7 | No |
| 4 | **G7 — `writable.step.{start,end}` 未由 cursor 发射 / `window_signal` 字段未写入** | Closes "step 来源可查" target from ADR-0184 §D6 + the existing xfail `test_event_delivery_e2e` flips to pass once this lands. | Yes with G14 | No |
| 5 | **G4 — `runtime_loop` 4 键裸 dict + 平行 `reflectors.runtime.emit_exception_caught` + `EnvelopeEmitter.emit_exception_caught` Protocol 4-str 三入口并存** | `2026-09-03-3-seam-emit-single-entry.md` PR-1/PR-2/PR-3 unlanded; user-visible BUG "traceback 永久丢失" persists because 4-key payload < 4 KiB does not trigger offload. | Yes | No |
| 6 | **G2 — `FsyncProtocol` enum 未上提 `lca/contracts/observability/ssot.py`；FileSink 3 fd × 3 implicit fsync 语义；`TracingFileSink._fallback_fd` 无 fsync** | ADR-0179 (referenced by note 2) is not drafted; correctness-equivalence with dsh `session-persistence-jsonl` requires protocol-level enum. Severity: `traces/runs` 不全是用户痛点的物理根因之一。 | Yes | No |
| 7 | **G3 — 30+ Status enum 字面 / `_capture_io.to_jsonable` 双份 / `seam_key: str` 未迁移** | L1 SSOT residual blocks the `2026-09-03-1-architecture-1-convergence-contract.md` PR-A/B/C landing; without it the 9+4 lint goals stay under target. | Yes | No |
| 8 | **G10 — `spine.llm.request.header` 仍被 stale reflector 字符串引用；I-MV-1/2/3/4/5 架构测试未落地** | Codifies what is already enforced by yaml registration; without it, future regressions in producer uniqueness will not be caught. Cheap to add; high signal. | Yes with G1 | Yes |
| 9 | **G15 — `JournalSink` 1/101 授权 + 三向一致性架构测试缺失** | Closes ADR-0183 PR-4 residual + plugin-universe PR-6; without it, dead sink + silent yaml miss can reappear (already caused 09-04 `UnauthorizedPublishError` 500 outage per note `2026-09-04-event-bus-publisher-authorization.md`). | Yes with G8 | No |
| 10 | **G8 — plugin-universe PR-3 (dead code) + PR-9 (7 @plugin 位置逃逸归位) + PR-11 (id grammar 滚动)** | 策略类位置残留与 7 @plugin 逃逸已关闭（策略类归位 `lca/plugins/strategies/`，plugin_location = 0）；residual: 6 dead scenario bundles + 4 orphan @plugin + id grammar 148 sites。Bulk-delete + import update work; mechanically independent of DSH semantic alignment. | Yes | No |

## 4. Not in this audit (intentional exclusions)

- **PR-4 deletion work** (`ADR-0185 PR-4`, `plugin-universe PR-3/4/5/6/7/8/9/10/11`, `note 1-4 PR-A/B/C`) — in flight in parallel worktrees; overlaps here would double-track.
- **G6 (NotificationBus.subscribe_pull) status note**: skeleton exists in `lca_kernel/events/notification.py:75` with explicit "PR-3 替换" docstring; PR-3 of ADR-0184 has not landed. Pull semantics remain a P2 follow-up; current sync `_dispatch_sinks` + `delivery_snapshot` covers the I-FW-BUS-1/2 contract.
- **G12 / G13 (payload typing bulk work)** — long-tail; explicitly P3 because they do not change wire semantics, only type safety.
- **G11 (runtime schema validation)** — pending pydantic vs dataclass decision from `2026-09-03-4-contract-payload-schema-typing.md`; no ADR filed yet.

## 5. Suggested sequencing (out of audit scope, advisory)

1. Ship **G1 + G5 + G10 + G14** as one PR sequence ("ADR-0185 PR-3.1 + ADR-0184 PR-D"): fold path replaces sidecar in webserver / `lca-ops` / doctor, I-MV-1/2/3/4/5 architecture tests land, PersistenceWorker wires into bus default queue. Together this eliminates the two highest-cost parallel SSOTs.
2. Ship **G7 + G14 收尾** (ADR-0184 PR-E): `writable.step.{start,end}` explicit emission, `window_signal` on `JournalStep.extra`, xfail → strict in `test_event_delivery_e2e`.
3. Ship **G4 + G3 + G2** as 3 independent PRs (single-emitter / L1 SSOT / FsyncProtocol): align with notes 1/2/3 + ADR-0179.
4. Cleanup **G8 + G9 + G15** (plugin-universe PR-3 / PR-5 / PR-6 + ADR-0183 PR-4 residual): mechanically independent, no wire impact.

## 6. Repo evidence inventory

Files / searches used in this audit (non-exhaustive):

- `rg "foldRequestHeader\|fold\.py" lca_kernel` — PR-0 fold module landed
- `rg "subscribe_pull" lca/ lca_kernel/ tests/` — 5 hits, 0 callers
- `rg "FsyncProtocol" lca/ lca/contracts` — 0 hits in contracts SSOT
- `rg "configure_delivery_policy(strict=True)" lca/` — 3 hits, all in tests
- `rg "model_visible_llm_adapter\|ModelVisibleLLMAdapter\|StdModelVisibleCapture\|StdReasonerPromptCapture" lca/` — present (PR-4 unlanded)
- `rg "fold_model_visible\|foldRequestHeader" lca/plugins/transport` — 0 hits (PR-3.1 unlanded)
- `rg '"paused"' lca/ scripts/ tests/` — > 30 (note 1 unlanded)
- `rg "def to_jsonable" lca/` — 2 hits (note 1 unlanded)
- `rg "emit_exception_caught" lca/` — 16 hits (note 3 unlanded)
- `rg "@plugin\b" lca/runtime/reducer.py lca/cognition/team/modes lca/application/session_live_builder_provider.py` — 7 hits (plugin-universe PR-9 unlanded)
- `rg "lca\.plugins\..*\.[A-Z][A-Za-z]+$" lca_kernel/events/config profiles/event-pipeline` — > 0 (plugin-universe PR-5 partial)

## 7. What this audit does NOT claim

- Not a code-level review of any single ADR; ADR texts are taken at face value.
- Not a runtime performance comparison (DSH throughput, latency) — out of scope.
- Not a security review (BOLA / SSRF / Prompt Injection) — out of scope.
- Not a release-plan; sequencing in §5 is advisory only and does not commit to merge order.

---

Audit trail: read-only repo traversal via grep / list_dir / read_file on
2026-09-04. No source files modified.
