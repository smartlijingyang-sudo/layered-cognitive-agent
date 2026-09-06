# LCA Agent Loop — 人读入口

> 权威决策：[ADR-0194](../../docs/adr/0194-cognitive-loop-architecture-convergence.md)  
> 拓扑配置：[bundles/declarative-phase-graph.yaml](../../bundles/declarative-phase-graph.yaml)

## 30 秒：一步 iteration 发生什么

```text
HTTP/CLI → CognitiveAgent → CognitiveRuntime → DeclarativeRuntimeDriver
  → GenericPlanInterpreter（图遍历）
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
