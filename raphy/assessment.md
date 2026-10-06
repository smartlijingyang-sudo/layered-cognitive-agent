# Raphy Assessment — 2026-10-06

**Skill:** `skills/improve-codebase-architecture/SKILL.md`（Explore + Present）
**Method:** YAGNI scoping via `git log --oneline`（~40 commits, 2026-10-06 hot spots）→
`CONTEXT.md` domain glossary → friction walk → deletion test →
present as candidate table. Avoided ralph Round 2 areas
（DecisionGates / Ingest / ContextFiles shims / Read Runs micro-dirs / `lca/cognition/memory/`）.

## Candidates

| ID | Files | Problem（friction） | Solution | Benefits（locality / leverage） | Strength |
|---|---|---|---|---|---|
| RA-001 | `lca/plugins/domain/assistant/catalog/events.py` ×3, `lca/plugins/assistant/tool/overlay.py` ×1, `lca/plugins/assistant/skill/overlay/overlay.py` ×3 — 7 `_emit_*` methods | Identical no-emitter-fallback seam duplicated 7×: `if self._emit is None: log.info('<scope>.ep.no_emitter')` else `self._emit(EVENT, payload.to_dict())`. Shallow modules: interface nearly as complex as implementation. One fallback-logic edit = 3 files touched today. | Extract one shared seam `emit_assistant_ep_or_log(emit_fn, scope, event, payload)`; log scope as parameter; all 7 delegate. | Locality: fallback behavior in one module. Leverage: future event types get the seam free. Testable through the single seam. | **Strong** |
| RA-002 | `lca/infrastructure/tools/collaboration/delegate_tool.py` L127, L213 — two `_fail(self, start, message)` | Character-identical method bodies in two tool classes of the same module. Copy-paste across classes. | Extract module-level `_fail_observation(start, message)`; both classes call it. **Not** `tools._shared.fail_observation` — Observation kwargs differ (payload=None/error=/extra= vs payload dict). | Locality: Observation construction in one place. Same idiom as `ba2ad56c6`. | **Strong** |
| RA-003 | `lca/plugins/events/hooks/model_visible/adapter.py` — `_emit_lifecycle_pre/post/fail` | Three functions repeat `step = hook._step_counter` + deferred `lifecycle_emit` import + single call. Looks like duplication. | Unify behind one dispatch seam — **only if genuinely simpler**. | Marginal: different signatures/targets; shared part is 2-line scaffolding. | **Worth exploring** |

## Top recommendation

RA-001 first: largest instance of the codebase's own "converge N identical X" idiom
（`ba2ad56c6`, `2a2059cca`, `9fecd23a0`）, deletion test clean, acceptance mechanically
verifiable （grep single `ep.no_emitter` call site）. RA-002 same idiom, smaller scale.
RA-003 weakest — droppable if the seam doesn't simplify.

## Outcome（optimize 轮）

- RA-001 ✅ done（`22fb55d10`）— 实际收敛 9 个（assess 漏了 evolve/jobs 的同形 seam，grep `ep.no_emitter` 发现），237 测试过。
- RA-002 ✅ done（`401c7e22c`）— 150 测试过。
- RA-003 ⏭️ dropped（`d8a5c00bd`）— 逐行对比确认三相签名/payload/目标全不同，统一只能走 getattr 字符串分发，净亏可读性。deletion test 不通过。
