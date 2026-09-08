# agent_lab → LCA plugin 体系收编：Design Spec / 实施计划

> **状态：** Approved（与 [ADR-0209](../adr/0209-agent-lab-cordis-unification.md) 2026-09-09 评审通过）
> **作者：** LCA Coding Agent
> **日期：** 2026-09-09
> **评审对象：** ADR-0209、Note [`2026-09-08-agent-lab-absorb-end-state`](../notes/proposed/seam/2026-09-08-agent-lab-absorb-end-state.md)、Note [`2026-09-09-colony-runtime-architecture-review-response`](../notes/plans/2026-09-09-colony-runtime-architecture-review-response.md)
> **关联：**
> - [ADR-0209](../adr/0209-agent-lab-cordis-unification.md)
> - [ADR-0206](../adr/0206-information-graph-kernel.md) §10 P7 阶段闭集迁移（前置依赖）
> - [ADR-0195](../adr/0195-platform-architecture-convergence.md) §4 SSOT 矩阵
> - [ADR-0186](../adr/0186-session-as-event-ssot.md) Session SSOT
> - [ADR-0194](../adr/0194-cognitive-loop-architecture-convergence.md) Loop 收敛

---

## 0. 摘要

按 ADR-0209 决策，把 `agent_lab/` 一次性收编进 LCA plugin 体系：

1. 消灭第二套 `@plugin` 装饰器（`agent_lab.plugins.base.GraphPlugin`）
2. 所有节点（≈96 个 plugin）迁为 LCA `@plugin`
3. Body / ToolRegistry / Executor / Transport / Session 装配移至 Bundle 上 `@plugin` provider
4. `act.execute` 等节点文件不再 `new SimpleBody`，只消费已 require 的句柄
5. Session 单轨：`set_publish_session` 唯一入口在 `lca/plugins/lab/session/provider/plugin.py`
6. `bundles/agent-lab-infoedge.yaml` / `profiles/agent-lab-infoedge.yaml` 保留至 §D delete-when 满足

**不做的**：见 §F（Reject 列表继承自 ADR-0209 §7）。

---

## A. 目标状态（吸收后）

### A.1 插件入口

```text
唯一入口：
  lca.harness.plugin_api.plugin  ──  Cordis 载体 + Manifest 审计

agent_lab.plugins.base 留存的符号：
  HookEvent（闭集枚举，lab runner 内部使用）
  fanout_hooks（仅在 LCA plugin setup() 内被调用）
  Bind（hook 选择器，仅 helper）

agent_lab.plugins.base 删除的符号：
  register_plugin / register_instance / register_fixture_instance
  unregister_instance / unregister_fixture_instance
  get_instance / get_fixture_instance / get_plugin_class / discover / resolve_plugin
```

### A.2 节点目录

```text
# Before
agent_lab/nodes/<area>/<name>/plugin.py        (96 个文件)
agent_lab/nodes/<area>/<name>/body.py          (仅 act/execute)
agent_lab/nodes/<area>/<name>/ops.py           (think 系列)
agent_lab/nodes/<area>/<name>/runtime_bind.py  (仅 act/execute)

# After
lca/plugins/lab/<area>/<name>/plugin.py        (96 个 @plugin)
lca/plugins/lab/<area>/<name>/ops.py           # 纯函数 helper；不写 plugin 注册
agent_lab/nodes/<area>/<name>/plugin.py        # 删除
agent_lab/nodes/<area>/<name>/body.py          # 删除
agent_lab/nodes/<area>/<name>/runtime_bind.py   # 删除
```

> **例外**：`agent_lab/nodes/` 完全删除。`graph/` `runtime/` `primitives/` 保留（编译器 / 递归解释器 / 不可变数据契约）。

### A.3 Bundle 拓扑

```text
profiles/web-standard.yaml                 # 不变（始终不挂 lab）

profiles/agent-lab-infoedge.yaml           # 增加 lab-* bundle
  bundles/base.yaml
  bundles/session-runtime.yaml
  bundles/observability-default.yaml
  bundles/declarative-phase-graph.yaml     # 0075 作为 dead Plan region（仅过 compile）
  bundles/web-app.yaml
  bundles/loop_cursor.spine_default.yaml
  bundles/event-bus-components.yaml
  bundles/lab-plugins.yaml                 # NEW: lab 工兵 plugin 集
  bundles/lab-act.yaml                     # NEW: Body / ToolRegistry / plan_ref / Transport
  bundles/lab-session.yaml                 # NEW: lab session provider
  bundles/agent-lab-infoedge.yaml          # 保留（loop driver 注册 + delete-when）
```

### A.4 Capability 闭集（`lab.*`）

见 ADR-0209 §1.4。完整列表建 spec [`capability-closed-set.md`](./capability-closed-set.md)（本 PR 系列内落地，含测试）。

---

## B. PR 拆分

> **总原则**：
> - 每个 PR 内部闭环（实现 + 消费者 + 测试 + 文档 + delete-when）
> - 每个 PR 不动 `web-standard`（lab Profile 独立）
> - 每个 PR 都加 §H 验收命令
> - 不留跨 PR 后门（删除与新增同 PR）

| PR | 标题 | 改动范围 | delete-when |
|---|---|---|---|
| **PR-A** | `refactor(lab): 把 GraphPlugin 收编为 LCA @plugin（hook helper 内置）` | 新增 `lca/plugins/lab/<kind>/plugin.py`（events / observers / parsers / semantic_router / control_slots / observation / memory_extract / tool_guard / session_log_emitter）；删除 `agent_lab.plugins.base` 的 plugin 注册面；helper 留 `lca.plugins.lab.internal` 私有 | `from agent_lab.plugins.base import GraphPlugin, register_plugin` = 0 |
| **PR-B** | `refactor(lab-act): act.* 工兵收编为 LCA @plugin；Body / ToolRegistry / plan_ref / Transport 拆为 provider` | `act.shape` / `act.authorize` / `act.observe` 迁 `@plugin`；`act.execute` 迁 `@plugin`，删除 `body.py`；新增 `lca/plugins/lab/act/body_provider`、`tools/provider`、`transport/provider`；新增 `bundles/lab-act.yaml`；`act.yaml` `factory:` 改 plugin id | `from lca.cognition.body|executor` 在 `agent_lab/nodes/` = 0；`build_body / run_body_act` 在 `agent_lab/` = 0 |
| **PR-C** | `refactor(lab-session): Session 单轨；删除 runtime_bind.global` | 删除 `runtime_bind.ensure_act_runtime`；新增 `lca/plugins/lab/session/provider/plugin.py`，setup 阶段 `set_publish_session`；新增 `bundles/lab-session.yaml` | `set_publish_session / global _PUBLISH_TOKEN` 在 `agent_lab/nodes/` = 0；`agent_lab_default` 构造 = 0 |
| **PR-D** | `refactor(lab): 全量节点收编（perceive/think/reflect/remember/session_log 等）` | 其余 92 个 plugin 全部迁 `@plugin`；新增 `bundles/lab-plugins.yaml`；`agent_lab/nodes/` 全部删除（仅留 graph/ runtime/ primitives/） | `agent_lab/nodes/` 目录为空（除 `__init__.py`） |
| **PR-E** | `refactor(lab): 删除 adapter / tools/registry 私有加载器；合并 capability 闭集文档` | 删除 `agent_lab/adapters/`；删除 `agent_lab/tools/registry.{py,yaml}`（由 `lca.plugins.lab.tools.provider` 接管）；新建 spec `capability-closed-set.md` + 测试；更新 `bundles/agent-lab-infoedge.yaml` / `profiles/agent-lab-infoedge.yaml` 头注释 delete-when | `agent_lab/adapters/` = 0；`tools/registry.{py,yaml}` = 0；spec 文件落地 |

### B.1 PR-A 详

**新增**：
- `lca/plugins/lab/events/plugin.py`（events sink）
- `lca/plugins/lab/observers/plugin.py`
- `lca/plugins/lab/parsers/plugin.py`
- `lca/plugins/lab/semantic_router/plugin.py`
- `lca/plugins/lab/control_slots/plugin.py`
- `lca/plugins/lab/observation/plugin.py`
- `lca/plugins/lab/memory_extract/plugin.py`
- `lca/plugins/lab/tool_guard/plugin.py`
- `lca/plugins/lab/session_log_emitter/plugin.py`（从 `agent_lab.nodes.session_log.plugin` 迁）
- `lca/plugins/lab/internal/hooks.py`（`fanout_hooks` / `Bind` / `HookEvent` 私有 helper）
- `bundles/lab-plugins.yaml`（仅 PR-D 时全集补齐；PR-A 仅含 events/observers/parsers/semantic_router/control_slots/observation/memory_extract/tool_guard/session_log_emitter）

**改动**：
- `agent_lab/plugins/base.py`：删除 plugin 注册面；保留 `HookEvent` / `fanout_hooks` / `Bind` / `HookContext`；改 import 路径为 `lca.plugins.lab.internal.hooks`（私有）。
- `agent_lab/nodes/session_log/plugin.py`：删除；功能迁 `lca/plugins/lab/session_log_emitter/plugin.py`。
- `agent_lab/graphs/configs/...yaml`：plugin 引用从 `kind:` 改为 `@plugin` 的 plugin id。
- `lca/plugins/events/publishers/_session_publish.py`：注释加 hook → spine EP 隔离说明（I-6）。

**测试**：
- `tests/plugins/lab/test_plugin_manifest.py`：所有新增 `lab.*` plugin 通过 Manifest 校验
- `tests/plugins/lab/test_no_second_decorator.py`：`from agent_lab.plugins.base import GraphPlugin / register_plugin` 在 `agent_lab/ lca/plugins/lab/` 仅允许在 helper 内部
- `tests/plugins/lab/test_hook_containment.py`：hook 失败不破坏 runner

**delete-when**：`from agent_lab.plugins.base import GraphPlugin, register_plugin, resolve_plugin` 在 `agent_lab/ lca/plugins/lab/` = 0。

### B.2 PR-B 详

**新增**：
- `lca/plugins/lab/act/shape/plugin.py`（从 `agent_lab/nodes/act/shape/plugin.py` 迁，装饰 `@plugin`）
- `lca/plugins/lab/act/authorize/plugin.py`（同）
- `lca/plugins/lab/act/execute/plugin.py`（同；`body.py` 删除）
- `lca/plugins/lab/act/observe/plugin.py`（同）
- `lca/plugins/lab/act/ops.py`（`_tool_intent` / `_normalize_tool_calls` 等纯函数）
- `lca/plugins/lab/act/body_provider/plugin.py`（从 `body.build_body` 迁出，组装 `lab.body / lab.safe_executor / lab.transport`）
- `lca/plugins/lab/tools/provider/plugin.py`（YAML 装载 LabToolRegistry → `SimpleToolRegistry`）
- `lca/plugins/lab/transport/provider/plugin.py`（`InternalTransport` + 已注册 agents）
- `bundles/lab-act.yaml`（含 body provider / tool registry / transport provider 三入口）

**改动**：
- `agent_lab/nodes/act/{shape,authorize,execute,observe}/plugin.py`：删除（迁完即删）
- `agent_lab/nodes/act/execute/body.py`：删除
- `agent_lab/graphs/configs/act.yaml`：`factory:` 改 plugin id
- `agent_lab/runtime/runner.py`：调用 `lab.act.execute.handle`（provider 已注入）而非直接 import `body.build_body`

**测试**：
- `tests/plugins/lab/act/test_execute_verdict_split.py`：4 类 verdict 分岔
- `tests/plugins/lab/act/test_body_provider.py`：Body / Executor / Transport 三件套在 setup 阶段正确装配
- `tests/plugins/lab/act/test_act_yaml_resolves.py`：`factory: lab.act.execute` 等能 resolve 到 `@plugin`
- `tests/plugins/lab/act/test_no_lca_cognition_import.py`：`agent_lab/nodes/act/` 无 `from lca.cognition.*` import

**delete-when**：`from lca.cognition.body|executor|session` 在 `agent_lab/nodes/act/` = 0；`build_body|run_body_act` 在 `agent_lab/` = 0。

### B.3 PR-C 详

**新增**：
- `lca/plugins/lab/session/provider/plugin.py`
  - `@plugin(id="lab.session.provider", requires=["run_loop_driver_registry"], provides=["lab.session"], layer="L4", kind=PluginKind.PROVIDER, effects=EffectClass.NONE)`
  - `setup()`:
    - `run_session = ctx.require("run_loop_driver_registry").get_active()`
    - `bound = getattr(run_session, "event_session", None)`
    - `bridge = getattr(bound, "bridge", None)`
    - `inner = getattr(bridge, "inner", None) if bridge is not None else None`
    - 若 `callable(getattr(inner, "append", None))`：取 `inner`；否则若 `bound.append` 可调：取 `bound`；否则**抛 `RuntimeError("lab session provider requires active run session with append")`**。
    - `set_publish_session(session)`；返回值作 disposer token。
    - `ctx.provide("lab.session", session)`
- `bundles/lab-session.yaml`

**改动**：
- `agent_lab/nodes/act/execute/runtime_bind.py`：删除 `ensure_act_runtime` / `reset_act_runtime_for_tests`；`plan_ref()` 常量迁 `lca/plugins/lab/act/body_provider/config.py`。
- `agent_lab/run.py`：调用 `LabRuntime.bind_session()` 改为「让 lab session provider 完成」（直接用 LCA 启动路径而非 lab 自己 bootstrap）。
- `agent_lab/runtime/runner.py`：移除 `ensure_act_runtime()` 调（迁 `bundles/lab-session.yaml` setup 阶段）。

**测试**：
- `tests/plugins/lab/session/test_provider_set_publish.py`：setup 阶段 `set_publish_session` 被调
- `tests/plugins/lab/session/test_missing_active_session_fails_loud.py`：active session 缺失时 `RuntimeError`
- `tests/plugins/lab/session/test_no_global_token.py`：`runtime_bind.py` 不再有 `global _PUBLISH_TOKEN`

**delete-when**：`set_publish_session|global _PUBLISH_TOKEN` 在 `agent_lab/nodes/` = 0；`ensure_act_runtime` 在 `agent_lab/` = 0。

### B.4 PR-D 详

**新增**（每个 plugin 一个文件）：
- `lca/plugins/lab/perceive/{sense,resolve,policy,memory,trim,commit}/plugin.py`
- `lca/plugins/lab/think/{expose,reason,classify,guard}/plugin.py`
- `lca/plugins/lab/reflect/{critique,extract,join}/plugin.py`
- `lca/plugins/lab/remember/{admit,commit,fold_history,snapshot}/plugin.py`
- `lca/plugins/lab/model_eye/{see,trust_classify,guard,freeze,shape}/plugin.py`
- `lca/plugins/lab/model_visible/{prompt_assemble,manifest_commit,messages_merge,history_attach}/plugin.py`
- `lca/plugins/lab/llm/{call_llm,assemble_messages}/plugin.py`
- `lca/plugins/lab/control/{route_on,barrier,join,discard,observe_checkpoint,observe_wildcard_node,stop_decide,stop_focus_node,act_execute_node,act_authorize_node,act_budget_node,act_constrain_node,act_safe_boundary_node,perceive_context_node,remember_admit,think_guard}/plugin.py`
- `lca/plugins/lab/event/{emit,tail}/plugin.py`
- `lca/plugins/lab/lineage/{trace_edge_fire,trace_node_start,trace_node_end,trace_subgraph_enter,trace_subgraph_exit}/plugin.py`
- `lca/plugins/lab/session_log/{append_node_start,append_node_end,append_edge_fire,append_subgraph_enter,append_subgraph_exit,append_decision,append_observation,append_reflection,append_tool_result,append_before_compile,append_after_compile,append_checkpoint,fanout_observers,register_observer,consume_events,snapshot_events,attach_sink,flush_sink,fold_header,session_seq}/plugin.py`
- `lca/plugins/lab/passthrough/{identity,constant,dedup,rank,redact,select,prefix,identity_v2,dedup_v2,rank_v2,redact_v2,select_v2,prefix_v2}/plugin.py`（仅 passthrough 纯变换；先评估是否值得独立 plugin——见 §I open question）
- `lca/plugins/lab/tool/{expose_schemas,resolve_tool,grant_check,registry_loader}/plugin.py`

**改动**：
- 全部 `agent_lab/nodes/<area>/<name>/plugin.py` 删除
- `agent_lab/graphs/configs/*.yaml` 的 `factory:` 改 plugin id

**测试**：
- `tests/plugins/lab/test_all_nodes_resolve.py`：图 B 所有 `factory:` 都能 resolve 到 `@plugin`
- `tests/plugins/lab/test_no_agent_lab_nodes_dir.py`：`agent_lab/nodes/` 仅留 `__init__.py`（或彻底删除该目录）
- `tests/plugins/lab/test_actor_imports_clean.py`：`from lca.*` 在 `lca/plugins/lab/` 仅允许在 provider plugin 内（Body / Transport / ToolRegistry 装配处），不允许在 execute plugin 内

**delete-when**：`agent_lab/nodes/` 目录只剩 `__init__.py`（或彻底删除）。

### B.5 PR-E 详

**删除**：
- `agent_lab/adapters/`（整目录）
- `agent_lab/tools/registry.py`（合并入 `lca.plugins.lab.tools.provider`）
- `agent_lab/tools/registry.yaml`（由 `bundles/lab-act.yaml` 的 `tools_yaml` 携带，或由 lab 专用 Profile 直接 inline `entries.config.tools`）

**新增**：
- `docs/specs/capability-closed-set.md`：登记 `lab.*` capability key 闭集；`lab.*` 命名规则；新增流程（必须先 ADR）。
- `tests/architecture/test_capability_closed_set.py`：
    - `lca.contracts.capabilities.cap_key("lab.*")` 全部可枚举
    - 新增 `lab.*` capability 必须在本文件 + 测试登记

**改动**：
- `bundles/agent-lab-infoedge.yaml` 头注释更新 delete-when（指向 ADR-0209 §6）
- `profiles/agent-lab-infoedge.yaml` 头注释更新 delete-when（同上）
- `lca/plugins/loop/driver/infoedge/plugin.py` 头注释更新（指向 ADR-0209 §6）

**测试**：
- `tests/plugins/lab/test_capability_closure.py`：Profile 解析后 capability 闭集 ⊇ YAML `capabilities.requires`
- `tests/architecture/test_lab_capability_closed_set.py`：登记与代码同源

**delete-when**：见 ADR-0209 §6（全 7 条）。

---

## C. Capability 闭集（首批）

> 完整列表见 [`capability-closed-set.md`](./capability-closed-set.md)（PR-E 落地）。

```text
# 装配面（provider provides）
lab.session                 # 活动 Session（注入；由 lab session provider 在 setup 阶段 set_publish_session）
lab.plan_ref                # 字符串 plan_ref
lab.body                    # SimpleBody（来自 lca.plugins.composer.act.body_provider）
lab.tool_registry           # LabToolRegistry
lab.safe_executor           # PipelineSafeExecutor
lab.transport               # InternalTransport + 已注册 agent

# 工兵产出（每个 out 端口一个 capability key）
lab.act.shape.out:intent
lab.act.authorize.out:authorized
lab.act.execute.out:receipt
lab.act.observe.out:observation
lab.perceive.sense.out:sensor_items
lab.perceive.resolve.out:sensors
lab.perceive.policy.out:policy
lab.perceive.memory.out:memory_items
lab.perceive.trim.out:trimmed
lab.perceive.commit.out:committed
lab.think.expose.out:messages
lab.think.expose.out:tools
lab.think.reason.out:response
lab.think.classify.out:decision
lab.think.guard.out:decision
lab.think.guard.out:think_signal
lab.reflect.critique.out:critique
lab.reflect.extract.out:lesson
lab.reflect.join.out:reflection
lab.remember.admit.out:fact
lab.remember.commit.out:remembered
lab.remember.fold_history.out:history
lab.remember.snapshot.out:snapshot

# plugin hook 入口（注册面 provider）
lab.hooks.compiletime.before_compile
lab.hooks.compiletime.after_compile
lab.hooks.runtime.node_start
lab.hooks.runtime.node_end
lab.hooks.runtime.after_node_execute
lab.hooks.runtime.edge_fire
lab.hooks.runtime.subgraph_enter
lab.hooks.runtime.subgraph_exit
lab.hooks.semantic.on_decision
lab.hooks.semantic.on_observation
lab.hooks.semantic.on_reflection
lab.hooks.semantic.on_event
```

---

## D. delete-when（同 ADR-0209 §6）

`profiles/agent-lab-infoedge.yaml` + `bundles/agent-lab-infoedge.yaml` + `lca/plugins/loop/driver/infoedge/` 在以下条件**同时**满足时可删除：

1. `agent_lab.plugins.base` 不导出 `register_*` / `GraphPlugin`
2. `agent_lab.nodes/**/plugin.py` 无 `from lca.cognition|executor|session` import
3. `lca/plugins/lab/<area>/<name>/plugin.py` 全量覆盖图 B 所有 `factory:`
4. `rg 'agent_lab\\.runtime\\.runner' lca/ lca_kernel/ profiles/ bundles/` = 0
5. `web-standard` 与 `agent-lab-infoedge` Profile 的 capability 闭集之差只剩 `lab.*`
6. `python -m agent_lab.run` 不再进 Gateway/生产入口（仅保留自检 CLI）
7. ADR-0206 §10 P7 阶段闭集迁移完成

---

## E. 验收（每 PR 必过）

| # | 验证 | 命令 |
|---|---|---|
| 1 | lint-imports | `./scripts/lca-ops lint-imports`（无新增失败） |
| 2 | plugin shape | `./scripts/lca-ops audit-plugin-shape`（新增 `lab.*` 全部通过 Manifest 校验） |
| 3 | capability 闭包 | `python -m agent_lab.run --describe --target graph:act` 列出所有 `requires / provides` |
| 4 | 节点纯度 | `rg "from lca\\.cognition\\|executor\\|session" agent_lab/nodes/` = 0 |
| 5 | 节点纯度 | `rg "= (SimpleBody\\|PipelineSafeExecutor\\|InternalTransport\\|Session)\\(" agent_lab/nodes/` = 0 |
| 6 | Session 单轨 | `rg "set_publish_session\\|global _PUBLISH_TOKEN" agent_lab/nodes/` = 0 |
| 7 | 第二 plugin 体系 | `rg "from agent_lab\\.plugins\\.base import" agent_lab/ lca/plugins/lab/` 仅在 helper 内部 |
| 8 | 拓扑 | `./scripts/lca-ops inspect-tree profiles/agent-lab-infoedge.yaml` 出现 `lab.*` plugin |
| 9 | Profile 差集 | `python -c "diff_capabilities(web_standard, agent_lab_infoedge)"` 仅 `lab.*` 差异 |
| 10 | lab CLI 自检 | `python -m agent_lab.run act` 通过；`python -m agent_lab.run --describe --target graph:agent_loop` 列出全部 capability 关系 |

---

## F. Reject（继承 ADR-0209 §7）

- 保留 `agent_lab.plugins.base.GraphPlugin` 作 helper
- 在 `act.execute` 里继续 `new SimpleBody`
- 把 Body / Executor 放进 `lab.act.execute` 同文件 setup
- 新增 `colony/` / `Pheromone` / `ActionValue`
- 暴露 `tools/registry.yaml` 后还在 lab 内部保留一份
- 「双轨运行、不收编」
- 把 `set_publish_session` 留在 `runtime_bind.py` 标记 deprecated
- 让 `web-standard` 也挂 `bundles/lab-plugins.yaml`

---

## G. 风险与代价

**正**：与 ADR-0209 §9 一致。

**代价**：≈96 plugin 迁移；5 个新 Bundle；`agent_lab/` 目录结构重整。

**风险与缓解**：
- 大规模 plugin codemod → **永远双轨 PR-A ~ PR-E**（每 PR 仅影响 lab Profile），web-standard 始终不动
- `from lca.cognition` 散落难以全扫 → lint-imports `lab-node-purity` 规则 + pre-push grep
- capability key 名漂移 → §C 闭集 + spec `capability-closed-set.md` 测试守护
- 新 Bundle 体积膨胀 → Bundle 内 plugin 全部 `@plugin` 化，`why-plugin` 一键回答归属

---

## H. 验证矩阵（合并类型 → 最低验证）

| 变更 | 最低验证 | 必须追加 |
|---|---|---|
| 新增 @plugin（PR-A/B/C/D/E） | ruff + ruff format + plugin-shape audit + `tests/plugins/lab/test_*` | Manifest 校验 + capability 闭集测试 + lab CLI 自检 |
| 修改 Bundle 拓扑（PR-A/B/C/D） | inspect-tree + lint-imports | 启动审计 + `why-plugin` 校验 |
| 删除文件（PR-A/B/C/D/E） | `rg` 静态扫描 = 0 | delete-when 测试 + Pre-push check |
| Spec / ADR（PR-E） | `verify_doc_slop` + `verify_doc_budgets` | 链接修复 + 索引更新 |

Pre-push 必跑（参考 [.agents/skills/lca-pre-push-checks](../../.agents/skills/lca-pre-push-checks/SKILL.md)）：

```bash
./scripts/lca-ops lint-imports
./scripts/lca-ops audit-plugin-shape
./scripts/lca-ops notes-audit
python -m agent_lab.run --describe --target graph:agent_loop
python -m agent_lab.run act
```

---

## I. Open Questions（跃迁 Accepted 前必答）

1. `agent_lab/passthrough/` 的 8 类纯变换是否值得独立 `@plugin`？评估标准：
   - 是否需要 capability 闭集证明「passthrough 在治理边界外」
   - 是否会被替换为 LCA 已有的等价 provider
   - 答案倾向：保留为 `lca.plugins.lab.passthrough.*` plugin（受审计），不直接复用 LCA pipeline 工具
2. `agent_lab.runtime.runner` 在收编后是否仍暴露为独立 RunLoopDriver target（`infoedge`），还是统一并入 `web-standard` 的 `RunLoopDriver`？
   - 答案倾向：保留 `infoedge` target 至 ADR-0206 P7 完成后合并；本系列 PR 不动 `lca/plugins/loop/driver/infoedge/`
3. LabRunDriver 在 `web-standard` 启动时如何 fail-loud「你挂的是 lab Profile」，避免误流量进 lab 图？
   - 答案倾向：lab Provider 在 setup 阶段 `assert profile_id == "agent-lab-infoedge"`，否则 `RuntimeError`
4. capability 闭集 `lab.*` 与 ADR-0110 plugin contract 的命名纪律（9 群归属 + 四维分解）是否需要新 PRD 文档？
   - 答案倾向：PR-E 一并落档 `capability-closed-set.md`，与 `docs/architecture/functional-group-mapping.md` 同源

---

## J. 跃迁 Acceptance（ADR-0209 升 Accepted 的硬条件）

- PR-A ~ PR-E 全部合并
- §D delete-when 全 7 条满足
- §E 验收 1–10 全部绿
- `capability-closed-set.md` 落地 + 测试守护
- `web-standard` Profile capability 闭集审计：`why-plugin lca-loop-infoedge` 在 `web-standard` 下 = "not in this profile"
- AGENTS.md §6 验证矩阵对 PR 类型的最低要求全部满足

---

## K. 相关文档索引

- ADR-0209（本文配套）
- ADR-0206 信息图内核
- ADR-0186 Session SSOT
- ADR-0194 Loop 收敛
- ADR-0195 平台架构收敛
- ADR-0110 plugin contract 命名
- ADR-0068 CompiledRunPlan
- ADR-0075 阶段图
- ADR-0090 / 0091 Session / Follow-up 控制器
- Note `2026-09-08-agent-lab-absorb-end-state`（吸收契约）
- Note `2026-09-09-colony-runtime-architecture-review-response`（拒绝 colony 层）
- Spec `0194-0195-implementation-plan.md`（PR 命名 / 轨道范本）
- `.agents/skills/lca-pre-push-checks`（pre-push 流程）