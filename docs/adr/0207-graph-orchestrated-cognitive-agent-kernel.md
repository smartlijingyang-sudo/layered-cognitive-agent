# ADR-0207 — 图编排式认知 Agent 内核：多图协作与编译期信息契约

## 状态

**Proposed — 2026-09-08**

Refines: [0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md)、[0068](0068-compiled-plugin-kernel-and-unified-run-plan.md)、[0194](0194-cognitive-loop-architecture-convergence.md)、[0201](0201-tool-result-prompt-closure.md)。

Companion: [0206](0206-information-graph-kernel.md)（LCA 落点词汇：`ControlPlan` · `InfoEdgeSpec` · `ProjectionSpec`）。

## 0. 决策摘要

Agent 不应再被实现为一个隐式 `while think→act→think` 循环。一次运行是**多个相互引用、各自拥有契约的图**，在受 `CompiledGraphBundle` 约束的薄解释器上协同执行。

| 图族（概念） | 回答的问题 | LCA 落点（见 0206） |
|---|---|---|
| 编排图 | 大流程、并行、合流、终态 | `ControlPlan` / 0075 phase graph |
| 认知图 | 感知、推理、批评、综合、反思 | `InfoEdgeSpec` 子配置（think 流水线） |
| 上下文图 | 每次 LLM 调用确切看到什么 | `ProjectionSpec` / ContextManifest |
| 效果图 | 工具意图→授权→执行→回执 | `InfoEdgeSpec` effect 边 + Effect Gateway |
| 溯源图 | 每个输出从哪来（观察投影） | Journal + Provenance 投影 |

**核心不变量**：模型只能消费 Context Graph 编译出的 `ContextManifest`；工具只能消费经 Gate 的 `Decision` 并经 Effect Graph 产出 `Receipt`；下一轮 Think 只能消费已 Journal-commit 的 `Observation`。任何一步缺 Binding → **编译失败**，不靠运行时约定。

**Reject**：第二 `GraphRuntime`；无类型全局黑板作 SSOT；运行时发明节点/边；「工具成功但结果默认不可见」。

## 1. 背景

### 1.1 问题本质

表面链路只有四步：`observe → decide → act → integrate`。失败几乎都不是模型能力不足，而是**信息未被当作一等公民**：

| 故障 | 根因 | 图编译如何消灭 |
|---|---|---|
| 工具跑了，下轮模型看不见 | 效应输出未边连到投影输入 | 缺 `project` 边 → 编译失败 |
| Prompt 拼装隐式、难审计 | 「模型所见」不是独立产物 | Context Graph 产出 `ContextManifest` |
| 校验/重试散落 if-else | 控制与消化未节点化 | 路由边 + Validate/Digest 工人 |
| 并行结果乱序污染上下文 | 无 Join 屏障 | 显式 `parallel` + `join` |
| 跨模块偷读 State | 无归属与借用契约 | `Borrow` + `CapabilityGrant` |

### 1.2 与现有 LCA 的关系

LCA 已具备：声明式 phase graph（0075）、`CompiledRunPlan`（0068）、Reducer 单写、Effect Gateway、Journal/Spine、`plan_hash` 恢复锁、Model-Visible 投影（0193/0201）。本 ADR 不是推倒重来，而是**概念升级**：把「模型见到什么」「tool result 如何进入下轮」「节点产出什么事实」从隐含约定提升为**编译期 Binding 契约**。

## 2. 决策

### 2.1 六类不可再分原语

| 原语 | 定义 | 禁止 |
|---|---|---|
| **Artifact** | 不可变信息载体（prompt 片段、tool output、ContextManifest） | 当作完整事实源 |
| **Port** | 节点的 typed 输入/输出接口 | 无 schema 的 dict 袋 |
| **Node** | 有职责的处理器（可并行、可失败、可重试） | 偷读全局 State |
| **Graph** | 节点 + 边 + 端口的声明式编排 | 上帝 YAML 吞一切 |
| **Binding** | 跨图/跨节点的显式数据连线 | 隐式 history 读取 |
| **Fact** | 追加式运行记录 | 由 Projection 反向写入 |

### 2.2 think 是 graph.call，不是函数

`think` 阶段引用认知子图（如 `cognition.think/v4`），子图内部是工人流水线：

```text
context.assemble → llm.reason → llm.critic (可并行) → decision.synthesize
```

每个工人声明：`responsibility`、`inputs`（从哪个图的哪个 port）、`outputs`、`on_failure` 路由、`capabilities`。父图通过 **export port** 消费子图输出；禁止字符串路径读子图内部。

### 2.3 Context Graph：模型所见是独立编译产物

每次 LLM 调用前，Context Graph 运行一次，输出 frozen `ContextManifest`：

```text
prompt.system ──┐
prompt.task   ──┼→ context.merge → context.validate → ContextManifest
tool.results  ──┤   ↑ 必须 Binding 自 effect.integrator/observation.delta
history       ──┘
```

`tool.results` 节点缺 Binding → 编译器报 `UNBOUND_PORT`。调试时 dump `ContextManifest` 即可见模型**确切**输入，无需猜 prompt 拼接。

### 2.4 Effect Graph 与闭环

```text
ToolIntent → grant.check → approval.wait → executor.dispatch → EffectReceipt
                                                                    │
                                                                    ▼
                                              observation.integrate → Observation (Fact)
                                                                    │
                                                                    ▼
                                              Context Graph (下轮 think)
```

Receipt 写 Journal；Observation 经 Reducer 更新 State 投影；**只有**经 `project` 边进入 Projection 的字节才可进 ContextManifest（对齐 0201 MV 闭包）。

### 2.5 并行与合流

```yaml
# 概念
- type: parallel
  branches: [research.web, research.code, research.docs]
  join:
    strategy: all_complete | first_success | quorum(n)
    on_partial: route_to(synthesizer.with_gaps)
```

无 Join 声明的 parallel → 编译错误。

### 2.6 错误处理是路由边，不是 try/catch

| 错误类 | 语义 | 默认路由 |
|---|---|---|
| `deterministic` | 契约/输入错误 | 不重试 → reflect → 可能 stop |
| `transient` | 网络/超时 | 退避重试 → 同一节点 |
| `policy` | 权限/审批拒绝 | → gate.rejected → HIL |
| `budget` | token/步数/成本超限 | → stop.budget_exceeded |

### 2.7 跨图借用（Borrow）

跨图只借 **artifact/fact id**，禁 live 对象指针。借用必须携带 `CapabilityGrant`：可读端口、只读/消费模式、TTL、审计。父图不能穿透读子图内部。

### 2.8 编译产物：CompiledGraphBundle

```text
Graph 配置 → Parse → Resolve（图引用展开）→ Analyze（死节点/unbound port/环/capability）
         → Compile → CompiledGraphBundle
              plan_hash · graph_hash · policy_hash
              bindings · join_table · route_table · observability_points
```

Recovery：`plan_hash` 不匹配 → 拒绝恢复（防图变更后 replay 语义漂移）。

### 2.9 运行时：薄 Graph VM，不是 Callback 链

内核保留 MTK（0075）：schema 校验、grant 单调、Reducer 单写、Journal 边界、Effect Gateway、Plan 验证器、通用解释器。新增：**Binding 调度器**、**Join 管理器**、**路由求值器**——不新增第二 Interpreter 名称。

节点调度：`ready ⟺ 全部 required input satisfied ∧ grant_ok ∧ 不在 abort 传播链`。

## 3. 不变量

| ID | 不变量 | 违反时 |
|---|---|---|
| G1 | Visibility-by-Binding：进入 ContextManifest 的字节必须来自 Projection 闭包内已声明 `project` 边 | 编译失败 |
| G2 | Effect-Receipt：每个 effect 必须有配对 Receipt；若策略要求可见，必须有到 Projection 的边或显式 Discard | 编译失败 |
| G3 | No-Silent-Drop：禁止「工具成功但结果既不投影也不 Discard」 | 编译失败 |
| G4 | Borrow-Grant：跨图读必须有 Grant；Grant 不可提权 | 编译失败 |
| G5 | Fact≠Projection：Digest/压缩不得写 Spine 真值 | 运行拒绝 |
| G6 | Single-Writer：每 Port 写入方唯一，或经显式 Merge 节点 | 编译失败 |
| G7 | Barrier：并行分支必须经 Join 再进下游 Think/Project | 编译失败 |
| G8 | Auditable-Fire：每条边点火产生可观测事件 | CI/运行断言 |
| G9 | Kernel-Closed：Control 语义不可旁路 Spine/Envelope/Manifest | 对齐 0190 |

G1∪G2∪G3 直接消灭「tool result 没灌入下轮模型所见」类漏洞。

## 4. 可观测性（天生便于 debug/审计）

调试器保留三视图：

1. **控制图**：经过的节点、边、循环、失败路由
2. **数据图**：Artifact  lineage（输入 digest → transform → 输出 digest）
3. **可见性图**：ContextManifest 包含/排除内容及原因

关键事实事件（复用/扩展现有 EP 闭集，不平行造词表）：

| 事件 | 最小字段 |
|---|---|
| `GraphRunStarted` | run、plan_hash、grant snapshot |
| `NodeAttemptStarted` | graph_path、node、input_refs |
| `ContextManifestCommitted` | model、included/excluded refs、digest |
| `EffectReceiptCommitted` | tool_call_id、status、result_refs |
| `JoinResolved` | branch states、merge policy |

Trace 是投影；稳定关联键：`execution_id`、`graph_invocation_id`、`node_attempt_id`、`artifact_id`、`tool_call_id`。

## 5. 实施路线

| 期 | 交付 | 验证 |
|---|---|---|
| P0 | Graph/Node/Port/Binding schema + Analyze 规则 | unbound port 编译失败测试 |
| P1 | Context Graph + ContextManifest artifact | 任意 LLM turn 可 dump 完整输入 |
| P2 | Effect→Observation→Context Binding | tool result 100% 进下轮 context（pytest 守护） |
| P3 | Parallel/Join + 错误路由边 | 并行 tool 全 join 后才 synthesize |

扩展路径：**schema bump 0068/0075 计划族**，不开第二 Runtime / 第二 Journal。

## 6. Alternatives considered

### 6.1 隐式 while-loop + prompt 拼接（现状）

失败模式已证明：tool result 失明（0201）、并行乱序、难审计。Reject。

### 6.2 单一 mega-graph 吞控制+数据+投影

LangGraph 式共享 State 图作 LCA 主模型会混淆 Fact 与 Projection、绕过 Effect Gateway。Reject（0206 架构室一致）。

### 6.3 第二 GraphRuntime / 平行 Interpreter

与 0068/0194 收敛冲突；双运行时不可测试、不可 recovery。Reject。

### 6.4 仅文档约定「记得把 tool result 放进 prompt」

0201 已证明写面/读面分离后仍可能漏 Bind；只有编译期 Binding 可证明。Reject。

## 7. 关联

- [0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md) — 声明式 phase graph、MTK
- [0068](0068-compiled-plugin-kernel-and-unified-run-plan.md) — CompiledRunPlan
- [0193](0193-session-projection-fabric-model-visible.md) — Model-Visible 读 SSOT
- [0201](0201-tool-result-prompt-closure.md) — tool result 写面闭环
- [0206](0206-information-graph-kernel.md) — LCA 落点词汇与 InfoEdge 编译不变式

## 8. delete-when

```text
隐式 history 拼 prompt 路径:
  delete_when: rg 'assemble_model_history' 全路径经 ContextManifest；
              pytest 断言缺 Binding 编译失败

临时 bridge 节点（tool→context 手工拷贝）:
  delete_when: CI analyze 对 C1–C3 全绿 + 0201 MV 测试通过
```
