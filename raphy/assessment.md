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



=====================================================================
## Assessment — 2026-10-19 04:47 (branch raphy/arch-20261019-0447)
=====================================================================

### Scope (YAGNI: git log -40 热点)
- browser 13-tool suite（de18490a0 / c0be39af2, 2026-10-18）：tools.py +1155 行、task_store.py 新建、cdp_driver.py +505 行——最大热区。
- web_search RA-148 收敛（14a487091, 当日早）：已落地，禁区。
- x-operator SSOT studio（194a8493d）、stochastic brain（5c82c41c6）：纯 docs/plans，无代码实现，不碰。
- 禁区（progress.txt Patterns）：RA-115/116/119/120/123/136/137/138/139/146/147/148 落地带；carrier/runs/resume.py；resource key probes（writer/state/adapter）。

### Friction walk（3 热区，全读非 grep）
A) lca/infrastructure/tools/browser/tools.py（1155 行全读）
B) lca/infrastructure/browser/cdp_driver.py（505 行全读）
C) lca/infrastructure/tools/browser/task_store.py（131 行全读）+ contracts/models/browser/models.py（71 行全读）

#### A 区五问
1. bounce：理解"任务派发"只看 tools.py 一处就够；但"引用解析"概念横跨 search 工具（写）/lookup 工具（读）/模块全局 dict（存）——三处 bounce。
2. shallow：每个 tool 类的 parameters/execute  vs 实现：BrowserListTasksTool 等只读工具深浅适中；BrowserSpawnTaskTool 的 description 承诺"异步执行+handoff 回流"，实现只做 session 创建+record 登记——interface 比实现"深"在假的方向（见 RA-149）。
3. 纯函数提取：_normalize_url 是真纯工具函数，有 locality；其余无 testability-driven 提取。
4. leaky seam：`_RECENT_SEARCH_RESULTS` 模块全局 dict 承载"引用"概念，search 写/lookup 读——seam 寄在模块命名空间而非任何模块（见 RA-152）；BrowserOpenTool 宣称"已在真实浏览器中打开页面"，但从不校验 driver.has_page()——resilient mode 的无 page session 照样报成功（见 RA-153）。
5. testability：spawn 的"异步执行"声明没有任何测试能钉住——因为没有任何执行者存在；_RECENT_SEARCH_RESULTS 的淘汰语义无测试（因为无淘汰）。

#### B 区五问
1. bounce：理解"输入派发"要读 driver.dispatch_input + arbitration.evaluate_input + routes_browser.py:170——三层，可接受。
2. shallow：PlaywrightCDPDriver ~15 方法 vs 505 行实现：deep module，deletion test 通过（删掉会话隔离/resilient/代理探测都要重写）。
3. 纯函数提取：choose_chromium_proxy/_chromium_proxy 是环境探测纯函数，无调用方隐藏 bug 证据——N/A。
4. leaky seam：`dispatch_input` 在 `self._cdp_sessions.get(session_id) is None` 时 return True——无 CDP、无 page，输入被吞，仍报成功（见 RA-150）。`navigate()` 在 page.goto 失败后仍返回 title="Navigated Page" 的 summary，工具层顺势宣称"真实打开"（见 RA-153）。
5. testability：dispatch_input 无 CDP 分支零测试；可通过 driver 接口直接钉（接口是对的）。

#### C 区五问
1. bounce：理解"验证码偏好"要看 record 字段（task_store.py:25）+ store 级 `_captcha_preferences` dict（:48）——双态，前者零读写（grep 全仓确认），后者是真状态（见 RA-152）。
2. shallow：store 接口 vs 131 行实现：depth 合理。
3. 纯函数提取：无。
4. leaky seam：`update_task(task_id, **kwargs)` + `hasattr/setattr`——stringly-typed 突变 seam，任意属性名可写记录；"The interface is the test surface"：kwargs 界面钉不住合法字段。本轮只观察，不成故事（Speculative）。
5. testability：list_tasks 的排序逻辑有测试；captcha scope 优先级（task>site>all_tasks）测试覆盖未知——RA-152 附带钉。

### 运行时验证（强制，干净主树本轮分支上执行）
- (a)+(c) MockLLMAdapter smoke：`RUN1: completed | RUN2: completed`——无 crash/hang/静默失败。
- (b) e2e：tests/scenario/browser/test_browser_preview_and_takeover_e2e.py —— 1 passed。
- 无新 P0/P1。

### Duplication scan（friction walk 之后）
- 6 个 tool 类逐字重复 `__init__(self, driver=None)` + `_get_driver()` 懒导入样板（tools.py:215/302/428/959/1013/1075）——见 RA-151。
- `[widget:browser_preview?...]` f-string 在 open/spawn/transfer 三处重复——RA-151 附带。
- 其余无字面簇。quota 满足：5 个 story 里只有 RA-151 是纯重复类。

---

### RA-149 自烤问 — spawn 的"异步执行 + handoff 回流"叙事≠实现
- **Constraints**：tool description 是 Muse 工具契约的一部分（模型据此决定"结束本轮等 handoff"）；ADR-0280 记录 13 工具套件；tests/scenario/browser/* 钉住了 spawn 的回执行为（改 fail-closed 要同步改测试）。
- **Dependencies**：消费者：零。`task_description` 全仓无 reader（subagent.py 不碰 task store；store 只有 tools.py 自身做 list/peek/steer/close/transfer）；handoff 无 producer。调用方：LLM（按 description 行事）。
- **Shape**：按 RA-115 二选一：(a) fail-closed——spawn 返回 honest error（"异步派发后端未实现"），像 deep_research（RA-147）那样；(b) 真 seam——新建 BrowserTaskRunner 消费 task_description，经 BrowserSubagent+arbitration 执行，timeline 落步骤，handoff producer 接线。本轮评估不预设立场，story 接受任一方向。
- **Test survival**：现有 spawn 测试钉的是"回执含 browser_task_id"——(a) 方向下这些测试要改写为钉 fail-closed；(b) 方向下要新增 runner 消费测试。
- **Deletion test verdict**：删掉 description/result text 里的"后台异步执行/handoff 回流"字句，复杂度零移动、诚实度上升——concentrates（诚实）。Strong。

### RA-150 自烤问 — dispatch_input 无 CDP 时静默 True
- **Constraints**：routes_browser.py:170 是人机视口唯一输入路径；arbitration gate 必须保留在前（安全顺序正确）；BrowserDriverPort 协议的 bool 返回语义。
- **Dependencies**：调用方：routes_browser.py:170（human 输入）。无 CDP 意味着无 page——输入无处可送。
- **Shape**：fail-closed：cdp 为 None 时 return False（+ 日志），与 arbitration 拒绝的 False 同语义。上游 routes 据此可给视口"未连接"反馈。
- **Test survival**：现有 dispatch 测试走有 CDP 路径（mock），无 CDP 分支零测试——新测试钉死。
- **Deletion test verdict**：删掉 `if cdp is None: return True`，改 False：把"降级到谎言"收成"降级到诚实"——concentrates。Strong（同 RA-147 伪造成功类）。

### RA-151 自烤问 — 6× _get_driver 样板
- **Constraints**：懒导入是为了避开 infrastructure.search 与 tools.browser 的导入时循环（BrowserSearchTool 注释）；base 类不能把导入提前到模块顶。
- **Dependencies**：6 个类 + build_browser_tools 的 driver 注入；测试经 set_shared_browser_driver / 构造注入。
- **Shape**：`lca/infrastructure/tools/browser/_driver_tool.py`（同类家园，RA-139 式）放 `_DriverInjectedTool(Tool)`：`__init__(self, driver=None)` + `_get_driver()` 懒导入；6 类继承。widget_tag 三处 f-string 收成小 helper。
- **Test survival**：构造注入测试不变；懒导入路径测试（无 driver 时走单例）照样过。
- **Deletion test verdict**：删掉 6 份样板，懒导入 seam 集中一处——concentrates。Strong（RA-136："two = real"，此处 six）。

### RA-152 自烤问 — 验证码偏好双态 + 引用缓存无界
- **Constraints**：captcha scope 优先级（task>site>all_tasks）是既有语义；citation_id 格式 `cit_<search_id>_<i>` 被 lookup 工具依赖。
- **Dependencies**：captcha 真状态：store._captcha_preferences（set/get 工具）；死字段：record.captcha_preference（零读写）。引用：search 写（:138）/lookup 读（:363），模块全局。
- **Shape**：(a) 删 record.captcha_preference 死字段（诚实解）；(b) _RECENT_SEARCH_RESULTS 收进深模块（如 task_store 内的 SearchCitationStore，OrderedDict LRU + 上限），引用随 search 会话资产走 store seam 而非模块全局。
- **Test survival**：现有 captcha 测试钉 scope 优先级——不动语义；新增引用缓存淘汰测试。
- **Deletion test verdict**：删死字段零复杂度移动；引用收进 store 把概念集中到一处——concentrates。Worth exploring（死字段删除无争议；引用缓存收敛的家园选址是判断）。

### RA-153 自烤问 — resilient-mode 下"已在真实浏览器中打开"伪造成功
- **Constraints**：resilient mode 是合法设计（无 Chromium 环境不炸）；BrowserSessionSummary.status 有 IDLE 等状态；工具契约"真实浏览器"是用户可见承诺。
- **Dependencies**：create_session/navigate 的 fail-open 路径（goto 失败→title="Navigated Page"/"Page"）；BrowserOpenTool/BrowserSpawnTaskTool 从不 has_page()。
- **Shape**：工具层宣称"真实"前过 has_page() 门；或把 liveness 收进 summary（resilient 会话 status 标记），工具按状态诚实措辞。RA-115 二选一：修叙事或修实现。
- **Test survival**：open 成功路径测试（有 page）不动；新增无 page 会话的诚实措辞测试。
- **Deletion test verdict**：把"真实"断言收敛到 has_page 一处检查——concentrates。Worth exploring（resilient 会话在某些部署是预期行为，措辞收敛的粒度是判断）。

---

### 候选表

| ID | Files | Problem | Solution | Benefits (locality+leverage) | Strength |
|---|---|---|---|---|---|
| RA-149 | tools.py (BrowserSpawnTaskTool ~380-490) | description/result text 宣称"异步执行+handoff 回流"，实现只建 session+登记 record；task_description 全仓零消费者，handoff 无 producer——伪造派发 | RA-115 二选一：(a) fail-closed 诚实报错（学 deep_research RA-147）；(b) 建 BrowserTaskRunner 真 seam 消费 task_description+接线 handoff | locality：派发语义集中到一处诚实 seam；leverage：模型不再被"等 handoff"误导空等；tests 可通过接口钉住派发决策 | Strong |
| RA-150 | cdp_driver.py dispatch_input (~425) | 无 CDP session 时 return True：人机视口唯一输入路径（routes_browser.py:170）上输入被静默吞掉却报成功 | fail-closed：cdp 为 None 时 return False+日志，与 arbitration 拒绝同语义 | locality：输入送达语义收进 driver 一处；leverage：上游可给视口真实"未连接"反馈；新测试钉死该分支 | Strong |
| RA-151 | tools.py (6 类 ~215/302/428/959/1013/1075) | `__init__(driver)`+`_get_driver()` 懒导入样板逐字×6；widget_tag f-string ×3 | `_DriverInjectedTool` 基类收进 `lca/infrastructure/tools/browser/`（同类家园）；widget_tag 收成 helper | locality：懒导入 seam 一处；leverage：以后加 driver 工具只继承；零行为变化，测试全存活 | Strong |
| RA-152 | task_store.py (:25/:48), tools.py (:36/:138/:363) | record.captcha_preference 死字段（全仓零读写）与 store 级真状态双态；_RECENT_SEARCH_RESULTS 模块全局无界、无淘汰 | 删死字段；引用缓存收进深模块（store 内 SearchCitationStore，LRU 上限） | locality：偏好/引用概念各归一处；leverage：引用生命周期可管理；scope 优先级测试钉住 | Worth exploring |
| RA-153 | tools.py (BrowserOpenTool), cdp_driver.py (navigate/create_session) | resilient 会话（无 page）下工具仍宣称"已在真实浏览器中打开页面"；navigate goto 失败仍回 title="Navigated Page" | 宣称"真实"前过 has_page() 门，或把 liveness 收进 summary 状态、工具按状态诚实措辞 | locality："真实"断言收敛到一处检查；leverage：无 Chromium 部署不再误导用户；tests 可钉无 page 措辞 | Worth exploring |

**Top recommendation: RA-149.** 理由：它是本轮唯一的"叙事级伪造"——description 直接指挥模型"结束本轮发言等待 handoff"，而 handoff 根本不存在；模型会空等一个永远不来的回流，这是行为级误导，不是代码异味。RA-147 已经为同类问题（deep_research）立了 fail-closed 先例，RA-148 刚为叙事≠实现类定了 RA-115 二选一规则——RA-149 是这两条规则在 browser 任务层的直接应用，评估证据最完整（零消费者 grep 实证），实现方向二选一都已写清，下一轮可直接认领。

Assessment complete: 5 stories written, top is RA-149.
