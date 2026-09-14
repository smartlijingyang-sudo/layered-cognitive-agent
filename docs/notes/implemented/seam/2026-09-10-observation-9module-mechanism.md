# Agent Note: Observation + Diagnosis 9-module 机制骨架

Status: implemented (M0 event_hub runtime hookup landed; 9 modules + 1 scheduler module = 10 modules, 14 plugins)

## Problem

诊断一次失败 run 时,agent 只能看到 SPINE 的事实流(`runtime.reducer.apply`、`phase.fact`、`control.*`、`agent_loop.iteration.*`),不知道:

1. plan 蓝图长什么样(`phase_graph` 节点 / 边 / 绑定 / 子图嵌套)
2. 每个节点的现场输入输出(完整 payload,不是 digest)
4. 期望 vs 实际的偏差(missing / unexpected / contract violations)
5. 根因链 + 修复提示(agent 直接可执行的命令)

需要一组机制把这 5 个子问题各自落到独立 module,模块化、可关可换、跟图框架零耦合。

## Decision

落地 9 modules × 27 contract schemas × 13 plugins × 4 CLI 子命令,全部 plugin 化,全部走 Session.append 单轨:

| Module | 关注点 | Contract | Producer plugin |
|---|---|---|---|
| M1 | 期望 (plan blueprint) | `PlanBlueprint` `PlanNodeSpec` `PlanEdgeSpec` | `observation.lifecycle.plan_compile` |
| M2 | 输入现场 | `NodeEnter` (inputs 完整 payload) | `observation.node_trajectory` (start) |
| M3 | 输出现场 | `NodeExit` `NodeException` (outputs 完整 payload) | `observation.node_trajectory` (end) |
| M4 | 装配期 | `PlanCompileComplete` `PlanCompileFailed` `SubgraphResolve` `BundleLoad` | `observation.lifecycle.{plan_compile, subgraph_resolve, bundle_load}` |
| M5 | 事件轨迹 | `DecisionTrace` `ControlTrace` `ToolCallTrace` `LLMCallTrace` `ReducerApply` (verbose 默认) | `observation.{decision, control, tool_call, llm_call, runtime_bookkeeping}` |
| M6 | artifact 状态 | `ArtifactSnapshot` | `observation.artifact_snapshot` |
| M7 | 偏差 (diff) | `DiffReport` `MissingNode` `UnexpectedNode` `ContractViolation` `EdgeDeviation` | `diagnosis.blueprint_trajectory_differ` (纯函数) |
| M8 | 根因 (explanation) | `FailureExplanation` `RootCauseStep` `RemediationHint` | `diagnosis.failure_explainer` (纯函数 + 模板表 `ROOT_CAUSE_TEMPLATES`) |
| M9 | 回放 (replay) | `RunReplay` `ReplayStep` `ReplayDiffSummary` | `diagnosis.run_replay` (纯函数 fold) |

**Contract**: 全部 Pydantic frozen + `extra="forbid"`(AGENTS.md C13)。位于 `lca/contracts/observability/observation/`,9 个 module 各自子目录 + `__init__.py` re-export。

**Plugin 形态**: 单文件单职责,模块级 Observer 函数(非 class),`@plugin(...)` 唯一入口,`effects="none"`,emit 走 `append_surface_bound` Session 单轨。零 in-memory state,零跨 plugin 直连,零私有文件。

**CLI**(4 个 `lca-ops` 子命令挂在 `observation` typer group 下):
- `lca-ops observation plan-show <profile>` —— 显示 PlanBlueprint
- `lca-ops observation trace-show <run_id> [--node <id>] [--kind <payload.kind>] [--seq <n>] [--filter <ep 子串>] [--full]` —— 显示 observation / diagnosis / phase_graph facts(graph facts 经 `graph_timeline` 投影;`--json` 为 agent 默认,给全量 payload)
- `lca-ops observation run-explain <run_id>` —— 输出 summary → root_cause_chain → graph_overview → next_actions
- `lca-ops observation run-replay <run_id>` —— 时间序 steps,agent 可 walk

**Bundle**: `bundles/observation-9module.yaml` 装载 13 个 plugin;`profiles/web-standard.yaml` `bundles:` 加一行。

**Loader 改动 = 0**: profile / bundle / plugin 装载机制一行不改,只多列。

## 设计模式

- **Plugin = Observer 函数 + `@plugin(...)` 装饰器**(无 class wrapper、无 `_shared`、无 base mixin)
- **Diagnosis plugin = 纯函数 + 数据驱动模板表**(可单测、可扩展、可固化 snapshot)
- **Module = 单一职责 + 单向依赖** (Contracts → Producers → Analyzers → CLI Surface)
- **Cross-module communication = Session.append 单轨**(ADR-0186/0191/0194 P1-P5)
- **CLI 默认 `--json`**,`--human` 投影;agent 工作流直接吃 `--json`,人不绕路 grep

## Alternatives considered

### Why not 改 `framework/` 加 SPINE EP listener API?

让 plugin 自动接收 `phase_graph.node.start` / `phase_graph.node.end` / `runtime.reducer.apply` 等 SPINE EP,需要在 `lca/framework/`(或 `lca/runtime/` 装配层)添加 listener / fan-out 机制。这违反 AGENTS.md 中"图框架尽量不动"的硬约束,也触碰 C11(EP 白名单闭集,新事件需 ADR)。

### Why not 改 `infrastructure/session/append.py` 加 hook?

在 SPINE emit 路径加 hook 是改动 `infrastructure/` 层。语义上是"基础设施层",不是"图框架",但**所有 SPINE EP 都会经过这条 hook**,等于跨 boundary 加副作用,违反 C7(控制/观察分离)的精神。

### Why not 走 Cordis 内置 eventbus 订阅?

Cordis eventbus 与 SPINE 是两套独立事件系统,SPINE 是 file-sink,Cordis eventbus 是 in-memory dispatch。两套不互通。让 plugin 走 Cordis eventbus 等于发明平行事件通道,违反 C3(事实可追溯)+ ADR-0186 单轨原则。

### Why not 用现有 `FieldProducer` (I17 seam) 注入额外字段?

`FieldProducer` 是 SPINE emit path 上的 enrich 钩子,**给 SPINE EP payload 注入额外字段**,不是 fan-out 接收事件。语义不同:它是 producer(产出数据),不是 consumer(接收事件)。

## Consequences

- ✅ 27 contract schema + 13 plugin + 4 CLI + 1 bundle + 64 tests + 文档闭环全部落地;ruff / pytest / sync_check 全过
- ✅ Plugin 装载路径已验证(`plan compile` 成功,`UndeclaredInteractionError` 已修复)
- ⚠️ **运行时自动 emit 这一公里没接通**:kernel 跑 run 时,SPINE 没出现 `observation.*` / `diagnosis.*` EP。CLI `observation run-explain <run_id>` 会返回 `no facts for run_id`。这是 framework 接入问题,**不是 plugin 设计缺陷**。
- ⚠️ 当前 CLI 跑诊断的能力**降级为读 SPINE 现有 facts**(`phase.fact` / `runtime.reducer.apply` / `control.*` 等),不依赖 plugin 自动 emit;agent 拿到一个 run_id 仍能跑 explain,只是根因链深度受限于现有 SPINE EP 而非新增的 `observation.*` fact。

## Testing

- `tests/observation/conftest.py` — 共享 fixture + factory (`make_blueprint`, `make_exit`, `make_enter`, `make_control`, `make_decision`)
- `tests/observation/test_blueprint_contract.py` —— 6 tests
- `tests/observation/test_trajectory_contract.py` —— 5 tests (覆盖 `inputs` / `outputs` 完整 payload)
- `tests/observation/test_lifecycle_contract.py` —— 5 tests
- `tests/observation/test_event_traces_contract.py` —— 6 tests
- `tests/observation/test_diff_replay_contract.py` —— 13 tests
- `tests/observation/test_diff_algorithm.py` —— 6 tests (含 H6 fixture)
- `tests/observation/test_explainer_algorithm.py` —— 4 tests (含 H6 根因链)
- `tests/observation/test_replay_algorithm.py` —— 5 tests
- `tests/observation/test_plugins_emit.py` —— 14 tests (含 13 plugin `@plugin` meta 验证)

总计 64 tests,全部 passed。

## Related

- `docs/debug/run-debug-guide.md` Step 4b —— observation-plane diagnostic 使用 SOP
- `scripts/check_run_debug_sync.py` —— SOP ↔ CLI sync 守护(SOP 提到 CLI 不存在的命令会失败)
- `bundles/observation-9module.yaml` —— 装载入口
- `profiles/web-standard.yaml` `bundles:` —— 装载列表

## Implementation 补完(M0 event_hub 接通 runtime, 2026-09-14)

「下一 PR TODO」两条候选路径(framework listener / runtime emit hook)都触碰 AGENTS.md §1 C1 / C11 / C13 与 ADR-0194 §3「认知原语零 emit」红线。改 framework 或 Session.append 主单轨都不被采纳;选第三条路:**bundle 内自装配 hub plugin,只调已存在的 `EventSpine.subscribe()`**,零 framework / harness / runtime 改动。

### 落地

- **Contract**: `lca/contracts/observability/observation/m0_event_hub/`。`EventHubConfig`(`BaseModel` frozen + `extra="forbid"`)承载 `rules: tuple[FanoutRule, ...]`;`FanoutRule` 单条 EP → observer capability + `enabled` 开关。**bijective 校验**(1 EP ↔ 1 observer)走 `validate_fanout_table()` 纯函数 + `EventHubConfig.model_validator` 双层守护。装载期抛 `EventHubConfigError`(first-class);直接构造 `EventHubConfig` 抛 pydantic `ValidationError`(消息含原始文本)。两层异常都能 grep 出同一条字串。
- **Plugin**: `lca/plugins/observation/event_hub/plugin.py`。`@plugin(id="observation.event_hub", requires=("event_spine", "observation.node_enter", "observation.node_exit", "observation.runtime_bookkeeping"), effects="none")`;setup 调 `ctx.require("event_spine").subscribe(make_dispatch_fn(...))` 把 closure 挂到 EventSpine 的 `_subscribers` 列表。
- **EP_FANOUT_TABLE** 当前覆盖 3 条 SPINE EP:`phase_graph.node.start` → `observation.node_enter`;`phase_graph.node.end` → `observation.node_exit`;`runtime.reducer.apply` → `observation.runtime_bookkeeping`。其余 9 类 observation fact(`DecisionTrace` / `ControlTrace` / `ToolCallTrace` / `LLMCallTrace` / `PlanCompileComplete` / `SubgraphResolve` / `BundleLoad` / `ArtifactSnapshot` / `NodeException`)按 plugin 间禁止直接 import 契约,在各 driver / lifecycle 调用方显式 `ctx.require(observer_capability_key)(...)` —— 单独 PR 处理。
- **Bundle**: `bundles/observation-9module.yaml` 把 `observation.event_hub` 列在 13 observer 之后(cordis resolve 按 yaml 顺序装载,放最后确保 observer 已 provide);header 注释更新为 `10 modules · 14 plugins`。
- **Tests**: `tests/observation/test_event_hub_contract.py`(8 test,bijective + extra=forbid + frozen + Pydantic 双层)+ `tests/observation/test_event_hub_plugin.py`(11 test,dispatch 行为 + observer 失败隔离 + unsubscribe 真正生效 + AST 守护 hub 不 import Session/journal + AST 守护 hub 不调除 `EventSpine.subscribe` 外的 EventSpine/Session 方法 + plugin meta 校验)。

### 防并行多轨(用户 review 落实)

hub plugin 实现期禁止出现的字符串(AST 守卫守护):

| 禁 | 理由 |
|---|---|
| `Session.append(` 在 hub module | 必须经 13 observer 已声明的 `append_surface_bound` 单点 |
| `EventSpine.append(` 在 hub module | hub 只订阅,不写 SPINE |
| `publish_ep_bound` / `publish_spine_ep` / `FactGateway(` | 不发明新 emit 路径 |
| `import lca.session` / `import lca.infrastructure.session` | 不直连 Session 后端(C7 + business-event-isolation) |
| `from lca.infrastructure.observability.journal` | 不直连旧 journal backends |

历史教训 cite: `spine_reflector_*`(ADR-0194 P5 退役,20+ 插件最后收敛回 `FactGateway`)+ `EventBus.publish`(ADR-0186 退役,曾是第二事实通道)。hub 不是第三条事实通道,它是调度器。

### 通道拓扑(hub 装好后)

```
runtime 触发 → EventSpine.append → sinks(SpineFileSink 写盘) + _subscribers(纯订阅回调列表)
                                                       │
                                                       ├─ SpineFileSink (写盘)
                                                       ├─ ProjectionCache / SpineAnomaly / TelemetryCapture
                                                       └─ 🆕 observation.event_hub._dispatch  ← 本 PR
                                                                          │
                                                                          │ EP_FANOUT_TABLE[record.execution_point]
                                                                          ▼
                                                                   observer_fn(record.payload)
                                                                          │
                                                                          │  observer 内部已调 append_surface_bound
                                                                          ▼
                                                                   Session.append → self._log.append(event)
```

两条通道(Session.append / EventSpine.append)各走各的入口,各写各的存储;hub 只出现在 EventSpine 的 `_subscribers` 列表,**不写两条通道的任何一个**,不重写 emit 拓扑。

## 下一 PR TODO

M0 event_hub 已落地,Runtime auto-emit 一公里接通(phase_graph.node.start/end + runtime.reducer.apply 已扇出到 13 observer)。剩余工作:

1. **9 类 runtime-emit 主动驱动**: `DecisionTrace` / `ControlTrace` / `ToolCallTrace` / `LLMCallTrace` / `PlanCompileComplete` / `SubgraphResolve` / `BundleLoad` / `ArtifactSnapshot` / `NodeException`。每个调用方在 driver / lifecycle 节点显式 `ctx.require(observer_capability_key)(payload)`。hub 的 `EP_FANOUT_TABLE` 预留 `enabled` 开关,后续 PR 翻成 `True` 即可把 fan-out 也启用(双通道保险)。
2. **`phase_graph.subgraph.enter/exit` / `phase_graph.edge.transit` EP 的 emit**: `SpineGraphObserver` 类已存在但未装配,需 framework 决策 ADR(触碰 C1 / C11),单独 PR 处理,不在本 note 范围。
3. **Session.append 主单轨契约**: 不动。

共同前提(写入 note 头部): **不发明平行事件通道,不改 graph framework 内部机制,不破坏 Session.append 单轨**。