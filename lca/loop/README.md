# LCA Agent Loop — 人读入口

> 权威决策：[ADR-0194](../../docs/adr/0194-cognitive-loop-architecture-convergence.md)  
> 拓扑配置：[bundles/declarative-phase-graph.yaml](../../bundles/declarative-phase-graph.yaml)

## 1. 职责

Turn 驱动与事实投递：`driver.py` 推进一次 iteration，`fact_gateway.py` 是经
`FactGateway` 到 `Session.append` 的唯一事实写入口，`emit/` 与 `commit/` 提供
spine EP 投递与提交收据，`transport.py` 承担 transport 面与 `kernel.run` 生命周期事实的投递；
`control/` 目前只有说明文档，尚无模块。

## 2. 不负责

- 认知算法本体（`lca/cognition`：Brain / Body / Memory / Gate）
- 控制面 State 单写（Reducer / RunCommitter，见 C4）
- 图遍历与 edge 选择（`lca/framework/graph`）
- HTTP 路由与 SSE 帧格式（`lca/plugins/transport`）

## 3. 输入

`ResolvedProfile` 编译产物（`CompiledRunPlan` / `V2ExecutablePlan`，经
`lca_kernel.plan.plan_compile`）、绑定后的 `RunSessionWriter` /
`FactGateway` writer、`AgentState` 与 graph 的 `Plan` / `NodeInput`。

## 4. 输出

包门面 `lca/loop/__init__.py.__all__` 恰好 10 个符号——事实投递
`publish_ep_bound` / `append_catalog_bound` / `DefaultFactGateway`，工具与记忆
commit 收据 `commit_tool_phase_call_start` / `commit_tool_phase_call_end` /
`commit_tool_phase_denied` / `commit_tool_journal_receipt` /
`commit_act_journal_receipt` / `commit_memory_journal_receipt` /
`commit_memory_spine_receipt`。驱动与解释器类型（`RuntimeDriver`、
`DeclarativeRuntimeDriver`、`TurnExecutor`、`PlanInterpreter`、
`InterpretationResult`、`DeclarativeExecution`、`DeclarativeCheckpoint`、
`SpineEmitRef`）从子模块 `lca.loop.driver` / `lca.loop.emit.*` /
`lca.loop.commit.*` 导出，不经包门面。

## 5. 允许依赖

—（镜像 pyproject `[tool.lca.package_contracts.lca.loop].allowed_dependencies`：
`lca.contracts`、`lca.framework`、`lca.harness`、`lca.infrastructure`、
`lca.runtime`、`lca_kernel.events`、`lca_kernel.plan`）

## 6. 禁止依赖

**pyproject.toml `[tool.lca.package_contracts.lca.loop].forbidden_dependencies`**:
`lca.agent`、`lca.application`、`lca.plugins`。本层不得 import 组合根或 agent
业务，也不得 import 具体插件实现；插件经 seam/provider 注入。

## 8. 失败语义

按源码 `raise` 统计：`ValueError` 3、`TypeError` 2、`AttributeError` 1。
事实投递失败**不静默**：未绑定 publish writer 时显式丢弃并给出原因
（`publish_ep_bound` 返回 `None`），observer 异常 contained 且不回滚已 commit 的
append；driver 侧异常向上抛给 kernel 记录失败 visit。

## 9. 公共入口

包门面（与模块 __all__ 声明一一对应）：

`DefaultFactGateway`, `append_catalog_bound`, `publish_ep_bound`,
`commit_act_journal_receipt`, `commit_memory_journal_receipt`,
`commit_memory_spine_receipt`, `commit_tool_journal_receipt`,
`commit_tool_phase_call_start`, `commit_tool_phase_call_end`,
`commit_tool_phase_denied`

子模块入口：`lca.loop.driver`、`lca.loop.emit`、`lca.loop.commit`、
`lca.loop.control`、`lca.loop.transport`、`lca.loop.fact_gateway`
## 7. 副作用

只写事实，不写世界（镜像 pyproject side_effects：`fact:session-append`、`log:emit`）：

| 入口 | 后果 |
|---|---|
| `publish_ep_bound(ep, payload, actor=…)` | 解析绑定的 publish writer → `Session.append` 一条 spine EP 事件；未绑定时**显式丢弃**（返回 `None` 并记录原因），不静默 |
| `append_catalog_bound(...)` | 经同一 seam 追加 catalog 事件，返回 `AppendReceipt` |
| observer 失败 | contained：已 commit 的 append 不回滚（§3 错误分类） |

本包不创建文件、不打开 socket、不直接写 journal 后端；落盘由 Session 后端与
sink 完成。

## 30 秒：一步 iteration 发生什么

```text
HTTP/CLI → CognitiveAgent → CognitiveRuntime → DeclarativeRuntimeDriver
  → PlanInterpreterAdapter（图遍历）
    → PhaseExecutionTransaction（单 phase visit）
      → PhaseExecutor（plugin）→ Brain/Body/Memory/PerceiveHub
      → FactGateway → Session.append → *.spine.jsonl
      → Reducer.apply_*（控制面 State）
```

**六语义 phase（图节点）**：`perceive → think → act → reflect → remember → stop`  
**Gate 不是 graph node**：Gate 是 Think 原语内的 `DecisionGate` 链（见 `lca/cognition/brain/cognitive_pipeline.py`）。

## 读代码顺序

| 顺序 | 文件 | 看什么 |
|---|---|---|
| 1 | `bundles/declarative-phase-graph.yaml` | 节点、边、控制 plugin 列表 |
| 2 | `lca/harness/graph/execute/interpreter.py` | 图遍历与 loop 回边 |
| 3 | `lca/loop/transaction.py` | 一次 visit 的生命周期 |
| 4 | `lca/plugins/phase_graph/*.py` | 各 phase 如何调认知原语（迁移目标：`plugins/phase/*`） |
| 5 | `lca/runtime/runtime_loop.py` | Run 入口与 lifecycle |
| 6 | `lca/loop/fact_gateway.py` + `emit/` + `commit/` | Gate/perceive catalog 事实 |

## 四类状态（勿混）

| 类别 | SSOT | 不要从这里构建 LLM wire |
|---|---|---|
| Facts | Session.append | — |
| Model-visible | ModelContextAssembler fold | ~~AgentState.history~~ |
| Control | RunCommitter / Reducer | — |
| Ephemeral | stream accumulators | — |

## 子目录

| 路径 | 职责 |
|---|---|
| `emit/spine/` | spine EP 投递（ep、phase_fact、kernel_loop） |
| `emit/cognitive/` | 认知面 EP（llm、reasoner、agent_spawn） |
| `commit/` | journal/spine 提交收据 |
| `transport.py` | transport 面 EP |

旧模块名经 ``lca.loop`` 包 ``sys.modules`` 兼容；新代码用上表路径。

- [0075 声明式阶段图](../../docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md)
- [0191 Runtime DSH 收敛](../../docs/adr/0191-runtime-loop-dsh-convergence-and-control-plane.md)
- [0192 Fact Plane](../../docs/adr/0192-fact-plane-convergence.md)
- [0194 Loop 架构收敛](../../docs/adr/0194-cognitive-loop-architecture-convergence.md)
- [0195 全栈平台收敛](../../docs/adr/0195-platform-architecture-convergence.md)
