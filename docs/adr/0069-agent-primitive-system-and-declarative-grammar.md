# ADR-0069：Agent 原语体系与声明组合语法

## 状态

**Proposed — 2026-08-21**

Refines: [ADR-0001](0001-five-layer-separation.md)、[ADR-0002](0002-cognitive-loop.md)、[ADR-0004](0004-protocol-first-pluggability.md)、[ADR-0033](0033-declarative-agent-spec.md)、[ADR-0056](0056-plugin-group-contribution.md)、[ADR-0066](0066-declarative-atomic-control-plugins.md)、[ADR-0067](0067-spacetime-runtime-and-governed-creation.md)、[ADR-0068](0068-compiled-plugin-kernel-and-unified-run-plan.md)

> **决策：LCA 采用《Agent 原语体系宪章》作为所有新概念、模块、策略和插件的唯一概念坐标。系统以十三个原语群、六维 LogicAddress、有限关系代数、六类 contribution operation 和三个 immutable run plans 组织；不再以框架目录、Hook 时序、临时 adapter 或特设 Agent loop 决定逻辑归属。**

## 背景

当前仓库已经积累了 plugin Manifest、角色、Brain、Body、Tool、Memory、Team、Journal、Profile、Composer、Creator 等大量能力。然而，代码审计表明这些能力尚未统一在单一概念语法之下：一个新控制逻辑可能被写成 gate、guard、hook、provider、action handler、gateway helper 或 context mutation；一个新的 Agent 模式也可能被实现为新的 loop，而不是现有能力和关系的组合。[1]

这会造成“补丁式架构”的主观感受：并非代码本身缺少抽象，而是系统缺少一个可在设计前判断“新东西本体是什么、坐在哪、与谁连接、能做什么、如何证明”的上层语言。主流 Agent 实践也表明，Agent 系统涉及不止模型与工具，还涉及运行循环、状态、协作、guardrail、approval、trace、工作流与评估。[2] [3] 因而 LCA 需要一个足够完整却有限的原语体系，以承接未知未来能力。

## 决策

### 一、十三个原语群是新逻辑的唯一主归属

LCA 定义以下十三群：

| 群 | 名称 | 主要问题 |
|---|---|---|
| G0 | Constitution & Kernel | 什么使系统全局可信？ |
| G1 | Identity, Intent & Contract | 谁要什么、为何允许、成功是什么？ |
| G2 | Spacetime, Environment & Context | 何时何地、在何身份与可见性下运行？ |
| G3 | Facts, State & Knowledge | 发生了什么、当前是什么、长期知道什么？ |
| G4 | Perception & Grounding | 外部世界如何成为可信 context？ |
| G5 | Cognition, Models & Planning | 如何产生和评估候选理解、计划与决策？ |
| G6 | Decision, Command & Control | 候选意图如何被批准、收窄、预算与停止？ |
| G7 | Execution, Tools & Operations | 如何安全改变外部世界？ |
| G8 | Collaboration & Organization | 如何委派、协作、合成和共享？ |
| G9 | Interaction, Transport & Interop | 人、设备、协议、外部系统如何接入？ |
| G10 | Composition, Configuration & Runtime Governance | 已有能力如何解析、编译、启动和回收？ |
| G11 | Creation, Learning & Evolution | 新能力如何产生、试验、提升、发布和撤回？ |
| G12 | Evidence, Evaluation & Operations | 如何解释、测试、监控、回放和改进？ |

一个逻辑只能有一个主群；它可通过声明关系消费其他群的 capability 或事实，但不得复制其他群的 owner 职责。新增第十四群必须证明现有十三群均不能表达其主问题，并经 ADR 批准。

### 二、每个生产逻辑必须有六维 `LogicAddress`

```text
LogicAddress = FunctionalGroup × ControlSlot × Scope × Authority × Evidence × Revision
```

| 维度 | 必须表达 |
|---|---|
| FunctionalGroup | 十三群中的唯一主归属与 role。 |
| ControlSlot | 何时生效；非运行逻辑填 resolve / boot / release lifecycle slot。 |
| Scope | release、profile、agent、run、turn、invocation、experiment、device 等有效边界。 |
| Authority | reads、state owner、capability grant、effect class、visibility。 |
| Evidence | fact descriptor、test fixture、eval criterion、replay 需求。 |
| Revision | config、plan、artifact 或 release version 的变更语义。 |

无法完整写出 LogicAddress 的代码只能是实验草稿，不得作为 production plugin、gateway helper 或 runtime extension。

### 三、系统关系类型有限，且必须静态可读

允许关系仅为：`provides`、`requires`、`contributes_to`、`reads_fact`、`emits_fact`、`governs`、`executes`、`delegates`、`projects`、`revises`、`evaluates`。任何新关系语义均须 ADR。

全局不变量如下：

1. authority 仅可向子 scope 衰减；
2. world effect 仅可经 G7 的 CommandEnvelope 穿出；
3. facts 仅可追加，state 仅可由 Reducer 投影；
4. profile / artifact 的变更只能形成 immutable PlanRevision；
5. projection 不得回写 facts 或 business state；
6. plugin 不得通过 live Context、global helper 或未声明 service locator 绕开这些关系。

### 四、普通插件只能使用六类 contribution operation

| operation | 语义 | 典型群 |
|---|---|---|
| `collect` | 收集候选 facts / capability。 | G4。 |
| `select` | 在预算内选择候选集合。 | G4、G5。 |
| `transform` | 对 typed input 做可验证转换。 | G4、G5、G6。 |
| `veto` | deny、ask 或 narrow；不能扩大权限。 | G6。 |
| `execute` | 仅在已授权 CommandEnvelope 下产生 effect。 | G7。 |
| `project` | 从 facts / plans 派生可丢弃视图。 | G9、G12。 |

这取代自由 before / after hook。任何 contribution 必须声明 operation、slot、priority、activation predicate、merge semantics、failure mode、authority 和 evidence descriptor。

### 五、所有 Agent 模式都是 `PlanTemplate`，不是独立框架分支

RAG、prompt chain、routing、parallel / voting、orchestrator-workers、evaluator-optimizer、tool-using loop、HITL、team、scheduled agent、realtime agent 和 self-evolving agent 均定义为对十三群与关系的受限组合模板。固定工作流应使用静态 WorkflowPlan；只有任务步骤无法预先确定、且需要环境反馈时，才使用动态 Agent loop。[3]

此决定禁止为每一种模式新建顶层 loop、全局 registry 或专属 context。模式只可选择 / 配置已有 ControlPlan、CapabilityPlan、ScopePlan 和 topology template。

### 六、`PluginContract` 是唯一生产扩展语法

所有 plugin 逐步迁移到以下语义区段：`identity`、`contribution`、`consumes`、`produces`、`authority`、`scope`、`lifecycle`、`evidence`、`verification`。现有 `PluginDefinition` 的通用字段保留为兼容输入，但任意 `meta` 不得继续承担关键 architecture semantics。

## 后果

| 方面 | 正面效果 | 代价 |
|---|---|---|
| 认知清晰度 | 设计者能通过填空决策树判断新逻辑应坐在哪里。 | 团队必须学习概念语言，而非只学目录。 |
| 可维护性 | 模式共享同一 plan / relation 语义，减少专用分支。 | 初期需要重命名、映射和删除重叠术语。 |
| 可验证性 | 地址、关系和 operation 可被静态检查与测试。 | Manifest / compiler schema 更复杂。 |
| 演化能力 | 新 artifact 可通过 PlanRevision 进入系统，而不破坏内核。 | 直接动态 import / live mutation 会被淘汰。 |
| 简洁性 | 小内核稳定，独立变化在外围声明。 | 不能把所有便利 helper 都保留为永久兼容层。 |

## 治理门禁

| 门禁 | 规则 |
|---|---|
| 新概念 | 先完成 G0–G12 主归属判定与 LogicAddress，再允许代码。 |
| 新 plugin | 必须有 typed contract、fixture、evidence descriptor 与删除 / 替代关系。 |
| 新模式 | 必须写为 PlanTemplate，列出包含的 group、relations、slots 与 terminal policy。 |
| 新 effect | 必须通过 CommandEnvelope 和 G6 约束；不得藏于 provider。 |
| 新动态能力 | 必须作为 G11 artifact 经过 verify / stage / promote / retire。 |
| 新 interop | 必须是 G9 anti-corruption adapter；不得拥有核心 policy。 |
| 新 kernel 行为 | 必须 ADR；profile 不得配置其因果 / authority 不变量。 |

## 迁移

1. 以 G0–G12 为轴，为现有 `lca/plugins/`、contracts、gateway 和 docs 建立概念映射；不要求立即移动目录。
2. 先实现 `PluginContract` 与 LogicAddress lint，阻止新增无地址逻辑。
3. 依 ADR-0068 实现 CompiledRunPlan，再将现有 gate、action、pipeline、scope 与 creator 分批迁入对应群和 slot。
4. 每迁完一群，删除其旧 hook / helper / global fallback，禁止永久双轨。
5. 将 PlanTemplate、scenario fixture 和 evaluation 变为发布物的一部分。

## 参考

[1]: ../design/2026-08-21-code-aligned-architecture-audit.md "代码对齐的第一性原理架构审计"
[2]: https://developers.openai.com/api/docs/guides/agents "OpenAI Agents SDK guide"
[3]: https://www.anthropic.com/engineering/building-effective-agents "Anthropic: Building effective agents"
[4]: ../design/2026-08-21-agent-primitive-system-constitution.md "Agent 原语体系宪章"
