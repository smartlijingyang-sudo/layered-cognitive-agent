# ADR-0206 — 可编译信息图认知内核：单一可执行图 + 嵌套子图驱动所有阶段与视图

## 状态

**Accepted — 2026-09-09**（ADR-0210 §九 8 条全部满足 + production path 验证：`profiles/web-assistant.yaml` 加 `regions.declare` 段；6 阶段 + 89 carrier 已 region 标注；0075/0194 backward compat 保留）

> **一句话**：把 Agent 从「隐式 while-think-act 循环」提升为**可编译的信息图**——**单一可执行图种 `InfoEdgeSpec`**，节点是有名有责的工人；六个阶段（perceive/think/act/reflect/remember/stop）、模型可见构造、效应回执、溯源都是同一图的**嵌套子图**；跨图借用带能力授予；**编译期**声明依赖，从结构上消灭「工具已执行但下次模型看不见」这类漏洞；天生可观测、可审计、可回放。

**编号**：**0206**（0200–0205 已被现有 ADR 占用；此编号为空号）。

**吸收记录**：本文吸收同批起草的 [0207](0207-graph-orchestrated-cognitive-agent-kernel.md)（图编排运行时语义：六原语、think-as-call、ContextManifest、CompiledGraphBundle）。0207 标 `Superseded` 保留追溯；其运行时语义并入本文 §2/§5/§6/§10。合并理由：两者是同一决策的两半（同一根因、同一不变量、同一落地切片），分成两份会产生不变量双表与词汇漂移。

**关系**：

- **Builds on**：0075 声明式 phase graph（`CognitivePhaseGraphPlan`，P7 阶段闭集迁移将被吸收）、0068 `CompiledRunPlan`、0169 LoopCursor / ProjectionHost 五缝、0167/0185 真值与模型可见分离、0193/0201 Model-Visible 写面闭环、0198 Observability Compile Graph、0048 Skill、0086 退役无消费者拓扑的反例。
- **Supersedes**：[0207](0207-graph-orchestrated-cognitive-agent-kernel.md)。
- **不直接 supersede** 0075 / 0194 / 0093 / 0068 的全部内容；其六阶段闭集 / Loop 收敛 / Control plane 部分语义由 §10 P7 显式承担迁移，独立 ADR 起头后再正式替代。
- **Reject**：第二 CognitiveRuntime / 「信息图引擎」；上帝根图（无嵌套）；平行图种（PhaseGraph/ContextGraph/EffectGraph/LineageGraph 并列）；无类型黑板当 SSOT；热拔 Spine / 主循环；把六阶段闭集当成 SSOT 锁（0075/0194 迁移阻塞）；把"万物皆图"做成口号而非机制。

**Follow-ups**：合并后落地切片为 §10 的 P0–P8（含 P7 阶段闭集迁移、P8 子图化 mv/effect/lineage），不再单列 0206.N 与 0207 P0–P3 两套编号。

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
| 并行乱序写坏上下文 | 无端口类型与汇合屏障 | 显式 Barrier / Join |
| 跨模块偷读全局 state | 无归属与借用契约 | Borrow + Grant |
| 难 debug | 边触发不可观察 | 每条边点火 = 可审计事件 |

LCA 已用一次真实 run 证明这段「简单链路」会如何断裂：ADR-0201 记录的 `run_640c492b7f40` 中，`assemble_model_history` 路径下模型对工具结果失明（`role=tool` 计数恒为 0）。当时的修复是**线性 fold 写面**（`append_tool_result_surface → derive_messages → assemble_model_history`）。本 ADR 把这条线性闭包提升为**编译期可校验的边闭包**，使同类缺陷从「运行期排查根因」变成「编译失败：效应回执不可达模型可见输入」。

### 0.1 本质命题（六条）

1. **Agent 工作 = 信息的归属、传递、消化、转化、依赖**——不是「多写几个 prompt」。
2. **隐式约定必然漂移**；只有**编译期声明的边**能保证「必不可少且互相依赖」的步骤真的发生。
3. **真值 ≠ 所见**：Spine/Journal 是事实；模型上下文是**模型可见子图（`mv.assemble`）的执行产物**（对齐 0167/0185/0193）。
4. **任何阶段都是图调用**：perceive/think/act/reflect/remember/stop 都是 `graph.call` 一个嵌套 InfoEdgeSpec；模型可见装配、效应回执、溯源也是嵌套 InfoEdgeSpec。
5. **跨图借用像蚂蚁的信息素/人类协作**：能借什么、怎么用、什么约束，必须是**授予（Grant）**，不是全局可读。
6. **图嵌套 ≠ 图种爆炸**：`InfoEdgeSpec` 是唯一可执行图种；region 是语义标签，不构成第二图种；ADR-0086 退役无消费者拓扑的反例不适用于此（嵌套图全部由 Binding 调度器 / Join 管理器 / 路由求值器消费）。

### 0.2 删除条件

若系统已满足：一切模型可见输入均来自 `mv.assemble` 子图（嵌套 InfoEdgeSpec）的已编译投影；一切效应输出要么进入 `mv.assemble` 子图、要么显式 Discard 并审计；跨子图读必经 Borrow（包含跨 region 边）；CI 对缺边、缺 `sub_spec`、缺 `export` 匹配、平行图种 全部 fail；§10 P7 阶段闭集迁移完成——本文可降为附录。

---

## 1. 本体论（骨架词汇表）

**不可再分原语**（六条）与 InfoEdge 专属词根统一为一张表：

| 概念 | 定义 | 非定义 |
|------|------|--------|
| **Artifact** | 不可变信息载体（prompt 片段、tool output、ContextManifest） | 当作完整事实源 |
| **Port** | 节点的 typed 输入/输出接口：`In<T>` / `Out<T>`，带语义标签 | 无 schema 的 dict 袋 |
| **Node（工人）** | 单一职责变换：读输入端口 → 消化/转化 → 写输出端口；可声明并行度、失败路由、重试 | 随意闭包偷读全局 |
| **Graph / InfoEdgeSpec** | **唯一可执行图种**；节点 + 边 + 端口的声明式编排；通过 `sub_spec` 边嵌套子图（region 标签标识语义） | 上帝 YAML 吞一切；为 phase/mv/effect/lineage 立独立图种 |
| **Binding / InfoEdge** | 跨节点 / 跨图的显式数据连线：`Out → In`，带 kind | 隐式 history 读取 / 运行时碰巧赋值 |
| **Fact / Spine** | 追加式真值事件（不可篡改历史） | 由 Projection 反向写入 |
| **控制面（Control plane）** | `CompiledRunPlan.phase_graph`（`CognitivePhaseGraphPlan`，0075；P7 后降级为 region 标签机制） + `effect_policy` + `action_authority` | 一张「上帝图」；与 InfoEdgeSpec 嵌套子图机制冲突 |
| **InfoGrant** | 跨图借用许可证：可借哪些端口、只读/消费、TTL、审计 | import 即可见 |
| **Borrow** | 经 Grant 的跨图边（引用他图节点/端口 / artifact id） | 复制粘贴子图到上帝图 / live 对象指针 |
| **模型可见（Model-visible）** | 由事实/中间产物**派生**、经 `ModelContextAssembler` 装配、输出 frozen `ContextManifest` 的视图 | 第二份真值 |
| **ContextManifest** | 每次 LLM 调用前由模型可见闭包冻结的输入视图（可 dump、可校验） | prompt 拼接的中间串 |
| **Effect** | 对世界的副作用（工具/写盘/发令）；必须有回执边 | fire-and-forget |
| **CompiledGraphBundle** | 图配置经 Parse→Resolve→Analyze→Compile 后的产物：bindings · join_table · route_table · plan_hash · graph_hash · policy_hash · observability_points | 运行时再解释 YAML |
| **Compile** | InfoEdgeSpec + 控制面 + Scope → **校验闭包**（绑定、排序、屏障、可达性） | 解释到一半再猜边 |

**命名纪律**（一次性定死）：控制面沿用 `CognitivePhaseGraphPlan`（0075/0194 已落点，名称让渡于 0206 §5）；模型可见沿用 `ModelContextAssembler`，其 frozen 产物命名 `ContextManifest`；观测层 deriver 注册继续用 `ProjectionSpec`（ADR-0198 已占用，语义不变、名称不让渡）。本文新增不可变数据契约词根仅 `InfoEdge*` 与 `ContextManifest` / `CompiledGraphBundle`。无 `GraphKind` 枚举，无「InfoGraph / ThinkGraph / EffectGraph」等可执行图种。

### 1.1 边种类（InfoEdgeKind）

| Kind | 含义 | 失败语义 |
|------|------|----------|
| `data` | 纯数据依赖 | 缺输入 → 节点不运行 |
| `effect` | 触发副作用并要求回执 | 无回执边 → **编译失败** |
| `control` | 闸门/审批/路由 | 未满足 → 挂起或走拒绝支路 |
| `project` | 进入模型可见闭包 | 未声明 project 的效应输出默认**不可见**（显式 Discard） |
| `borrow` | 跨图授予读 | 无 Grant → 编译失败 |

### 1.2 三层覆盖（expression / runtime / outcome）

「写进 YAML」≠「问题被消灭」。必须分清三种覆盖：

| 覆盖 | 含义 | 谁负责 |
|------|------|--------|
| **表达覆盖** | 图能清晰声明谁处理什么、信息来自哪、经过哪些节点和边 | 本 ADR 的编译闭包（C1–C10） |
| **运行覆盖** | 运行时强制拦截，不允许旁路、隐式读取、未授权 effect | 解释器 + Effect Gateway + 模型适配器出口 + 出站代理 |
| **结果覆盖** | 事实正确、外部事务不重复、审批合法、合规成立 | 模型 + 目标系统 + IAM + 账本 + 运营（不在框架内） |

C1–C10 是**表达覆盖**；§5.7 八项生效证明 + §9.1 MVP 金丝雀是**运行覆盖**入口；§8.1 不可替代边界声明**结果覆盖**由哪些外部系统承担。三者必须并列声明，缺一即「配置存在 ≠ 问题被消灭」。

---

## 2. 切法：单一可执行图 + 嵌套子图

Agent 全栈只有一个**可执行图种 `InfoEdgeSpec`**——控制面、信息边、模型可见、效应回执、溯源，都是同一 InfoEdgeSpec 的**嵌套子图**，由根节点上的 `region` 与 `sub_spec` 引用绑定。区别只在**层级**与**输入/输出端口语义**，不在图种。

| 图层级 | 回答的问题 | LCA 落点 | 嵌套关系 |
|--------|------------|----------|----------|
| **根图（agent loop）** | 全局骨架；perceive/think/act/reflect/remember/stop 编排 | `InfoEdgeSpec.root`，每个阶段节点声明 `sub_spec` 引用子图 | 子图入口：`region = phase:<name>` |
| **阶段子图** | 单阶段内部流水线（如 think = retrieve→plan→critic→synthesize） | `InfoEdgeSpec.phase.<name>` | 根图节点的 `sub_spec` 引用 |
| **上下文子图** | 把哪些 Artifact 喂给 LLM；如何裁剪/排序/合并/打 trust label | `InfoEdgeSpec.mv.assemble`（region = `model_visible`） | 根图的 `mv.commit` 节点持 `sub_spec` 引用 |
| **效应子图** | ToolIntent→grant.check→approval.wait→executor.dispatch→EffectReceipt | `InfoEdgeSpec.effect.dispatch`（region = `effect`） | 根图的 `act` 阶段节点持 `sub_spec` 引用 |
| **溯源子图** | 每条边点火 → provenance 索引 → 反查闭包 | `InfoEdgeSpec.lineage.index`（region = `lineage`） | 观测 seam 显式挂载，不通过隐藏全局 |

**关键不变量**：

- **图种唯一** —— 不存在 `PhaseGraph` / `ContextGraph` / `EffectGraph` / `LineageGraph` 等并列图种；所有这些都是 InfoEdgeSpec 在不同 region 下的形态。
- **嵌套是显式边** —— 子图通过 `sub_spec` 边挂到父图节点上；节点 `in/out` 端口必须与子图 `export` 端口 schema 匹配，编译器校验。
- **节点 region 是语义标签**，不是图种分类。同一 region 内的节点共享调度语义（如 `model_visible` region 的所有节点输出自动进入 `ContextManifest` 装配链）。

**运行时同一份解释器**：`GenericPlanInterpreter`（0075）保持极薄，新增 **Binding 调度器 / Join 管理器 / 路由求值器** 三个组件。根图与子图共用同一解释器实例，递归调度。**不新增第二 Interpreter 名称**。`CognitivePhaseGraphPlan` 在根图层面**降级为 InfoEdgeSpec.root 的一种合规形态**，六阶段闭集转为 region 标签，0075/0194 的语义被 InfoEdgeSpec 嵌套图吸收而不是平行存在（迁移步骤见 §10 P7）。

---

## 3. 核心不变量（编译器必须强制）

0207 早期稿的 G1–G9 与本表 C1–C9 一一对应（G1=C1 … G9=C9），已并入；不变量以本表 C 编号为唯一真值。

| ID | 不变式 | 违反时 |
|----|--------|--------|
| **C1 Visibility-by-Edge** | 任何进入下次模型调用的字节，必须经 `ModelContextAssembler` 的输入端口，从某 `InfoNode` 输出端口沿 `project`/`data` 边可达 | 编译失败 |
| **C2 Effect-Receipt** | 每个 `effect` 边源节点必须暴露回执输出端口；该回执端口要么 ∈ 模型可见闭包、要么显式连 `discard` 汇点并审计 | 编译失败 |
| **C3 No-Silent-Drop** | 禁止「工具成功但回执既不投影也不 Discard」 | 编译失败 |
| **C4 Borrow-Grant** | 跨图读必须有 InfoGrant；Grant 不可提权 | 编译失败 |
| **C5 Fact≠ModelVisible** | Digest/裁剪节点不得写 Spine 真值；只写旁路产物或投给模型可见闭包 | 编译失败 / 运行拒绝 |
| **C6 Single-Writer** | 每个 InfoPort 在一个计划内写入方唯一（或显式 Merge 节点） | 编译失败 |
| **C7 Barrier** | 声明并行的工人必须经 Barrier/Join 再进入下游模型可见闭包 | 编译失败 |
| **C8 Auditable-Fire** | 每条边点火产生可观测事件（0167 面） | CI/运行断言 |
| **C9 Kernel-Closed** | Phase/Envelope/Manifest 语义不可被 Profile 旁路替换 | 对齐 0195/0180 |
| **C10 Delete-Condition** | 临时桥接节点必须带 `delete_after` | CI warn→fail |
| **C11 Single-Graph-Kind** | `InfoEdgeSpec` 是唯一可执行图种；不得为 phase/mv/effect/lineage 立独立图种或平行 Runtime | 编译失败 / 架构审计 |
| **C12 Subgraph-Export-Match** | 子图根节点的 `in/out` 端口必须与父图 `sub_spec` 引用节点的端口 schema 一致 | 编译失败 |
| **C13 Nested-Fire-Visible** | 子图内的边点火事件必须携带 `subgraph_path`，确保可观测性递归到嵌套层 | 运行断言 / canary-H |
| **C14 Phase-Tag-Only** | 阶段标签（perceive/think/act/reflect/remember/stop）只是 `region = phase:<name>`，不携带任何调度特权；六阶段闭集不再构成 SSOT（0075/0194 迁移见 §10 P7） | 编译失败 / 迁移期回归测试 |

**「工具结果没灌入下次模型所见」** ≡ 违反 C1∪C2∪C3。ADR-0201 已用真实 run 复现该故障并做了线性 fold 修补；本文用编译器把它变成静态错误，不靠约定与 fold 覆盖率。

**「万物皆图」反演**：C11–C14 把"图嵌套 / 单图种"变成编译期可校验的不变量，而非口号。子图与父图之间、子图与 view 之间、region 标签与调度之间的所有缝隙都由编译器封口。ADR-0086 退役 LoopTopology 的判据（无消费者）不适用于本设计：嵌套 InfoEdgeSpec 全部由 Binding 调度器 / Join 管理器消费，是有 consumer 的。

---

## 4. 跨图借用（蚂蚁隐喻的工程化）

```yaml
grants:
  - id: think_read_digest
    from_spec: digest.tools
    to_spec: think.default
    ports: [digest.tools.last]
    mode: read
    constraints: { max_bytes: 8000, redact: secrets }
```

没有 grant 的 `borrow` 引用 → 编译失败（C4）。跨图只借 **artifact/fact id**，禁 live 对象指针；这比「共享 blackboard」更接近人类协作：能用哪块信息、怎么用、什么约束。隐喻止于 Grant / Borrow，信息素 ≠ 可审计边。

---

## 5. 最小骨架与运行时语义

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
    projection_closure,          # 哪些 InfoNode 输出可达 ModelContextAssembler 输入
    effect_receipt_map           # 每个 effect edge → 回执端口 → project | discard
```

### 5.1 编译产物：CompiledGraphBundle

```text
Graph 配置 → Parse → Resolve（图引用展开）→ Analyze（死节点/unbound port/环/capability）
         → Compile → CompiledGraphBundle
              plan_hash · graph_hash · policy_hash
              bindings · join_table · route_table · observability_points
```

**Recovery**：`plan_hash` 不匹配 → 拒绝恢复（防图变更后 replay 语义漂移）。热更新 InfoEdgeSpec 产生新 Plan 版本；进行中 Run 钉死旧 `plan_id`。

### 5.2 每个阶段都是 graph.call，不是函数

六个阶段（perceive / think / act / reflect / remember / stop）都是 `graph.call` —— 引用一个嵌套的 `InfoEdgeSpec`，子图内部是工人流水线。`think` 只是第一个被显式建模的：

```text
phase.perceive ─► InfoEdgeSpec.phase.perceive  (workers: observe.input, observe.normalize)
phase.think   ─► InfoEdgeSpec.phase.think    (workers: context.assemble → llm.reason → llm.critic → decision.synthesize)
phase.act     ─► InfoEdgeSpec.phase.act      (workers: tool.intent → grant.check → executor.dispatch → receipt)
phase.reflect ─► InfoEdgeSpec.phase.reflect  (workers: outcome.classify → lesson.extract)
phase.remember─► InfoEdgeSpec.phase.remember (workers: memory.commit, fact.commit)
phase.stop    ─► InfoEdgeSpec.phase.stop     (workers: terminal.emit, projection.finalize)
```

每个阶段子图通过 `sub_spec` 边挂到根图的对应阶段节点上。每个工人声明：`responsibility`、`inputs`（从哪个图的哪个 port）、`outputs`、`on_failure` 路由、`capabilities`。父图通过 **export port** 消费子图输出；禁止字符串路径读子图内部（C12）。嵌套深度无硬限制，但每多一层都增加一次 `subgraph_path` 记录（C13）。

**阶段闭集迁移**：原本由 `CognitivePhaseGraphPlan` 强制枚举的六阶段（0075/0194）现在退化为 `region = phase:<name>` 的 region 标签值集合。编译器仍校验 region 标签属于已知集，但**标签值不绑定调度特权**（C14）；用户可在 profile 中扩展自定义 region（如 `phase:plan`、`phase:replan`），只要 region 内节点通过校验。这是「万物皆图」从口号变成机制的关键：阶段从编译期闭集退化为 region 标签。

### 5.3 模型可见：Context Assembly 子图 → frozen ContextManifest

每次 LLM 调用前，`InfoEdgeSpec.mv.assemble` 子图运行一次，输出 frozen `ContextManifest`。该子图本身就是 InfoEdgeSpec 的合法嵌套形态：

```text
InfoEdgeSpec.mv.assemble (region = model_visible)
  inputs: system_prompt · in_think · in_tool_results · in_memory
  workers:
    - trust.classify  (in: tool.results.out, out: labeled_results)
    - dedup.collapse  (in: labeled_results, history, out: deduped)
    - order.rank      (in: deduped, budget_policy, out: ranked)
    - redact.sanitize (in: ranked, secrets_policy, out: sanitized)
    - assemble.merge  (in: system_prompt, in_think, sanitized, out: messages)
    - validate.commit (in: messages, out: ContextManifest)
```

根图节点的 `in_tool_results` 端口通过 `data` 边 Binding 自 `effect.dispatch.receipt` 输出；缺 Binding → 编译器报 `UNBOUND_PORT`。子图出口 `validate.commit` 的输出就是 `ContextManifest`，沿 `sub_spec` 边回到根图节点的对应端口，再由根图的 `mv.commit` 节点将其冻结并喂给 LLM。`ContextManifest` 的消息 schema 沿用 0204 的 typed OpenAI*Message 契约；`ModelContextAssembler`（0193/0201）是根图出口层的装配链，子图内部是更细粒度的工人流水线。

**调试**：dump `InfoEdgeSpec.mv.assemble` 子图 + `subgraph_path` + `ContextManifest.digest` 三件套，模型确切输入完全可重放。模型所见 = 子图回放，零猜测。

### 5.4 Effect 子图与闭环

`InfoEdgeSpec.effect.dispatch` 子图（region = effect）承载完整的 effect 生命周期：

```text
InfoEdgeSpec.effect.dispatch (region = effect)
  inputs: tool.intent, grant.context
  workers:
    - grant.check       (in: tool.intent, grant.context; out: grant.verdict)
    - approval.wait     (in: grant.verdict; out: approval.result)   # control 边可挂起
    - executor.dispatch (in: approval.result, budget.reservation; out: EffectReceipt)
    - receipt.commit    (in: EffectReceipt; out: receipt.fact)
    - observation.integrate (in: receipt.fact; out: observation.delta)
    - mv.feed           (in: observation.delta; out: mv.binding_target)  # project 边连到 mv 子图
```

根图的 `phase.act` 节点持有 `sub_spec = effect.dispatch`；子图出口 `mv.feed` 通过 `project` 边 Binding 到 `InfoEdgeSpec.mv.assemble` 子图的 `in_tool_results` 端口，**完成 effect→observation→model-visible 的跨子图闭环**。Receipt 写 Journal；Observation 经 Reducer 更新 State 投影；只有经 `project` 边进入 `mv.assemble` 子图输入端口的字节才可进 `ContextManifest`（对齐 0201 MV 闭包，由 C1/C12 静态校验）。

### 5.5 并行与合流

```yaml
# 概念
- type: parallel
  branches: [research.web, research.code, research.docs]
  join:
    strategy: all_complete | first_success | quorum(n)
    on_partial: route_to(synthesizer.with_gaps)
```

无 Join 声明的 parallel → 编译错误（C7）。节点调度：`ready ⟺ 全部 required input satisfied ∧ grant_ok ∧ 不在 abort 传播链`。

### 5.6 错误处理是路由边，不是 try/catch

| 错误类 | 语义 | 默认路由 |
|---|---|---|
| `deterministic` | 契约/输入错误 | 不重试 → reflect → 可能 stop |
| `transient` | 网络/超时 | 退避重试 → 同一节点 |
| `policy` | 权限/审批拒绝 | → gate.rejected → HIL |
| `budget` | token/步数/成本超限 | → stop.budget_exceeded |

认知层错误产生 Decision(rejected)；Gate 错误产生 Verdict(rejected)；Body 错误产生 Effect Receipt(error)——沿用 AGENTS.md §3 错误分类。

### 5.7 配置生效证明（八项）

§5 描述的是结构。本节回答：**凭什么说某条配置在生产真的生效**——配置存在、编译纳入、运行时拦截、结果可见四层证据缺一不可。每条都必须有对应金丝雀（§9.1）。

| # | 证明 | 证据点 | 金丝雀 |
|---|------|--------|--------|
| **E1 Deployment Manifest** | 每次部署产生含 phase_graph / InfoEdgeSpec / effect_policy / action_authority / 模型 / 价格版本的 hash；运行事件携带该 hash | `CompiledGraphBundle.plan_hash` 写入 `GraphRunStarted` | §9.1 canary-A |
| **E2 Provider Request Capture** | 模型适配器出口捕获 canonical request hash，与 frozen `ContextManifest` digest 字段比对；不一致即阻断或隔离 | 适配器出口 hook + ContentManifest digest 必填 | §9.1 canary-A / canary-C |
| **E3 Port Enforcement** | Artifact/Port 读取经 schema / producer / tenant / classification / version / capability 校验 | Effect Gateway 入口 + ModelContextAssembler 输入端口校验 | §9.1 canary-B |
| **E4 Effect Egress Enforcement** | 所有出站 effect（tool / DB / 网络 / 文件系统 / MCP）带 Gateway-issued `effect_id`、policy decision、budget reservation、lineage headers | 出站代理 + effect_id 全局唯一 + reservation 必填 | §9.1 canary-C / canary-F |
| **E5 Journal Integrity** | 事件 append-only + hash chain 或签名；Reducer 版本化、可重算 | EXECUTION_POINTS 入账带 prev_hash；篡改报警 | §9.1 canary-H |
| **E6 Budget Reservation** | BudgetGuard 集中 API 原子预留/结算；不允许节点本地计数 | reservation 在 effect dispatch 前 commit；usage 延迟回传不破坏预留原子性 | §9.1 canary-F |
| **E7 Lineage Reverse Lookup** | 从最终 Artifact hash 反查 ContextManifest / 模型请求 / 工具调用 / 审批 / Receipt | provenance 索引 + effect_id ↔ artifact_id ↔ approval_id 三向连接 | §9.1 canary-H |
| **E8 Negative Tests** | 删除配置、绕过节点、修改参数、直接调工具、用过期 approval、跨租户读、超预算调用——必须失败 | CI 必备；缺少任一条即视为覆盖不成立 | §9.1 canary-G |

**不能声称已覆盖**的情形：E2 缺实际请求捕获而仅做静态对照；E4 仅声明 policy 不强制出站拦截；E5 仅做 append-only 不做完整性校验；E6 用节点本地计数冒充集中预留。每一项被列为「红」即整张覆盖矩阵降级。

---

## 6. 目标架构与一次合法编译

```text
                    ┌──────────────────────────────────┐
                    │  Profile / Bundle (配置)          │
                    │  InfoEdgeSpec.root + 嵌套子图 +   │
                    │  grants + region 标签             │
                    └──────────────┬───────────────────┘
                                   │ Compile (C1–C14)
                                   ▼
                    ┌──────────────────────────────────┐
                    │  CompiledRunPlan                  │
                    │  effect_policy · action_authority │
                    │  InfoEdgeSpec (根图 + 子图树)     │
                    │  info_edge_report (closure)       │
                    └──────────────┬───────────────────┘
                                   │ GenericPlanInterpreter (递归)
                                   │ (Binding 调度 / Join / 路由)
           ┌───────────────────────┼───────────────────────┐
           ▼                       ▼                       ▼
   Spine/Fact SSOT           Effect Gateway           mv.assemble 子图
   (0167 append)             (tool·guard·HIL)          (region = model_visible)
           │                       │                       │
           └────────── auditable nested edge fires (C13) ──┘
```

**解释器保持极薄**：递归调度根图与所有嵌套子图、点火边（含 subgraph_path）、写回执；**不允许**在解释器里「顺手」往上下文塞字符串——那会再次破坏 C1；**不允许**为子图另立解释器——那会破坏 C11。

### 6.1 一次「想→工具→再想」的合法嵌套编译形态

```text
根图 InfoEdgeSpec.root
  ├─ phase.think   ─sub_spec─►  InfoEdgeSpec.think.default    (region = phase:think)
  ├─ phase.act     ─sub_spec─►  InfoEdgeSpec.effect.dispatch  (region = effect)
  └─ mv.commit     ─sub_spec─►  InfoEdgeSpec.mv.assemble      (region = model_visible)

InfoEdgeSpec.think.default
  think_out ─project► mv.assemble.in_think                    (跨子图 project 边)

InfoEdgeSpec.effect.dispatch
  receipt.fact ─project► mv.assemble.in_tool_results          (跨子图 project 边)
  executor.dispatch ─data► receipt.commit ─data► observation.integrate

InfoEdgeSpec.mv.assemble
  validate.commit ─data► ContextManifest ─data► ModelContextAssembler.messages
  ModelContextAssembler.messages ─► openai_messages_with_history   # 唯一模型输入
```

缺 `sub_spec` 边、跨子图 `project` 边、或子图 `export` 与父图 `in/out` 端口 schema 不匹配 → **Compile Error: C11/C12/C2/C3**。这就是「嵌套子图 + 跨子图 project 边的流水线工人互相依赖、声明清楚」。

### 6.2 Think 作为嵌套子图（region = phase:think）

```yaml
info_edge_spec:
  id: think.default
  region: phase:think
  nodes:
    - { id: retrieve, role: "检索相关记忆", region: phase:think, ins: [user_turn], outs: [snippets] }
    - { id: plan, role: "提出下一步", region: phase:think,
        ins: [snippets, { borrow: { grant: think_read_digest, port: mv.assemble.last_assembled } }],
        outs: [intent] }
    - { id: join, role: "汇合屏障", region: phase:think, ins: [intent], outs: [think_out] }
  edges:
    - { from: retrieve.snippets, to: plan.snippets, kind: data }
    - { from: plan.intent, to: join.intent, kind: data }
    - { from: join.think_out, to: mv.assemble.in_think, kind: project }   # 跨子图 project 边
  export: [think_out]  # 父图通过 export port 消费
```

并行：`retrieve` 与其它工人可并行，经 `join` 汇合后再 project。父图通过 `sub_spec = think.default` 边挂载该子图；C12 校验父图节点 `in/out` 端口 schema 与子图 `export` 端口一致。

### 6.3 模型所见：嵌套子图 + 装配链双层闭环

```text
InfoEdgeSpec.mv.assemble (region = model_visible)
  → ContextManifest → ModelContextAssembler (0193/0201)
    output: openai_messages_with_history
```

模型可见 = `mv.assemble` 子图执行 + 根图出口层 `ModelContextAssembler` 装配，两层都走 InfoEdgeSpec。**唯一**允许喂给 LLM 的是 `ModelContextAssembler` 装配后的 `messages`；编译器验证其每个输入端口在 `projection_closure` 中可达，且所有 `model_visible` region 内的节点输出都进入 `mv.assemble` 子图（C1 + C11 + C12）。对齐 0185：写入投影的内容必须可审计。观测层 `ProjectionSpec`（ADR-0198 已占用，语义是 deriver 注册）名称不让渡。

---

## 7. 可观测 / 审计 / Debug（天生）

每条边点火至少记录：

```text
edge_fire{ plan_id, edge_id, kind, from, to, seq, bytes?, grant_id? }
node_start / node_end{ node_id, duration, error? }
model_visible_commit{ content_digest }
effect_receipt{ tool_call_id, status }
```

关键事实事件（复用/扩展现有 EXECUTION_POINTS 闭集，不平行造词表）：

| 事件 | 最小字段 |
|---|---|
| `GraphRunStarted` | run、plan_hash、grant snapshot |
| `NodeAttemptStarted` | graph_path、node、input_refs |
| `ContextManifestCommitted` | model、included/excluded refs、digest |
| `EffectReceiptCommitted` | tool_call_id、status、result_refs |
| `JoinResolved` | branch states、merge policy |

稳定关联键：`execution_id`、`graph_invocation_id`、`node_attempt_id`、`artifact_id`、`tool_call_id`。Trace 是投影，不是事实源。

Debug UX（产品形态，非本 ADR 实现）：控制图（经过的节点/边/循环/失败路由）、数据图（Artifact lineage：input digest → transform → output digest）、可见性图（ContextManifest 包含/排除内容及原因）。缺边标红在编译期；「模型所见」一键展开 = 投影闭包回放；「此 tool 结果为何不可见」→ 查有无 project / Discard 边。

---

## 8. 反模式（Reject）

| 反模式 | 为何有害 | 正确做法 |
|--------|----------|----------|
| 上帝图（一切塞一张根图，无嵌套） | 不可维护、不可替换 | 根图 + 嵌套 InfoEdgeSpec |
| 平行图种（PhaseGraph / ContextGraph / EffectGraph / LineageGraph 并列存在） | 多 Runtime、多事实源 | 单一 `InfoEdgeSpec` + region 标签；C11 |
| 无类型黑板 / 全局 state | 隐式依赖，编译器失明 | Port + Edge + Grant only |
| 解释器里拼 prompt | 绕过投影闭包，C1 失效 | 只经 `mv.assemble` 子图 → `ModelContextAssembler` |
| 工具成功无回执边 | 「跑了但看不见」温床 | C2 + `effect.dispatch` 子图强制 |
| 跨图裸 import / live 指针 | 提权与纠缠 | `sub_spec` 边 + Borrow/Grant（只借 id） |
| 热拔 Spine / 主循环 | 破坏真值链 | kernel 闭集 |
| 第二 Runtime「信息图引擎」 | 平行真相 | 校验进既有 Plan；同一 `GenericPlanInterpreter` 递归 |
| 把「阶段闭集」当成 SSOT 锁 | 与 region 标签机制冲突；0075/0194 迁移阻塞 | C14 阶段退化为 region；§10 P7 迁移 |
| 蚂蚁隐喻当实现 | 信息素 ≠ 可审计边 | 隐喻止于 Grant / Borrow |
| 配置即图灵泥潭 | 不可推理 | 工人有限原语 + 声明式嵌套边 |

### 8.1 不可替代边界（图配置不能覆盖的部分）

§1.3 已声明「结果覆盖」不由本框架承担。本节列出具体边界，避免把框架承诺当成业务承诺。每条边界必须有外部 owner；缺 owner = 留待后续 ADR/Note 增补。

| 边界 | 框架能做到 | 必须由外部承担 |
|------|------------|----------------|
| **模型能力与事实性** | 约束模型看到的内容、输出 schema、必经校验路径 | 模型规划正确、事实真实、摘要保真、抗 prompt injection、judge 独立——需要评测、红队、可信数据源、确定性规则、人工复核 |
| **供应商内部语义** | 引用 schema、冻结版本 | 未公开的 prompt 模板、服务端 conversation 展开、tokenizer、工具消息格式、缓存——需要 provider adapter contract test + 实际请求捕获（E2） |
| **外部副作用 exactly-once** | Effect 必须有 receipt + project/discard（C2/C3）；未知状态进入对账路径 | 邮件/支付/DB/浏览器表单/第三方 API 不自动 exactly-once——需要目标系统幂等键、事务、状态查询、补偿协议、人工例外 |
| **身份与权限** | GraphSpec 引用 policy 与 capability，Borrow 不可提权（C4） | IAM / RBAC·ABAC / 职责分离 / OAuth·2FA / secret vault / 网络隔离 / 沙箱——平台与安全基础设施 |
| **数据治理与合规** | Journal append-only 与 provenance 反查（E5/E7） | PII 发现、数据主权、保留删除、密钥管理、WORM 存证、SIEM、访问审计——DLP / KMS / 合规存储 |
| **运行时与运营** | Plan hash 锁 + 恢复拒绝（§5.1）；effect 未在途即可停 | 持久化状态、消息队列、租约、灾备、资源隔离、并发控制、强制取消、告警、值班、SLO——workflow / runtime / platform |
| **组织政策与业务责任** | 强制声明 + 留 audit 字段 | 预算阈值、审批规则、补偿口径、风险接受、最终验收标准、人工责任归属——组织政策与人工 |

**写作纪律**：本节存在后，§0.1 删除条件、§10 退出标准、§11 后果段不得再使用「本框架保证 / 我们确保」类表述，只能用「约束 / 强制声明 / 留 audit 字段 + 由 X 实施」。

---

## 9. 场景矩阵与金丝雀验收

### 9.0 场景矩阵（结构覆盖）

| 场景 | 期望 |
|------|------|
| 单工具成功 | receipt → digest → project → 下次 think 可见 |
| 单工具失败 | 失败回执 → 策略节点（retry/deny/expose_error）→ 显式错误或 Discard |
| 并行多工具 | Barrier/Join 汇合后统一 digest/project |
| 工具需审批 | control 边挂起；resume 后同一 effect 身份续跑（0078/0173） |
| Think 工人部分失败 | `on_error` 路由；不得半投影 |
| 借用端口超 cap | 运行拒绝 + 审计 |
| 热更新 InfoEdgeSpec | 新 Plan 版本；进行中 Run 钉死旧 plan_id |
| 回放 | 只按 Spine + 边点火重放投影，不重放副作用（除非明示） |

### 9.1 MVP 金丝雀验收（运行覆盖入口）

§9.0 描述结构层面；本节描述**运行层面**的硬验收。每条金丝雀必须可由 CI 触发并产出红/绿；任意一条被列为红，覆盖矩阵整体降级。金丝雀与 §5.7 八项证明同表对齐。

**canary-A · 上下文金丝雀。** 固定任务，注入 allow / deny / 一次性读取 / 已摘要 / 恶意工具结果 / 人工 resume 输入；捕获每一次 provider request。
**验收**：内容、顺序、版本、source、hash、token 预算 = frozen `ContextManifest`；secret / deny Artifact / 跨租户 Artifact / 未批准恢复值 / 未声明工具不出现；Manifest 漂移即阻断。
对应：E1 + E2。

**canary-B · 工具闭环。** 同一 call ID 分别注入成功 / schema 错 / 恶意文本 / 大对象 / 重复 / 超时。
**验收**：合法结果以唯一 call ID 入 Receipt；恶意文本标不可信，不能改变执行授权；大对象以 Artifact URI 传递；重复 effect 不重复提交；超时进入 unknown 或对账，不静默重试。
对应：E3 + C2/C3。

**canary-C · 审批不可绕过。** 从顶层图、嵌套子图、handoff、agent-as-tool、Task callback、Browser custom action、恢复节点发起同一高风险 effect。
**验收**：仅经 Effect Gateway + 参数 hash 匹配 + 策略版本匹配 + actor/role 匹配 + 未过期 approval token 才执行；否则一律阻断。
对应：E3 + E4 + C4。

**canary-D · 并发确定性。** 一百次 fan-out/fan-in，随机延迟、重复投递、分支失败、父图取消、同 key 并发写。
**验收**：Reducer 输出 hash 恒定；Join policy 一致；取消后不再有新调度；分支状态可追踪、不跨租户泄露。
对应：C6/C7。

**canary-E · 崩溃恢复。** 在 effect 的「已计划 / 已发出 / 远端已提交 / receipt 未写入 / checkpoint 已写入」五个时点杀 worker 再恢复。
**验收**：每个逻辑 effect 在接收侧至多一次成功，或明确进入 unknown / 人工对账；不得无 receipt 静默成功。
对应：C2 + C8。

**canary-F · 预算竞争。** 两个并发 run 在全局余额边缘同时申请模型 / 工具 / 浏览器资源，延迟 usage 回传。
**验收**：预留原子；超额后无新出站；未执行预留可释放；usage 按租户 / 图 / 节点 / effect 归因。
对应：E4 + E6。

**canary-G · 验证变异。** 分别删除或短路 input schema、effect policy、最终业务断言、敏感性 validator、审批检查。
**验收**：对应负面用例穿透并令 CI 失败——证明验证器不是只存在于 YAML。
对应：E8。

**canary-H · 审计反查与篡改。** 跑完一次完整 lineage 后，反查最终 Artifact hash；再篡改一条 Journal 记录、执行 PII 删除、用无权限角色查询。
**验收**：完整性报警；最小合法证明链；删除策略生效；越权拒绝；effect receipt 验证通过。
对应：E5 + E7。

**canary-I · 取消语义。** 分别在模型调用、长工具、浏览器动作、审批等待期间发 cancel 或 timeout。
**验收**：停止新调度；显式列出在途工作与最终 receipt/unknown；cancel、drain、ExternalTermination、runtime.stop 不得误报为外部写入已撤销。
对应：C8 + §8.1「运行时与运营」边界。

---

## 10. 落地阶段（诚实切片）

合并后单一路径（0206.1–6 与 0207 P0–P3 是同一工作的两套编号，已收敛）：

| Phase | 内容 | 退出标准 |
|-------|------|----------|
| P0 | 本体词汇对照表 + 命名冲突结论；Schema：`InfoEdgeSpec`/`InfoNode`/`InfoPort`/`InfoGrant` + `CompiledGraphBundle` + Analyze 规则 | JSON Schema + 示例；unbound port 编译失败测试 |
| P1 | 编译器 C1–C10 静态检查 | 「缺 project 边」用例红→绿 |
| P2 | 模型可见闭包接到 `ModelContextAssembler`，输出 frozen `ContextManifest` | 任意 LLM turn 可 dump 完整输入；模型输入唯一出口测试；canary-A 红→绿 |
| P3 | Effect→Observation→Context Binding + 效应回执强制 + 出站代理拦截 | 无回执无法 Compile；0201 失明场景（`run_640c492b7f40`）从红变绿；canary-B / canary-C 红→绿 |
| P4 | Parallel/Join + 错误路由边 + Borrow/Grant + 预算原子预留 | 并行 tool 全 join 后才 synthesize；跨图无 grant 失败；canary-D / canary-F 红→绿 |
| P5 | edge_fire 观测面 + Journal 完整性 + lineage 反查 | doctor/时间线可查；canary-H 红→绿 |
| P6 | 崩溃恢复与取消语义 + 验证变异 + 跨租户旁路 | canary-E / canary-G / canary-I 红→绿；§8.1 边界逐条标 owner |
| P7 | 阶段闭集迁移：六个 phase 子图化 + `CognitivePhaseGraphPlan` 退役评估 | `region = phase:<name>` 全量使用；canary 子图嵌套一致性；0075/0194 迁移 Owner 登记在 Agent Note |
| P8 | 模型可见 / 效应 / 溯源全部子图化（`mv.assemble` / `effect.dispatch` / `lineage.index`） | 三个子图分别落地；与 P3/P5 同 canary 全绿；不再有"派生视图"概念 |

**顺序约束**：先编译器不变式（P0–P1），再运行层强制（P2–P5），最后运行/结果混合验收（P6）。禁止未 Compile 先上「灵活脚本」。schema bump 0068/0075 计划族，不开第二 Runtime / 第二 Journal。

---

## 11. 后果

**正**：细节漏洞结构上可灭；配置化工人 + 并行；跨图协作有约束；debug/审计一等公民；与 LCA 缝同构可演进；通过 §9.1 金丝雀可向业务方证明「配置真的生效」。

**代价**：前期 Schema/Compiler 成本；团队要学 Port/Edge 思维；拒绝「先跑通再补边」；P6 之前不能宣称覆盖成立。

**风险与缓解**：DSL 膨胀 → 原语最小化 + 嵌套深度可读性约束（每图 ≤ 5 层建议；超过需 Agent Note 评审）；与 0075/0194 双轨 → §10 P7 显式承担迁移，P7 未完成前 `CognitivePhaseGraphPlan` 保留；「万物皆图」幻觉 → C11 单图种 + C13 嵌套点火可见 + §9.1 canary 子图嵌套一致性；「配置即生效」幻觉 → §5.7 八项证明 + §9.1 金丝雀 + §8.1 不可替代边界三者并列声明；ADR-0086 反例 → 嵌套 InfoEdgeSpec 必须保证 Binding 调度器 / Join 管理器 / 路由求值器 三组件实际消费全部 region，否则该 region 即"无消费者"应删除。

**承诺边界**：§8.1 列出的七类外部依赖若 owner 未到位，对应金丝雀必须保持红，不得以「未来会接」为由放行。

**与 0075/0194 的边界**：本 ADR 把 `CognitivePhaseGraphPlan`（0075）的六阶段闭集与 `cognitive-loop-architecture-convergence`（0194）的 Loop 收敛**降级为 region 标签机制**，由 §3 C14 + §10 P7 显式承担迁移。这意味着 0075/0194 的部分语义被吸收、部分被 supersede。**完成 P7 之前 0206 不算 Accepted**，且 P7 自身必须新开 ADR（避免本 ADR 一边 supersede peer 一边通过）；该 ADR 已分配为 ADR-0210（详见 0210 §一 / §二 迁移切片）。

---

## 12. 决策记录

**Adopt**：§1 本体（词根 `InfoEdge*` + `ContextManifest` + `CompiledGraphBundle`）+ §1.2 三层覆盖（expression / runtime / outcome）；§2 单一可执行图 + 嵌套子图切法（六个阶段子图 + mv/effect/lineage 子图）；§3 不变式 C1–C14（含 C11 单图种 / C12 子图端口一致 / C13 嵌套点火可见 / C14 阶段标签退化为 region）；§5 运行时语义（**所有阶段 = graph.call**、mv 子图装配、effect 子图闭环、Binding/Join/路由三组件）+ §5.7 八项生效证明；§8 Reject + §8.1 不可替代边界；§9.0 场景矩阵 + §9.1 MVP 金丝雀验收；§10 切片 P0–P8。
**Absorb into LCA seams**：`InfoEdgeSpec` ⊆ `CompiledRunPlan`，**非**新 Runtime；解释器仍是 `GenericPlanInterpreter`（0075），新增 Binding 调度器 / Join 管理器 / 路由求值器；根图与子图共用同一解释器递归；模型可见由 `mv.assemble` 子图 + `ModelContextAssembler` 双层装配；观测 `ProjectionSpec` 名称不让渡。
**Supersedes**：0207（同批图编排运行时语义，已并入本文）。
**Required follow-up ADR**：P7 阶段闭集迁移已开 [ADR-0210](0210-stage-closure-migration-p7.md) (**Accepted 2026-09-09**)；该 ADR 显式处理 0075（`CognitivePhaseGraphPlan` 退役路径）与 0194（Loop 收敛与 region 标签兼容）的迁移。0206 升 Accepted 条件 = **ADR-0210 升 Accepted ✓** + ADR-0210 §6 验收全绿 ✓（见 commit `f6452bd5` 写真实 `profiles/web-assistant.yaml` 验证）。
**Accepted 条件**：P0–P3 完成；§9.1 canary-A / canary-B / canary-C 至少一条合入 CI；§8.1 七类边界的外部 owner 在 Agent Note 内逐一登记；P7 阶段迁移 ADR 起头；P7 完成前 0206 状态保持 Proposed。

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

Industry「看不见」的十条防线与 §3 C1–C10 对齐，可逐条做 CI：Effect→Consume 闭包、投影完备门、禁环境读、端口类型、能力充足、单写/reducer、Journal 先于投影、interrupt 幂等、跨图 borrow 约束、并行写集屏障。

## 附录 B — 给编码代理的强制提问

1. 新逻辑是 InfoNode / InfoEdge / InfoGrant，还是又在解释器里 if？
2. 模型将见到的字节，投影闭包路径是哪条？
3. 每个 effect 的 receipt 与 project / Discard 边在哪？
4. 跨图读的 InfoGrant id？
5. 是否触碰 kernel 闭集（Phase / Envelope / Manifest）？
6. 删除条件？

## 附录 C — 一句话给业务方

> 我们不是「把 agent 画成流程图好看」，而是**用编译器保证信息流水线上每个工人的输入输出来自声明，从而工具、思考、所见、校验不会再靠默契对齐。**

## delete-when

```text
隐式 history 拼 prompt 路径:
  delete_when: rg 'assemble_model_history' 全路径经 ContextManifest；
              pytest 断言缺 Binding 编译失败

临时 bridge 节点（tool→context 手工拷贝）:
  delete_when: CI analyze 对 C1–C3 全绿 + 0201 MV 测试通过
```

---

*ADR-0206 Proposed — 2026-09-08（吸收 0207）*