# Raphy Assessment — 2026-10-19 01:45 round (`raphy/arch-20261019-0145`)

Basis: main tip `0a024decf` (clean worktree; RA-147 merge landed in the
previous round). 3 hot areas read end-to-end; runtime verification run on
the branch with `LLM_API_KEY=dummy`.

## Phase 1 — Explore

### Hot-spot scan (`git log --oneline -40`)

The last 40 commits are dominated by three lanes:
1. **browser tooling** (agy): 13-tool suite, live page wiring, scenario
   tests, transfer arbitration (walked thoroughly in the 2026-10-18
   22:58 round → RA-147; skipped this round to avoid re-walking).
2. **raphy rounds themselves**: RA-146 / RA-147 merges.
3. **iter-quality / iter-tests hygiene + memory**: N-series scans,
   sense-gate dead-store, layout budget bumps.
4. **docs/plans**: stochastic-decision-brain + stealth-actuator-decouple
   plans — verified they target `~/tools/x-operator` (a different repo),
   not this one; not a hotspot here.

Hot areas chosen for the friction walk (all different from last round):
(A) `lca/cognition/proactive/worthiness.py` (249L, single module),
(B) `lca/application/api/api.py` (334L, the public Agent/Team facade),
(C) the web_search dual seam:
`lca/infrastructure/tools/web_search/__init__.py` (WebSearchExecutor) +
`lca/infrastructure/capability/search/search.py` (SearchService) +
`lca/infrastructure/search/service/service.py` (module-level `web_search`).

### Organic friction walk

#### Area A — `proactive/worthiness.py`

1. **Bouncing between small modules?** No — the whole worthiness gate is
   one module with five small private functions; contracts live in
   `lca/contracts/models/proactive/`. Good locality.
2. **Shallow modules?** No. `_decide_matrix` / `_apply_downgrade_only` /
   `_apply_policy` each concentrate one real decision; the deletion test
   passes (deleting any of them concentrates, not moves).
3. **Pure functions hiding call-site bugs?** No — this is the good case:
   `decide()` is a genuine pure function and the call sites are thin.
4. **Leaky seams?** No — the docstring's honesty claims check out:
   REJECTED short-circuits before the downgrade merge (credential redline
   is "highest suppression"), and the downgrade-only merge never upgrades
   (`base_level > declared_level` keeps the declared verdict). The module
   docstring's fail-closed/fail-open split (credentials + request_ref
   membership are exactly decidable → fail-closed; "worth interrupting"
   is not → quiet surface) matches the code line for line.
5. **Testability?** The interface IS the test surface: `decide(request,
   policy=, now=)` is fully deterministic and testable through the
   interface.
6. **Verdict**: examined, no story. Honest module, well-documented.

#### Area B — `application/api/api.py`

1. **Bouncing?** No — single facade module; the spec lives in
   `contracts/protocols/journal/spec/spec.py`, assembly in `api/spawn.py`.
2. **Shallow?** No. The `Agent.__init__` concentrates real assembly work
   (auto_mcp dedup, RoleProfile materialization, ToolPermissionManifest
   authorization per C5, fail-loud `llm is None` TypeError). Deletion test
   passes.
3. **Leaky seams?** `run()` sets capability bindings around
   `self._agent.run` and resets in `finally` — honest, no leak.
4. **Verdict**: examined, no story. The facade earns its depth.

#### Area C — web_search dual-dispatch (THE FINDING)

Files:
- `lca/infrastructure/tools/web_search/__init__.py`
  (`WebSearchExecutor.search`, lines ~87-89)
- `lca/infrastructure/capability/search/search.py` (`SearchService`)
- `lca/infrastructure/search/service/service.py` (module `web_search`)
- `lca/infrastructure/tools/default/set.py` (`build_default_tools`,
  `build_g2a_chat_tools`)
- `lca/plugins/act/tools/provider.py` (`_g2a_factory`)

1. **Bouncing between small modules?** Yes — and this is the finding.
   `WebSearchExecutor` declares itself a *"search seam Consumer — 只通过
   SearchService（Definition）发请求"* (line 62), but `search()` reads:

   ```python
   if self._search is not None:
       result = await self._search.web_search(query, topic=topic_s, time_range=range_s)
   else:
       result = await web_search(query, topic=topic_s, time_range=range_s)
   ```

   The `else` branch silently routes to the **infrastructure** `web_search`
   — a different seam with a different provider strategy:
   - `SearchService.web_search`: single-active `ProviderDispatch`
     ("current()"), `RuntimeError("search: no provider registered")`
     when empty, no observability marking, no fallback chain.
   - infra `web_search`: tries `configured_provider_ids()` in order with
     per-provider fallback, fires `mark_web_search_attempt` scope
     observability, returns `SearchResponse(error=...)` gracefully.
2. **Leaky seam?** Yes, both directions:
   - Through the identical `Tool.execute` interface, the caller cannot
     tell which seam executed the query — different providers may answer,
     different observability fires, different failure semantics apply.
     "The interface is the test surface": this interface cannot
     distinguish "routed via kernel ctx.search" from "routed via infra
     fallback".
   - It breaks the kernel degrade-to-None discipline: `_g2a_factory`
     deliberately degrades a wrong-shaped `b.search` to `None` with the
     comment *"build_default_tools skips the corresponding tools"* — but
     web_search tools are NOT skipped when `search=None`; they get built
     anyway and silently swap backends.
3. **Narrative vs implementation** (RA-115 class): the class docstring
   promises "只通过 SearchService（Definition）发请求"; the code does
   "SearchService, or silently the other seam".
4. **Untested?** `rg` finds zero tests covering `WebSearchExecutor`'s
   dispatch decision. `test_search_providers.py` pins only the infra
   fallback chain; `test_plugin_alignment.py` pins that `SearchService()`
   must not be instantiated in the composition root (it must come from
   the plugin tree) — which constrains the fix direction.
5. **Duplication scan**: the twin `web_search` definitions (module fn vs
   `SearchService.web_search`) are this same finding, not a second one.
   No other mechanical duplication found in the walked areas.

### Runtime verification

- Agent smoke with `MockLLMAdapter` on the branch:
  `RUN1: completed | RUN2: completed` (two sequential runs, no
  crash/hang/silent-failure).
- No P0 crash/hang found.

## Phase 2 — Self-grilling (RA-148)

- **Constraints**:
  - The kernel seam ownership stays: `ctx.search` is owned by
    `SearchService` (Definition); the `lca-search-provider` plugin
    registers providers on it; `test_plugin_alignment.py` forbids
    `SearchService()` inline instantiation in the composition root.
    The fix must not re-litigate the Definition/provider-registry
    architecture (ADR-0220 §4.1) and must not instantiate
    `SearchService()` in the composition root.
  - `browser/tools.py` (RA-147) calls the infra `web_search` directly —
    that path is settled and out of scope; the infra seam itself stays.
  - Tool name/namespace/parameters of the web_search tool unchanged.
- **Dependencies**: callers are `build_default_tools` /
  `build_g2a_chat_tools` ← `_g2a_factory` (kernel, `fallback=False`,
  `search` from `BindingsView`, degraded to None on wrong shape).
- **Shape of the deepened module**: two honest options (RA-115 rule:
  narrative must equal implementation):
  - (a) **fail-closed**: delete the silent `else` branch; when
    `search is None`, return a fail-closed `Observation`
    (success=False, "no search backend"). This matches the existing
    docstring claim — "删掉承诺也是诚实解".
  - (b) **declared dual-path**: keep both paths but declare the fallback
    in the docstring, expose which seam executed each call (e.g. via the
    Observation `extra`/reason), and pin both paths with tests.
  - Either way, the routing decision becomes visible through the
    interface; the silent swap dies.
- **Test survival**: `test_search_providers.py` (infra chain) unaffected;
  `test_plugin_alignment.py` (SearchService() guard) must stay green;
  new tests pin the dispatch decision (search=None vs SearchService).
- **Deletion test verdict**: deleting the `else` branch concentrates the
  routing decision at construction time (the `build_tools` caller must
  supply `SearchService` or accept fail-closed) instead of hiding the
  seam choice behind the interface. Concentrates (weakly — the fail-closed
  vs declared-dual-path choice is still open, hence Worth exploring).
- **Strength**: Worth exploring. Real leaky seam + narrative mismatch +
  testability gap, but the fix direction needs a judgment call between
  fail-closed and declared dual-path, and the kernel plugin wiring
  implications deserve care.

## Phase 3 — Present and record

| ID | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-148 | `lca/infrastructure/tools/web_search/__init__.py`, `lca/infrastructure/capability/search/search.py`, `lca/infrastructure/search/service/service.py`, `lca/infrastructure/tools/default/set.py`, `lca/plugins/act/tools/provider.py` | `WebSearchExecutor` 宣称"只通过 SearchService（Definition）发请求"，但 `search=None` 时静默走 infra `web_search`——另一套 provider 策略（单活派发 vs 有序 fallback、可观测打点、失败语义都不同）。接口层面无法区分哪条 seam 真执行了；kernel 的 degrade-to-None 纪律被违反（search=None 没跳过工具，而是静默换 backend）；零测试覆盖该派发决策。 | 二选一：(a) 删 `else` 分支，`search is None` 时 fail-closed（契合现有 docstring）；(b) 把 fallback 写成显式声明的双路径，Observation 里暴露实际走的 seam + 测试钉住两条路。 | locality：派发决策从运行时隐式行为收敛到构造时显式契约；leverage：以后所有 web_search 消费者只面对一条诚实 seam，可观测与失败语义可预测；tests 通过接口就能断言路由。 | Worth exploring |

Top recommendation: **RA-148** is the only candidate this round (areas A and B
came back clean — both modules earn their depth; worthiness.py in particular
is the good example of what the docstring-honesty discipline looks like when
it holds). The web_search dual-dispatch is the same RA-115 narrative-vs-code
class in a new seam, with a testability gap on top. Implement by picking
fail-closed vs declared-dual-path per the acceptance criteria; the story
accepts either as long as narrative == implementation.

Assessment complete: 1 story written, top is RA-148.
