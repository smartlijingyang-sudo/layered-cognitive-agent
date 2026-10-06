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

---

# Raphy Assessment — Round 2 (2026-10-06, hardened prompt)

**Prompt:** `raphy/prompts/raphy-assess.md` @ `9d379ffe2`（用户 23:02 质疑首轮评估太浅后硬化：强制 friction walk 5 问必答、self-grilling、diversity quota）。
**Skill:** `skills/improve-codebase-architecture/SKILL.md`（Explore + Present；引用的 `codebase-design`/`grilling`/`domain-modeling` 三个 skill 不存在，已按 prompt 内嵌词汇表与 self-grilling 替代）。

## Phase 1 — Explore

**YAGNI scoping:** `git log --oneline -40 --name-only -- lca/` 热点计数：
`infrastructure/tools/assistant/memory_tools.py`(3)、`infrastructure/cli/commands/_shared/projection.py`(3)、
`plugins/transport/webserver/read/runs/*`(4)、`plugins/assistant/*`(多)、`infrastructure/memory/contextfiles/*`(2)。
**禁区排除**（ralph Round 2 领地 + 冻结区）：`memory_tools.py` 是 ralph Round 2 "unify the MemoryTools
directory seam" 的领地；`webserver/read/runs/` 是 Round 2 "Read Runs micro-dirs"；
`contextfiles/` 是 Round 2 "ContextFiles shims"；`lca/cognition/memory/` 按 AP-01 冻结；
`plugins/assistant/*` 首轮 RA-001 已收敛。**最终三区**：composer 三阶段组装
（`lca/plugins/composer/`）、CLI 投影（`infrastructure/cli/commands/_shared/projection.py` +
`observation/debug_graph.py`）、daemon 生命周期（`infrastructure/cli/services/daemon/daemon.py`）。

**Friction walk（5 问 × 3 区，file:line 证据；三路并行精读子 agent 报告，本轮综合）：**

**A. composer**（`lca/plugins/composer/`；注：任务简报路径有误，实为 `plugins/composer` 非 `plugins/composition/composer`）
- Q1 sprawl：轻度。理解 think 组装要跳 provider 壳→`brain_composer.py:46`→`brain.py:32-159`；但每层有真实理由（插件声明式注册不可省、composer 是 merge 冲突归因协议）。perceive 的 `build_perceive_hub` 另有真实第二消费者（`application/api/spawn.py:26,38`），拆分是赚的。
- Q2 浅模块：三 provider 壳（各 66 行，除 plugin id/provides 键/authority grant/composer 类外逐行相同）deletion test → **收敛**（表驱动消除 ~130 行样板）。`action_authority.py` 看似浅但删掉是搬运（丢测试接缝）→ 保留。`DefaultBrainPromptCatalogFactory` 是能力类型要求的实例 → 保留。
- Q3 locality 缺口：`build_action_registry_from_authority` 纯且有 fail-closed 测试，但调用点 `body_composer.py:49-50` 预填充了**可变脏注册表**——测试的干净 fake 盖不住注册顺序 bug；`instrument_llm` 的 `llm._inner` 解包行为取决于调用历史，单元测试盖不住。
- Q4 泄漏：`brain.py:65` 直读 `TelemetryLLMAdapter._inner`（跨模块私有属性）；`brain.py:74` 函数内局部 import 躲 composer↔events 导入环；`perceive/composer.py:39` 用裸字符串 `"journal_store"` 能力键（兄弟代码用类型化常量）。
- Q5 盲区：三 provider `setup()` 无直接测试（只测了 bundle 注册项）；`resolve_brain` 测试用 `scope=object()`+MagicMock 绕过真实 boot scope。

**B. CLI 投影**（`_shared/projection.py` 235 行 + `observation/debug_graph.py` 319 行，逐行精读）
- Q1：`debug_graph` 一屏输出链跨两文件 7 函数，但分层本身有 depth；真问题是"半收敛"——`summarize_outputs` 的 docstring 自述从 `debug_graph._summarize_outputs` 折出（projection.py:158-163），但 debug_graph 保留了私有 loader 和手写渲染环，截断宽度都不一致（cap=80 vs 默认 120）。
- Q2：`truncate`/`spine_filename_for_run_cwd`/`_safe_repr` deletion test 全部 → 搬运不收敛（保留）；真收敛点是 `spine_filename_for_run_cwd` 与 `load_spine_events` 内两份逐字相同的 lazy import（projection.py:54-57 vs 76-79）。
- Q3（最硬证据）：`debug_graph._load_events`（debug_graph.py:46-62）是 `load_spine_events`（projection.py:67-108）的私有复刻，**丢了 `isinstance(obj, dict)` 守卫**（projection.py:95-96）。spine.jsonl 混入合法 JSON 非 dict 行 → `build_debug_graph` 在 `ev.get`（debug_graph.py:113）直接 AttributeError。而 debug_graph 恰是"journal 缺失时的 fallback 路径"——fallback 比主路径更脆。治理脚本 `scripts/lca-cli-shape.py:64-71` 的门限只看"是否 import 任一共享名"，debug_graph 因 import 了别的共享名被判合规，重复 loader 毫发无伤。
- Q4：debug_graph.py:24 跨模块 import 下划线私有的 `_safe_repr`（seam 名存实亡）；`load_spine_facts` 被 3 个命令 import 却不在 `__all__`（projection.py:222-229），治理脚本 docstring 与代码已漂移；`_DOMAIN_PREFIXES`（:28）手抄 contracts taxonomy（注释 :22-23 明示"so we do not import from contracts into CLI surface code"——**刻意的设计规则**），且同一文件另有 `_EP_PREFIX_FAMILIES`（:147）匹配语义还不一样。
- Q5：`load_spine_facts` 零测试；`_safe_repr` 零直接测试；`debug_graph._load_events` 只能绕过 interface 测（test_debug_graph.py:82 直接 import 私有函数）。

**C. daemon**（`daemon.py` 446 行 + `service.py`/`state.py`/`sudo.py`/`config.py`，逐行精读；PR #40 `44fbdd846` 已读）
- Q1：`start()` 一次调用触及 5 个模块，但邻接模块 interface 都比 implementation 浅（`Sudo` 门面、`ChangeReport` 内聚、`Service` Protocol）——健康的 depth。真跳点在 `daemon.py` 内部：`start` 把轮询/`_deploy_cli`/`_spawn` 混成一条方法，本文件内上下翻 300 行。
- Q2：`_cli_source_changed`（164-166）浅但真收敛点是三处重复的 `detect_changes("daemon_cli", ...)`（158/166/170）→ 收敛为一个私有 helper；`state.py:120-126` 的 `has_changed`/`save_stamp` 是零调用方的向后兼容别名 → 可删；`sudo.py` 的薄包装浅但有 locality（封装 chown 语义）→ 不动。
- Q3：`restart()`（130-133）= stop + `sleep(0.5)` + start，**"同一时间只活一个 daemon"的不变量没有任何 module 负责**——PR #40 刚修的"双 daemon 抢 device id"正是该不变量被破坏的后果，restart 路径今天仍可复现（pkill 生效慢于 0.5s → start 判定未运行 → 直接 spawn）。`_deploy_cli` 的裸 except 把 tsc/npm 失败吞成 False——fingerprint 再正确也定位不了哪步挂了。
- Q4：进程签名 `"node.*index.js.*connect"` 在 daemon.py:122/423 和 `user_cli.py:82,94` 三处硬编码（TS 改名即静默失效）；`_spawn`（385-430）f-string 生成脚本硬编码 PATH/`--token lca-local-host`（406）/log 路径，而 token 默认同时在 `host_runtime/config.py:47`——改凭证改两处；`_deploy_python_runtime`（344-352）硬编码依赖列表。
- Q5：`start()` 全链无测试；`_spawn` 脚本内容只能真跑验证；restart 竞态 mock 永远 pin 不住。

**Duplication scan（次要）：** `except Exception as exc:` 在 tools 下 7 文件出现但各处理不同，非机械重复；`new_id("obs")` 高频点均为异构 payload。**无 RA-001/RA-002 级 identical-builder 簇**——收敛类 idiom 本轮无新实例，符合 diversity quota 预期。

## Phase 2 — Self-grilling（每候选五项，写在评估里不在脑子里）

### RA-004（Strong）：删 `debug_graph._load_events` 私有复刻，改调 `load_spine_events`
- Constraints：不改变 debug-graph 人类输出；SpineRow 是 tolerant dict，下游 `ev.get` 兼容；fail-soft（跳过坏行）语义保留；不碰"CLI surface 不 import contracts"规则。
- Dependencies：调用方仅 `build_debug_graph`；test_debug_graph.py:82 直接 import 私有函数（必须改）；shape 脚本 `SHARED_PROJECTION_NAMES` 已含 `load_spine_events`。
- Shape：删除 debug_graph.py:46-62，`build_debug_graph` 改调共享 loader；测试改 import 共享函数；顺手修 `lca-cli-shape.py` docstring 漂移（补 `load_spine_facts` 进文档名单）。
- Test survival：test_debug_graph.py（CliRunner e2e）、test_projection.py（5 个测试钉住 loader 含 isinstance 守卫）。**新测试**：spine.jsonl 混入非 dict JSON 行（如 `42`）→ debug-graph 退出 0（钉住本次真 bug）。
- Deletion test：收敛——解析语义 + 守卫全宇宙只剩一处。✅

### RA-005（Worth exploring）：统一 projection.py 内两张域前缀表 + 一种匹配语义
- Constraints：**绝不 import contracts**（projection.py:22-23 是刻意规则，"contracts 常量"方案已否决）；`filter_by_domain` 的 substring 语义可能有调用方依赖（runs/debug.py:157 四域计数）——改语义前先跑它的测试。
- Dependencies：`filter_by_domain` ← runs/debug.py:32；`load_spine_facts` ← run_explain/run_replay/trace_show。
- Shape：模块内一张表 + 一种语义；保留 mirror 注释并注明语义选择理由。
- Test survival：test_projection.py；runs/debug 相关测试。
- Deletion test：收敛——execution_point→domain 映射单点。✅（Worth exploring：语义选择需谨慎验证。）

### RA-006（Strong）：给"单 daemon 不变量"一个家——`_kill_existing` 接缝 + 等待退出
- Constraints：保留 PR #40 行为（pkill 经 `Sudo.run`）；`user_cli.py` 的 stop_daemon 是 host-runtime 另一 concern——只收敛签名串，不碰它的 kill 流程；restart 仍返回 ServiceState。
- Dependencies：`service.py` 已有 `kill_tree`/`pid_alive` 原语（直接 leverage）；`user_cli.py:82,94` 共享签名串。
- Shape：模块级 `_CONNECT_PROC_PATTERN` 常量由 daemon.py 与 user_cli.py 共用；daemon.py 新增 `_kill_existing(pattern, timeout)`（sudo pkill + 轮询 pid_alive 至死亡）；`stop()`/`restart()` 走它；restart 删 `sleep(0.5)`。
- Test survival：test_daemon_stop_uses_sudo（mock 形状断言，可扩展断言等待）；**新测试**：pid_alive 由真转假的 mock 序列 → restart 在确认死亡后才 start。
- Deletion test：收敛——kill 语义 + "只活一个"不变量有了 owner。✅

### RA-007（Worth exploring）：`_spawn` 脚本模板泄漏 → 纯渲染函数 + 配置收敛
- Constraints：/opt/lca 部署目标不变；token 默认 `lca-local-host` 仍以 `host_runtime/config.py:47` 为单一来源；生成脚本行为不变。
- Dependencies：`DaemonService._spawn`；`DaemonConfig`（加字段或复用现有）。
- Shape：纯函数 `render_start_script(config) -> str`；token/路径进 DaemonConfig；`_spawn` 只负责写与拉起。
- Test survival：今天零测试钉住脚本内容 → **新测试**钉住渲染脚本包含配置 token/log 路径（"脚本长什么样"首次可测）。
- Deletion test：收敛——部署契约单点。✅（Worth exploring：config 字段 vs 模板参数的设计选择。）

### RA-008（Strong）：三 provider 壳表驱动收敛（先写测试再收敛）
- Constraints：**先证明 `@plugin` 发现机制能拾取动态生成的注册**——验收标准第 1 条就是这个测试；authority grant 各异（perceive 为 `context.read`）；observability descriptor 系 id 派生，无信息丢失。
- Dependencies：`plan_binding.bind_agent_from_scope` 读 `composer.*` 能力；tests/composer/test_plan_composer_providers.py。
- Shape：`[("lca-plan-brain-composer","composer.brain","plugin.serve",BrainComposer), ...]` 表 + 循环生成注册（若动态生成不被发现机制拾取，退化为 `_register_composer_plugin(...)` 工厂调 3 次——同样消除 ~100 行）。
- Test survival：test_plan_composer_providers.py（2 测试）；**新测试**：`setup()` 为每个 id provide 正确的 composer（Q5 发现的盲区，声明被测了装配没被测）。
- Deletion test：收敛——注册形状单点，第 4 个阶段不再复制样板。✅

### RA-009（Worth exploring）：`llm._inner` 私有访问 + 延迟 import 的接缝硬化（含 spike）
- Constraints：`instrument_llm` 幂等性必须保持；composer↔events 导入环真实存在（延迟 import 事出有因）；`TelemetryLLMAdapter` 内部属 observability。
- Dependencies：`TelemetryLLMAdapter`（infrastructure/observability/adapters）、model_visible adapter、`brain.py:65/74`。
- Shape：**先读 `TelemetryLLMAdapter` 再定**——候选方案：在 adapter 侧提供公开解包原语；用 contracts 层协议解开循环。spike 是 story 的一部分。
- Test survival：test_hook_resolution_path.py。
- Deletion test：不适用（非删除类，是接缝契约化）。Worth exploring：方案本轮未定。⚠️

## Phase 3 — Present

| ID | Files | Problem（friction） | Solution | Benefits（locality / leverage） | Strength |
|---|---|---|---|---|---|
| RA-004 | `cli/commands/observation/debug_graph.py:46-62`, `cli/commands/_shared/projection.py:67-108`, `scripts/lca-cli-shape.py` | `_load_events` 是共享 loader 的私有复刻，丢了 `isinstance(obj, dict)` 守卫；非 dict 行 → AttributeError。fallback 命令比主路径脆；治理门限误判合规 | 删复刻改调 `load_spine_events`；测试改 import；修 shape docstring 漂移 | 解析语义单点；"任何 run 都能出图"的设计承诺兑现；门限不再瞎 | **Strong** |
| RA-005 | `cli/commands/_shared/projection.py:28-43` vs `:147-150` | 同一概念两张表、两种匹配语义；`_DOMAIN_PREFIXES` 是 contracts taxonomy 的手抄镜像（刻意不 import contracts 的规则必须保留） | 模块内统一一张表一种语义；mirror 注释保留 | 同一 run 上两函数不再给出不同域集合 | **Worth exploring** |
| RA-006 | `cli/services/daemon/daemon.py:115-133`, `host_runtime/providers/user_cli.py:82,94` | "只活一个 daemon"无 owner；restart=stop+sleep(0.5)+start 靠 timing；PR #40 修的双 daemon 可复现；签名串三处硬编码 | `_kill_existing` 接缝（sudo pkill + 等待退出）；签名串收为常量共用 | restart 不再靠运气；回归被结构性消除 | **Strong** |
| RA-007 | `cli/services/daemon/daemon.py:385-430`, `cli/config/config.py:47` | `_spawn` f-string 硬编码 PATH/token/log；token 改两处；脚本内容不可测 | 纯 `render_start_script(config)`；token/路径进 DaemonConfig | 部署契约单点；脚本首次可单元测试 | **Worth exploring** |
| RA-008 | `plugins/composer/think/brain_provider.py`, `perceive/provider.py`, `act/body_provider.py`（各 66 行） | 三文件除 4 处外逐行相同；第 4 个阶段又要复制 | 表驱动生成注册（先测发现机制）；或工厂调 3 次 | −130 行样板；注册差异变数据可审计 | **Strong** |
| RA-009 | `plugins/composer/think/brain.py:65,74` | 直读 `TelemetryLLMAdapter._inner` 私有属性；局部 import 躲导入环——接缝靠非正式手段 | spike 后：adapter 公开解包原语；contracts 协议解环 | 接缝契约化；adapter 重构不再静默破坏 | **Worth exploring** |

**Top recommendation:** RA-004 first。真 bug（非 dict 行崩溃）、blast radius 最小（删一个函数，共享 loader 已有 5 个测试钉住）、验收机械可验证（非 dict 行回归测试）。其次 RA-006（真竞态，PR #40 的回归区）。

**Diversity quota:** 6 个故事中 5 个来自 friction walk（RA-004 测试性/复刻腐烂、RA-005 接缝镜像、RA-006 不变量无 locality、RA-007 跨接缝泄漏、RA-009 私有访问），仅 RA-008 为 duplication 类。✅ 不全是重复收敛。

**Stories written:** RA-004（P1）、RA-006（P2）、RA-008（P3）、RA-005（P4）、RA-007（P5）、RA-009（P6），`passes: false`，接 RA-001~003 续号。分支：`raphy/arch-20261006-2301`。

**Learnings for future iterations:**
- CLI surface 不 import contracts 是刻意规则（projection.py:22-23）：看到"镜像"先读注释，别把"统一成 import"当默认解。
- 共享接缝的私有复刻会静默腐烂（丢守卫）：治理脚本的"import 名门限"看不见它——deletion test 之外，fork 本身就是 smell。
- "sleep(0.5) 式 restart"是"不变量无 owner"的症状：修竞态要给不变量找家，不是调大 sleep。
- `@plugin` 动态注册先测发现机制再收敛——表驱动的前提是机制支持，验收标准第 1 条写死它。
- 任务简报里的路径可能错（本轮 `plugins/composition/composer` 实为 `plugins/composer`）：story 的 Files 以实测 `ls` 为准。
