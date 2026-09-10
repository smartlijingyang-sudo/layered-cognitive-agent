# Agent Note: Observation + Diagnosis 9-module 机制骨架

Status: implemented

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
- `lca-ops observation trace-show <run_id> [--node <id>] [--filter kind=<kind>]` —— 显示 observation facts
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

## 下一 PR TODO

让运行时自动 emit 接通。两条可行路径(需要 ADR):

1. **Framework 加 SPINE EP listener API**(最干净,但需要 ADR + 改 `lca/framework/` 或 `lca/runtime/` 装配层)
2. **Runtime 装配层在 emit SPINE EP 时调 `ObservationHub.notify(ep, payload)`**,hub 自己注册 fan-out(改 `infrastructure/session/append.py`,也需要 ADR)

两条路径共同前提:**不发明平行事件通道,不改 graph framework 内部机制,不破坏 Session.append 单轨**。