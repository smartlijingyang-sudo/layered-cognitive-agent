# ADR-0206 — 信息图内核与信息边编译闭包：可编译的 Agent 编排骨架（归属·传递·消化·转化·依赖）

## 状态

**Proposed — 2026-09-08**

> **一句话**：把 Agent 从「隐式 while-think-act 循环」提升为**可编译的信息边闭包**——控制面、信息边、模型可见投影三层分离；节点是有名有责的工人；跨图借用带能力授予；**编译期**声明依赖，从结构上消灭「工具已执行但下次模型看不见」这类漏洞；天生可观测、可审计、可回放。

**编号**：**0206**（0200–0205 已被现有 ADR 占用；此编号为空号）。

**关系**：

- **Builds on**：0075 声明式 phase graph（`CognitivePhaseGraphPlan`）、0068 `CompiledRunPlan`、0169 LoopCursor / ProjectionHost 五缝、0167/0185 真值与模型可见分离、0193/0201 Model-Visible 写面闭环、0198 Observability Compile Graph、0048 Skill。
- **Companion**：[0207](0207-graph-orchestrated-cognitive-agent-kernel.md) 承载多图协作与编译期信息契约的「如何运行」语义（六原语、think-as-call、ContextManifest、CompiledGraphBundle）；本文给出**统一信息本体 + 编译不变式 + 落点对照**，是 0207 的词汇与不变式基础。
- **不 supersede** 上述 Accepted；既有的缝是落点而非推倒。
- **Reject**：第二 CognitiveRuntime / 「信息图引擎」；上帝图；无类型黑板当 SSOT；热拔 Spine / 主循环。

**Follow-ups**：0206.1 Schema；0206.2 编译器与不变式 CI；0206.3 投影闭包；0206.4 效应回执强制；0206.5 跨图 Borrow/Grant；0206.6 边点火观测面。

---

## 0. 第一性原理：问题本质

用户看到的「简单链路」：

```text
想 → 调工具 → 得结果 → 再想 → …
```

真实失败几乎都不是「模型不够聪明」，而是**信息没有被当成一等公民**：

| 故障类 | 本质 | 编译如何消灭 |
|--------|------|--------------|
| 工具跑了，下次上下文没有结果 | 效应输出未边连到模型可见输入 | 缺边 → 编译失败 |
| Prompt 拼装隐式、难审计 | 「模型所见」不是独立可校验产物 | 模型可见闭包一等公民 |
| 校验/重试散落 if-else | 控制与消化未节点化 | Validate/Digest 工人节点 |
| 并行乱序写坏上下文 | 无端口类型与汇合屏障 | 显式 Barrier |
| 跨模块偷读全局 state | 无归属与借用契约 | Borrow + Grant |
| 难 debug | 边触发不可观察 | 每条边点火 = 可审计事件 |

LCA 已用一次真实 run 证明这段「简单链路」会如何断裂：ADR-0201 记录的 `run_640c492b7f40` 中，`assemble_model_history` 路径下模型对工具结果失明（`role=tool` 计数恒为 0）。当时的修复是**线性 fold 写面**（`append_tool_result_surface → derive_messages → assemble_model_history`）。本 ADR 把这条线性闭包提升为**编译期可校验的边闭包**，使同类缺陷从「运行期排查根因」变成「编译失败：效应回执不可达模型可见输入」。

### 0.1 本质命题（五条）

1. **Agent 工作 = 信息的归属、传递、消化、转化、依赖**——不是「多写几个 prompt」。
2. **隐式约定必然漂移**；只有**编译期声明的边**能保证「必不可少且互相依赖」的步骤真的发生。
3. **真值 ≠ 所见**：Spine/Journal 是事实；模型上下文是**模型可见投影的输出**（对齐 0167/0185/0193）。
4. **思考不是单点函数**，是有角色的工人流水线（可并行），本身可配置为边的编排。
5. **跨图借用像蚂蚁的信息素/人类协作**：能借什么、怎么用、什么约束，必须是**授予（Grant）**，不是全局可读。

### 0.2 删除条件

若系统已满足：一切模型可见输入均来自已编译投影闭包；一切效应输出要么进入模型可见闭包、要么显式 Discard 并审计；跨图读必经 Borrow；CI 对缺边 fail——本 ADR 可降为附录。

---

## 1. 本体论（骨架词汇表）

| 概念 | 定义 | 非定义 |
|------|------|--------|
| **Fact / Spine** | 追加式真值事件（不可篡改历史） | 不是 LLM 消息列表 |
| **控制面（Control plane）** | `CompiledRunPlan.phase_graph`（`CognitivePhaseGraphPlan`）+ `effect_policy` + `action_authority` | 不是一张「上帝图」 |
| **信息边（InfoEdge）** | 声明依赖：`Out → In`；种类见 §1.1 | 不是运行时碰巧赋值 |
| **InfoNode（工人）** | 单一职责变换：读输入端口 → 消化/转化 → 写输出端口；可声明并行度 | 不是随意闭包偷读全局 |
| **InfoPort** | 类型化入口/出口：`In<T>` / `Out<T>`；带语义标签 | 不是无 schema 的 dict 袋 |
| **InfoGrant** | 跨图借用许可证：可借哪些端口、只读/消费、TTL、审计 | 不是 import 即可见 |
| **Borrow** | 经 Grant 的跨图边（引用他图节点/端口） | 不是复制粘贴子图到上帝图 |
| **模型可见（Model-visible）** | 由事实/中间产物**派生**、经 `ModelContextAssembler` 送达模型的视图 | 不是第二份真值 |
| **Effect** | 对世界的副作用（工具/写盘/发令）；必须有回执边 | 不是 fire-and-forget |
| **Compile** | InfoEdgeSpec + 控制面 + Scope → **校验闭包**（绑定、排序、屏障、可达性） | 不是解释到一半再猜边 |

**命名纪律**：控制面沿用既有 `CognitivePhaseGraphPlan`（不复用已退役的 `ControlPlan`）；模型可见沿用既有 `ModelContextAssembler`（不复用观测层已占用的 `ProjectionSpec`，见 §5）。本文新增的不可变数据契约仅一个词根 `InfoEdge*`——`InfoEdgeSpec` / `InfoNode` / `InfoPort` / `InfoEdge` / `InfoGrant`。无 `GraphKind` 枚举，无「InfoGraph / ThinkGraph / EffectGraph」等可执行图种。

### 1.1 边种类（InfoEdgeKind）

| Kind | 含义 | 失败语义 |
|------|------|----------|
| `data` | 纯数据依赖 | 缺输入 → 节点不运行 |
| `effect` | 触发副作用并要求回执 | 无回执边 → **编译失败** |
| `control` | 闸门/审批/路由 | 未满足 → 挂起或走拒绝支路 |
| `project` | 进入模型可见闭包 | 未声明 project 的效应输出默认**不可见**（显式 Discard） |
| `borrow` | 跨图授予读 | 无 Grant → 编译失败 |

### 1.2 三层切法（与既有缝对照）

| 层 | 职责 | LCA 现有落点 | 本 ADR 新增 |
|----|------|-------------|-------------|
| **控制面** | 阶段/循环骨架；LoopCursor 只 `advance` / `record_*` | `CognitivePhaseGraphPlan`、`EffectPolicyPlan`、`ActionAuthorityPlan` | 无 |
| **信息边** | 「思考」「工具」「消化」「校验」的依赖闭包 | —（尚无） | `InfoEdgeSpec` 编译闭包 |
| **模型可见** | 模型究竟见到什么 | `ModelContextAssembler` + surface fold（0193/0201） | 编译期可达性校验，不重命名 |

用户说的「think 也是图」「模型所见是独立图」「tool result 控制是图」——分别对应信息边上的 think / effect∪digest 区域与模型可见闭包，**禁止**揉进单一控制面，也禁止为它们另立可执行图种。多图协作如何运行的语义延伸见 [0207](0207-graph-orchestrated-cognitive-agent-kernel.md)。

---

## 2. 核心不变量（编译器必须强制）

| ID | 不变式 | 违反时 |
|----|--------|--------|
| **C1 Visibility-by-Edge** | 任何进入下次模型调用的字节，必须经 `ModelContextAssembler` 的输入端口，从某 `InfoNode` 输出端口沿 `project`/`data` 边可达 | 编译失败 |
| **C2 Effect-Receipt** | 每个 `effect` 边源节点必须暴露回执输出端口；该回执端口要么 ∈ 模型可见闭包、要么显式连 `discard` 汇点并审计 | 编译失败 |
| **C3 No-Silent-Drop** | 禁止「工具成功但回执既不投影也不 Discard」 | 编译失败 |
| **C4 Borrow-Grant** | 跨图读必须有 InfoGrant；Grant 不可提权 | 编译失败 |
| **C5 Fact≠ModelVisible** | Digest/裁剪节点不得写 Spine 真值；只写旁路产物或投给模型可见闭包 | 编译失败 / 运行拒绝 |
| **C6 Single-Writer** | 每个 InfoPort 在一个计划内写入方唯一（或显式 Merge 节点） | 编译失败 |
| **C7 Barrier** | 声明并行的工人必须经 Barrier 再进入下游模型可见闭包 | 编译失败 |
| **C8 Auditable-Fire** | 每条边点火产生可观测事件（0167 面） | CI/运行断言 |
| **C9 Kernel-Closed** | Phase/Envelope/Manifest 语义不可被 Profile 旁路替换 | 对齐 0195/0180 |
| **C10 Delete-Condition** | 临时桥接节点必须带 `delete_after` | CI warn→fail |

**「工具结果没灌入下次模型所见」** ≡ 违反 C1∪C2∪C3。ADR-0201 已用真实 run 复现该故障并做了线性 fold 修补；本 ADR 用编译器把它变成静态错误，不靠约定与 fold 覆盖率。

---

## 3. 最小骨架（类型级草图）

新增的不可变数据契约 `InfoEdgeSpec` 挂载为 `CompiledRunPlan` 的新 region（与 `phase_graph` / `effect_policy` / `action_authority` 并列），**不**新开解释器或 Runtime。`region` 只是节点分组标签（think / effect / digest / projection_feed），供校验与观测使用，不是可执行图种。

```text
SchemaRef = 既有类型引用（如效应回执、surface message、artifact id）

InfoPort  = { id, dir: in|out, type: SchemaRef, tag: fact|projection|effect|control }
InfoNode  = { id, role, region, ins: [PortRef], outs: [PortRef],
              parallelism?, on_error: fail|retry|route(InfoNode.id), delete_after? }
InfoEdge  = { from: PortRef, to: PortRef, kind: InfoEdgeKind, required: bool }
PortRef   = { spec: InfoEdgeSpec.id, node: InfoNode.id, port: InfoPort.id } | BorrowRef
BorrowRef = { grant: InfoGrant.id, port: PortRef }
InfoGrant = { id, from_spec, to_spec, ports: [PortRef], mode: read|consume, constraints }
InfoEdgeSpec = { id, version, nodes, edges, grants,
                 model_visible_feed: PortRef|null, discard_sink: InfoNode.id|null }

InfoEdgeValidationReport = Compile(InfoEdgeSpec, CompiledRunPlan, Scope)
  → bindings, schedule_layers, barriers,
    projection_closure,         # 哪些 InfoNode 输出可达 ModelContextAssembler 输入
    effect_receipt_map          # 每个 effect edge → 回执端口 → project | discard
```

### 3.1 设计模式

| 模式 | 用法 |
|------|------|
| **Ports & Adapters** | 工人只认 Port；LLM / Tool / HTTP 是 Adapter |
| **Composite** | 图即子 spec；InfoEdgeSpec 组装 |
| **Strategy** | 同 Port 类型可换 Digest / Validate 策略节点 |
| **Capability** | Borrow = 带 cap 的边 |
| **Compiler 校验 + 薄解释器** | InfoEdgeSpec → 校验闭包 → 既有 `GenericPlanInterpreter`（0075 同构） |
| **CQRS** | 事实写入 vs 模型可见读取 |
| **Saga/Receipt** | Effect 必须有回执边 |

---

## 4. 目标架构

```text
                    ┌──────────────────────────────────┐
                    │  Profile / Bundle (配置)          │
                    │  phase_graph + InfoEdgeSpec +     │
                    │  projections + grants             │
                    └──────────────┬───────────────────┘
                                   │ Compile (C1–C10)
                                   ▼
                    ┌──────────────────────────────────┐
                    │  CompiledRunPlan                  │
                    │  phase_graph · effect_policy ·    │
                    │  action_authority · InfoEdgeSpec  │
                    │  info_edge_report (closure)       │
                    └──────────────┬───────────────────┘
                                   │ GenericPlanInterpreter (thin, 0075)
           ┌───────────────────────┼───────────────────────┐
           ▼                       ▼                       ▼
   Spine/Fact SSOT           Effect Gateway           ModelContextAssembler
   (0167 append)             (tool·guard·HIL)          (模型所见唯一装配链)
           │                       │                       │
           └────────── auditable edge fires (0167) ────────┘
```

**解释器保持极薄**：只按 Plan 调度工人、点火边、写回执；**不允许**在解释器里「顺手」往上下文塞字符串——那会再次破坏 C1。

### 4.1 一次「想→工具→再想」的合法编译形态

```text
InfoNode think.plan ──project──► ModelContextAssembler.in_think
InfoNode effect.tool ──effect──► ToolAdapter
effect.tool.receipt ──data──► InfoNode digest.tool
InfoNode digest.tool ──project──► ModelContextAssembler.in_tool_results
ModelContextAssembler.messages ──► openai_messages_with_history   # 唯一模型输入
```

缺 `receipt→digest→project` 任一边 → **Compile Error: C2/C3**。这就是「流水线工人互相依赖、声明清楚」。

### 4.2 Think 作为 InfoEdge 区域（非第四种图）

```yaml
info_edge_spec:
  id: think.default
  nodes:
    - { id: retrieve, role: "检索相关记忆", region: think, ins: [user_turn], outs: [snippets] }
    - { id: plan, role: "提出下一步", region: think,
        ins: [snippets, { borrow: { grant: think_read_digest, port: digest.tools.last } }],
        outs: [intent] }
    - { id: join, role: "汇合屏障", region: think, ins: [intent], outs: [think_out] }
  edges:
    - { from: retrieve.snippets, to: plan.snippets, kind: data }
    - { from: plan.intent, to: join.intent, kind: data }
    - { from: join.think_out, to: model_visible.in_think, kind: project }
  model_visible_feed: model_visible.in_think
```

并行：`retrieve` 与其它工人可并行，经 `join` 汇合后再 project。运行时调度语义（`ready ⟺ 全部 required input 满足`）见 0207。

### 4.3 模型所见：既有装配链的闭包校验

```text
ModelContextAssembler (0193/0201)
  inputs: system_prompt, in_think, in_tool_results, in_memory
  output: messages  →  openai_messages_with_history
```

**唯一**允许喂给 LLM 的是 `ModelContextAssembler` 装配后的 `messages`；编译器验证其每个输入端口在 `projection_closure` 中可达。对齐 0185：写入投影的内容必须可审计。本层**不复用**观测层 `ProjectionSpec`（ADR-0198 已占用该名，语义是 deriver 注册）。

### 4.4 跨图借用（蚂蚁隐喻的工程化）

```yaml
grants:
  - id: think_read_digest
    from_spec: digest.tools
    to_spec: think.default
    ports: [digest.tools.last]
    mode: read
    constraints: { max_bytes: 8000, redact: secrets }
```

没有 grant 的 `borrow` 引用 → 编译失败（C4）。这比「共享 blackboard」更接近人类协作：你能用我的哪块信息、怎么用、什么约束。

---

## 5. 与 LCA 既有缝的吸收映射（确切类型/文件）

| 用户概念 | LCA 现役落点 | 动作 |
|----------|--------------|------|
| 总编排图 | `CompiledRunPlan.phase_graph` = `CognitivePhaseGraphPlan`（`lca/contracts/protocols/declarative/declarative_1/declarative_graph.py`） | Keep；不追加新解释器 |
| 编译计划 | `CompiledRunPlan`（`lca/contracts/protocols/state/plan.py`） | 扩一个 `InfoEdgeSpec` region |
| 效应回执 | `ToolJournalReceipt` / `ActJournalReceipt`（`lca/loop/commit/tool_journal.py`、`act_journal.py`）+ `RuntimeEffectGateway` + `SafeExecutor` | InfoEdge 效应工人 |
| 模型可见 | `ModelContextAssembler`（`lca/contracts/protocols/session/model/context.py`）、`derive_messages`、`assemble_model_history`、`append_tool_result_surface`（ADR-0193/0201） | 编译器加可达性校验，不重命名 |
| 真值 | Spine / Session append（0167） | 消化节点禁止写回 |
| 观测投影 | `ProjectionSpec` + `CompiledObservabilityPlan`（`lca/contracts/observability/compile/plan.py`，ADR-0198） | 保持原义，名称不让渡 |
| 插件边界 | Manifest Def/Prov/Cons（0180/0190） | InfoNode 实现为 Provider |

**命名冲突结论**（本文与早期草稿的差异）：草稿曾把三层冻结为 `ControlPlan / InfoEdgeSpec / ProjectionSpec`。核对代码后更正——`ControlPlan` 已退役（`plan.py` 明确「旧 ControlPlan 不再进入运行计划」）；`ProjectionSpec` 已被 ADR-0198 占用为观测层 deriver 注册。故控制面用 `CognitivePhaseGraphPlan`、模型可见用 `ModelContextAssembler`，新增词根仅 `InfoEdge*`。

**历史命名校正**（沿用早期草稿的实况核对）：

| 校正 | 结论 |
|------|------|
| 用户口中的「0189 极端插件」 | main 文件多为 `0190-extreme-plugin-organization`（历史自标 0189） |
| think-as-graph | 0075/0194 仍是单条六阶段认知图，非多信息边注册表；本 ADR 用 `InfoEdgeSpec` region 承载多区域编排 |
| tool→next-context | 0048 是运行时 activate，无编译期依赖边；本 ADR 补编译期 `effect→digest→project` 边 |
| 吸收策略 | 扩展 0068/0075 计划族 schema（bump），不开第二 Runtime / 第二 Journal |

**禁止**：为「信息边」再造平行 Runtime / 平行 Journal。骨架 = Schema + 校验闭包，挂在既有 Resolve→Compile→Interpret 链上；多图运行细节由 0207 在同一解释器内扩展，而非另起执行器。

---

## 6. 可观测 / 审计 / Debug（天生）

每条边点火至少记录：

```text
edge_fire{ plan_id, edge_id, kind, from, to, seq, bytes?, grant_id? }
node_start / node_end{ node_id, duration, error? }
model_visible_commit{ content_digest }
effect_receipt{ tool_call_id, status }
```

Debug UX（产品形态，非本 ADR 实现）：

- 图可视化：缺边标红（编译期）
- 一次 Run 的边点火时间线
- 「模型所见」一键展开 = 投影闭包回放
- 「此 tool 结果为何不可见」→ 查有无 project / Discard 边

---

## 7. 反模式（Reject）

| 反模式 | 为何有害 | 正确做法 |
|--------|----------|----------|
| 上帝图（一切塞一张） | 不可维护、不可替换 | 三层分离 + InfoEdgeSpec |
| 无类型黑板 / 全局 state | 隐式依赖，编译器失明 | Port + Edge only |
| 解释器里拼 prompt | 绕过投影闭包，C1 失效 | 只经 `ModelContextAssembler` |
| 工具成功无回执边 | 「跑了但看不见」温床 | C2 强制 |
| 跨图裸 import | 提权与纠缠 | Borrow + Grant |
| 热拔 Spine / 主循环 | 破坏真值链 | kernel 闭集 |
| 第二 Runtime「信息图引擎」 | 平行真相 | 校验进既有 Plan |
| 蚂蚁隐喻当实现 | 信息素 ≠ 可审计边 | 隐喻止于 Grant / Borrow |
| 配置即图灵泥潭 | 不可推理 | 工人有限原语 + 声明式边 |

---

## 8. 场景矩阵（骨架必须覆盖）

| 场景 | 期望 |
|------|------|
| 单工具成功 | receipt → digest → project → 下次 think 可见 |
| 单工具失败 | 失败回执 → 策略节点（retry/deny/expose_error）→ 显式错误或 Discard |
| 并行多工具 | Barrier 汇合后统一 digest/project |
| 工具需审批 | control 边挂起；resume 后同一 effect 身份续跑（0078/0173） |
| Think 工人部分失败 | `on_error` 路由；不得半投影 |
| 借用端口超 cap | 运行拒绝 + 审计 |
| 热更新 InfoEdgeSpec | 新 Plan 版本；进行中 Run 钉死旧 plan_id |
| 回放 | 只按 Spine + 边点火重放投影，不重放副作用（除非明示） |

---

## 9. 落地阶段（诚实切片）

| Phase | ID | 内容 | 退出标准 |
|-------|-----|------|----------|
| 0 | — | 本体词汇对照表 + 命名冲突结论入本 ADR | 本 ADR 被评审确认 |
| 1 | 0206.1 | Schema：`InfoEdgeSpec` / `InfoNode` / `InfoPort` / `InfoEdge` / `InfoGrant` | JSON Schema + 示例 |
| 2 | 0206.2 | Compiler：C1–C7 静态检查 | 「缺 project 边」用例红→绿 |
| 3 | 0206.3 | 模型可见闭包接到 `ModelContextAssembler` | 模型输入唯一出口测试 |
| 4 | 0206.4 | Effect 回执强制 | 无回执无法 Compile |
| 5 | 0206.5 | Borrow/Grant | 跨图无 grant 失败 |
| 6 | 0206.6 | edge_fire 观测面 | doctor/时间线可查 |

**顺序约束**：先编译器不变式，再丰富 DSL 糖；禁止未 Compile 先上「灵活脚本」。与 0207 的实施分期（schema / ContextManifest / Effect→Observation→Context / Parallel+Join）同源，按同一「不新开 Runtime」前提推进。

---

## 10. 后果

**正**：细节漏洞结构上可灭；配置化工人 + 并行；跨图协作有约束；debug/审计一等公民；与 LCA 缝同构可演进。

**代价**：前期 Schema/Compiler 成本；团队要学 Port/Edge 思维；拒绝「先跑通再补边」。

**风险与缓解**：DSL 膨胀 → 原语最小化；与 0075 双轨 → 信息边只作 `CompiledRunPlan` 新 region，不另起解释器；表演式「万物皆图」→ 三层白名单（控制面 / 信息边 / 模型可见）。

---

## 11. 决策记录

**Adopt**：§1 本体（词根 `InfoEdge*` + 三层切法）；§2 不变式 C1–C10 落实为 `InfoEdgeSpec` 编译闭包；§5 命名冲突结论与历史命名校正；§7 Reject；§9 切片 0206.1–0206.6。
**Absorb into LCA seams**：`InfoEdgeSpec` ⊆ `CompiledRunPlan`，**非**新 Runtime；模型可见复用 `ModelContextAssembler`；观测 `ProjectionSpec` 名称不让渡；多图运行语义由 0207 在同一解释器内扩展。
**Accepted 条件**：Phase 0–2 完成；至少一个「缺边则编译失败」的金样例合入 CI。

---

## 附录 A — 业界坐标（吸收姿态）

| 范式 | 吸什么 | 不吸什么 |
|------|--------|----------|
| **KPN / Beam** | 端口就绪才读；声明与执行分离；复合变换 = 子 spec | 重跑批处理全家桶 |
| **Dagster assets** | 效应回执/摘要/模型可见包当有血缘资产 | 把编排引擎当认知内核 |
| **LangGraph Pregel** | 通道订阅 = 端口；BSP 屏障防半更新上下文；interrupt 当效应边 | **共享可变 State dict 当唯一黑板** |
| **Temporal** | 效应结果必须进历史；HITL = 耐久等待边；幂等活动 | 用 Temporal 替换 Spine/内核 |
| **Actor mailbox** | 效应工人隔离 | 无类型消息风暴当编排 |
| **CQRS** | 真值追加 + 投影折叠 | `messages[]` 当真值 |
| **Object capability** | 边上的 Grant 衰减 | 仅 OS 级权限 |
| **蚂蚁信息素** | 隐喻 → Borrow + TTL + 约束 | 无衰减黑板垃圾场 |
| **LCA CompiledRunPlan** | 不可变计划为权威；能力门 | 运行时再解释 YAML 旁路 Compile |

Industry「看不见」的十条防线与 §2 C1–C10 对齐，可逐条做 CI：Effect→Consume 闭包、投影完备门、禁环境读、端口类型、能力充足、单写/reducer、Journal 先于投影、interrupt 幂等、跨图 borrow 约束、并行写集屏障。

## 附录 B — 给编码代理的强制提问

1. 新逻辑是 InfoNode / InfoEdge / InfoGrant，还是又在解释器里 if？
2. 模型将见到的字节，投影闭包路径是哪条？
3. 每个 effect 的 receipt 与 project / Discard 边在哪？
4. 跨图读的 InfoGrant id？
5. 是否触碰 kernel 闭集（Phase / Envelope / Manifest）？
6. 删除条件？

## 附录 C — 一句话给业务方

> 我们不是「把 agent 画成流程图好看」，而是**用编译器保证信息流水线上每个工人的输入输出来自声明，从而工具、思考、所见、校验不会再靠默契对齐。**

---

*ADR-0206 Proposed — 2026-09-08*