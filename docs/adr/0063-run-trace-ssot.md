# ADR-0063：统一运行事件账本、插件化投影与 Coding Agent 轨迹检查

## 状态

**Accepted — 2026-08-20；本次记录完整覆盖原 ADR-0063。**

本 ADR 细化并继承 [ADR-0037](0037-journal-as-truth.md) 的 **Journal-as-Truth** 决策，替代此前“Journal 事实流 + 平行 `DiagnosticStream` 诊断流”的双流设计。它同时吸收仓库的 日志系统评估（已归档） 与用户提供的“业界范式 + 面向 Coding Agent 的日志插件设计”材料：DeepSeek Harness 的 Session 追加事件流与插件投影边界、OpenTelemetry GenAI 的互操作追踪模型，以及 Langfuse 的 trace / observation 关联模型。[1] [2] [3]

> **核心决策：每次运行只有一个可追加事件账本；事实、结构生命周期与运行解释共享同一封套和因果链。任何 JSONL、SSE、控制台、OTel、Langfuse、诊断摘要或 Coding Agent 工具结果都是已提交事件的只读投影。**

## 背景与问题陈述

LCA 已拥有 `JournalEvent → RunStore.append()` 的事实记录路径，但实现逐渐偏离第一性原理。`RunStore` 同时承担追加、订阅、缓存查询、派生洞察和兼容读取；`InsightEngine` 作为订阅者反向 `append(RunInsight)`；`DiagnosticStream` 又重新分配独立序号；`ContextManifest` 存在双写开关；进程级实时分发曾重铸每条事件的 `seq`。这些机制使“发生了什么”“为何如此发生”“如何发给用户”和“如何给外部系统导出”分散在不同所有者中。

日志评估进一步指出，两套词表、多个 `ContextVar`、重复的投影状态、写入期深拷贝、读取期 predicate 缓存，以及 JSONL / SSE / OTel 各自处理安全与可见性的做法，会使 schema 演进成本和排障复杂度呈乘法增长。最严重的后果不是代码冗余，而是 Coding Agent 无法从单个稳定因果图回答以下问题：哪个插件参与、谁触发谁、上下文为何被注入、工具或代码为何失败、数据如何跨 transport 传输、哪里最慢、最小复现应保留哪些事件。

用户提供的范式材料强调，成熟 Agent Harness 将运行看作可追加轨迹：**模型可见内容必须可重建；状态是投影；事件带稳定序列、时间、类型、作用域与因果父引用；外部 telemetry 只是投影。** 这与 DeepSeek Harness 的 Surface / Structural / Log-only 事件分层一致，也与 OpenTelemetry 将 trace 作为操作关联模型、而非业务事实库的定位一致。[1] [2]

## 决策驱动因素

| 驱动因素 | 架构要求 |
|---|---|
| 可恢复、审计、重放 | 一个严格追加、顺序稳定、提交后可读的运行账本。 |
| Agent 可解释性 | 插件、Hook、LLM、工具、记忆、权限、代码与传输行为必须与领域事实在同一因果图中可查询。 |
| 最小原语 | 核心写路径只做验证、治理、盖章、原子追加、提交后发布；不维护查询缓存、洞察状态或 UI 状态。 |
| 插件化 | 新导出后端、新展示、新摘要和新分析只能作为投影插件加入，不能反向影响账本。 |
| 数据治理 | 脱敏、详细程度、可见性、敏感等级和外部导出许可必须在统一描述符与写入边界执行。 |
| Coding Agent 消费 | 提供小、稳定、机器可读的检查 API，而非要求 Agent 扫描完整 JSONL 或解析人类控制台文本。 |

## 第一性原理与不可变约束

运行事件账本不是“更多日志”，而是系统在某次 `trace_id` 下发生行为的最小可验证历史。任何能改变状态、解释运行边界或让模型 / 操作者理解执行过程的记录，都必须拥有一个稳定的账本事件身份；任何派生产物都必须能被丢弃和重建。

| 编号 | 约束 | 说明 |
|---|---|---|
| **I1** | **一次发生，一次追加** | 一个生产运行事件只经 `RunStore.append()` 提交一次；不得同时写 Journal、诊断流和私有文件。 |
| **I2** | **提交先于观察** | 投影器仅接收已经进入账本的事件；投影器异常不改变 Agent 领域执行。 |
| **I3** | **事件序列不可重铸** | `seq` 是所属 run 账本的提交顺序。跨 run 实时聚合必须使用独立 transport cursor 或 `(trace_id, run_id, seq)`，绝不覆写 `seq`。 |
| **I4** | **投影永不回写** | 投影、摘要、洞察、SSE、OTel 与 JSONL 不得向同一账本追加“跟随事件”。 |
| **I5** | **策略先于持久化和外送** | 文本脱敏、截断、可见性和敏感等级在追加边界统一执行；外部投影不得重新自行猜测安全策略。 |
| **I6** | **动态扩展不扩张核心原语** | 新插件可发 `RuntimeObserved` 或新增已登记类型；不得再建立第二个 EventBus、第二条诊断序列或自建 JSONL。 |
| **I7** | **分析按需派生** | 失败路径、成本、瓶颈、交互图和最小复现由只读检查器生成；不在写路径维护 predicate 缓存或 mini store。 |

## 目标架构

### 事件封套与三平面

LCA 保留 typed `JournalEvent` payload，以保护领域语义；所有 payload 被 `StampedEvent` 盖章为统一运行记录。封套保留既有 `seq`、`ts`、`RunScope`、`turn`、`event_type`、`data` 与 `correlation_ids`，并新增可选 `parent_seq`。`parent_seq` 只表达事件级直接因果；跨 run、跨委派和跨外部调用仍以 `RunScope` 的 `trace_id`、`run_id`、`parent_run_id` 与 `delegation_id` 表达。

| 平面 | 事件内容 | 典型类型 | 能否驱动恢复 / reducer |
|---|---|---|---|
| **Surface** | 用户、模型或工具结果可见的内容和引用 | `InboxFollowupCreated`、`StepTextDelta`、`ToolInvoked`、`ContextManifested` | 是；内容遵从更严格的可见性和保留策略。 |
| **Structural** | run、委派、step、LLM、工具及审批生命周期 | `AgentRunStarted`、`DelegationIssued`、`LlmCallCompleted`、`ToolStarted`、`RunPaused` | 是；用于重放、状态归约和完整性检查。 |
| **Explanation** | 运行如何由插件、Hook、适配器和数据边界完成 | `RuntimeObserved` | 否；它解释运行，但不替代领域事实或改变 reducer。 |

`RuntimeObserved` 是统一解释原语，不是另一个诊断封套。它使用稳定 `RuntimeKind`（`agent`、`plugin`、`hook`、`llm`、`tool`、`memory`、`transport`、`code`、`permission`、`compaction`、`error`、`retry`）和 `OperationOutcome`（`started`、`ok`、`error`、`cancelled`、`retry`），携带 `operation`、`source`、`duration_ms`、受策略治理的 `attributes` / `output`、错误摘要、是否可重试及 `causation_refs`。推荐操作名使用稳定点分命名，例如 `plugin.interaction`、`context.injected`、`permission.decided`、`code.execution`、`transport.receive`。

```mermaid
flowchart LR
    P[Agent / 插件 / Hook / 适配器] -->|record(领域或结构事件)| W[RunStore.append]
    P -->|observe(运行解释)| W
    W -->|验证 + 策略 + 盖章 + 原子提交| L[单一运行事件账本]
    L --> R[ProjectionRegistry]
    R --> J[JSONL 持久化投影]
    R --> S[SSE / LiveTail 传输投影]
    R --> C[Console / FactStream 视图]
    R --> O[OTel / Langfuse 投影]
    R --> D[诊断 JSONL 兼容投影]
    L --> T[TraceInspector：只读检查]
    T --> A[Coding Agent / CLI / 未来工具包装]
```

### 最小写入原语与环境上下文

业务和插件作者只有四类意图：`record(event)` 提交领域或结构事件；`observe(...)` 提交运行解释；`observe_operation(...)` 成对记录开始与终态；`span()` / `event()` 生成外部 tracing 语义。未绑定 Hub 时这些门面保持安全 no-op，不创建局部私有缓冲。

门面将原先分散的 Hub、session、actor、step `ContextVar` 收束为不可变 `BoundObservability`。`RunScope` 仍只服务于账本关联骨架。这样上下文所有权被清楚分为两层：**门面运行环境** 与 **事件关联身份**，避免多份 ambient 状态互相漂移。

`RunStore` 只拥有以下职责：验证词表登记、要求 frozen dataclass、执行 `AttributePolicy`、分配连续序列、写入内存账本、生成封套、向投影注册表发布。它不再拥有 `derive_events` 缓存、`get_event` / `get_blob` 兼容读取、跟随事件 drain、洞察汇总或深拷贝隔离。未发生策略转换的 frozen payload 以零冗余复制提交；发生枚举归一、脱敏或截断时才产生替换对象。

### 唯一事件描述符与治理

`EventDescriptor` 是投影和分析代码的统一治理查询面。每个已登记事件具有 `type_name`、`plane`、`domain`、唯一 `emitter`、`durability`、`audience`、`sensitivity`、`retention`、必填字段、说明与 OTel 类型。`EVENT_DESCRIPTORS` 将既有 `JOURNAL_CATALOG` 与 `JOURNAL_CATALOG_META` 收束为供消费者读取的描述符；旧登记表在迁移期保留为 schema 兼容输入，**消费者不得再分别解释两张表**。

| 治理维度 | 决策 | 执行位置 |
|---|---|---|
| 类型登记 | 未登记或非 frozen payload fail-fast | `RunStore.append()` |
| 文本与密钥 | 统一 sanitize、截断与 verbosity 预算 | `AttributePolicy` 于提交前执行 |
| 外部可导出 | `restricted` 或 `confidential` 事件不进入 OTel / Langfuse | `may_export_externally()` 与 `OtelProjector` |
| 用户实时可见 | SSE 按事件受众过滤，并在 transport 层执行额外字段裁剪 | SSE 投影 / 帧序列化层 |
| 保留与载荷 | `required` 与 `best_effort`、`default` 与 `short` 由描述符声明 | 未来 durable store / retention worker 的单一输入 |

这使“ReasoningDelta 能否外送”“工具参数预览是否可见”“JSONL 是否必须保留”等问题不再由每个投影器写自己的 `isinstance` 分支决定。

### 投影插件、兼容输出与生命周期

`ProjectionRegistry` 是提交后的顺序发布器。投影实现 `on_event(StampedEvent)`；`flush()` 与 `close()` 是可选生命周期能力。注册表逐个隔离故障：一个 OTel exporter、SSE writer、控制台 renderer 或本地文件写入失败，只产生进程级 `structlog` 告警，不能阻断已经完成的账本提交或 Agent run。

旧 `DiagnosticStream` 和其独立 `DiagnosticEvent.seq` 被删除。为保持现有 `lca.diagnostic.v1` JSONL 和 CLI 的可读性，`DiagnosticJsonlProjection` 将已提交的 `RuntimeObserved` **只读渲染**为兼容 `DiagnosticEvent`。兼容接收器使用语义明确的 `DiagnosticSink.write()`，而非与投影同名的 `on_event()`；该投影不分配序号、不维护第二历史、不参与恢复，也不回写主账本。

`ObservabilityHub` 是唯一组合根：它装配一个 `RunStore`、一个 `ProjectionRegistry`、OTel exporter、外部 bridge，以及可选的兼容诊断 JSONL 投影。`release()` 关闭账本投影资源；`dispose()` 处理 exporter 与 bridge。`InsightEngine` 已删除，`RunInsight` 不再由订阅者自动产生；兼容调用方如显式写入该旧事件，现有视图仍可渲染，但不得用于新的分析设计。

### 插件、交互、上下文与数据传输边界

解释事件只在拥有语义的边界产生，避免“每层都记一行”的噪声。当前实现将 Hook、LLM、工具、委派传输、传感器与记忆失败接入 `observe` / `observe_operation`；后续插件应遵循相同规则。

| 边界 | 必须记录的解释 | 因果关系 |
|---|---|---|
| Plugin / Hook | `plugin.interaction`、`hook.trigger`、插件标识、目标插件、结果 | 触发事件的 `seq` 放入 `causation_refs`；交互图读取 `source → target_plugin`。 |
| Context / Memory | `context.injected`、`sensor.read`、`memory.perceive`、来源、数量、摘要 / digest、失败 | 对应 `ContextManifested` 或前置输入事件为父。 |
| LLM | `llm.request` / `llm.complete`、模型、token、TTFT / 延迟、完成原因 | 结构事实 `LlmCallStarted` / `LlmCallCompleted` 仍是恢复与成本事实。 |
| Tool / Code | `tool.execute`、`code.execution`、权限裁决、摘要、退出码、可重试性 | 关联 `ToolStarted` / `ToolInvoked` / `ToolDenied` 和 invocation id。 |
| Transport | `transport.send` / `transport.receive`、协议、callee、任务 ID、context ref 数量、延迟 | 关联 `DelegationIssued` / `DelegationCompleted` 与 delegation id。 |
| Retry / Failure | `error` / `retry`、稳定错误码、消息摘要、retryable | 错误事件的 `parent_seq` 指向最近直接原因，检查器递归生成失败链。 |

进程级 `ProcessJournal` 只作为共享实时投影，转发原始 `StampedEvent`；它不得再把 per-run `seq` 改写成 process seq。跨 run 订阅请求以 `trace_id`、`run_id` 和原始 `seq` 唯一定位；如果将来需要全局消费游标，必须引入与事件封套分离的 `ProcessEventFrame.cursor`，而非篡改事件身份。

### Coding Agent 消费接口

`TraceInspector` 直接读取 `RunStore.events` 或重放后的封套集合，不依赖控制台格式和私有缓存。它是面向工具包装层的最小领域服务，当前提供以下稳定能力。

| 接口 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `inspect_trace` | `trace_id` / `run_id`、`focus`、`depth` | `TraceReport`、事件摘要、因果链、瓶颈、交互图 | 常规理解轨迹；`focus` 支持 `all`、`error`、`latency`、`tool`、`plugin`。 |
| `explain_failure` | `trace_id` / `run_id`、深度 | 首个失败、因果祖先、同 run 窗口 | 将“为什么失败”压缩为 Agent 可读的最短证据链。 |
| `find_optimization_candidates` | 事件集合、数量上限 | LLM、工具、运行解释的按延迟排序候选 | 定位慢模型、慢工具、慢插件及 transport 瓶颈。 |
| `export_minimal_reproduction` | `trace_id` / `run_id` | 失败事件及其因果祖先的最小封套子集 | 供离线复现、差分和 issue 附件使用。 |
| `plugin_interaction_graph` | 事件集合 | Mermaid `flowchart` | 显示 `source → target_plugin` 的交互关系。 |

这些接口故意不在每个 turn 结束时自动写 `trajectory.md` 或 `bottleneck` 事件。摘要是可重新生成的视图；只有用户显式请求、CLI 或未来工具包装器调用时才计算，从而保持写路径最小且让分析算法可以独立演进。

## 已移除或收敛的机制

| 旧机制 | 问题 | 新机制 |
|---|---|---|
| `DiagnosticStream` / 独立诊断序列 | 第二条历史、第二个顺序与第二套生命周期 | `RuntimeObserved` 进入主账本；诊断 JSONL 变为兼容投影。 |
| `InsightEngine` 回写 `RunInsight` | 投影反向修改写路径，维护 parallel mini store | `TraceInspector` 从提交历史只读派生。 |
| `RunStore.derive_events` 与 predicate 缓存 | 写路径承担查询和缓存失效 | `read_from()`、`get()` 与按需检查器。 |
| `get_event` / `get_blob` 读取旁路 | 重复 API 与隐式载荷 owner | `get(seq)` 返回完整 `StampedEvent`。 |
| ContextManifest 双写开关 | 迁移开关成为长期第二路径 | 生产 `JournalSink` 无条件向当前账本追加。 |
| 多个 facade `ContextVar` | Hub、session、actor、step 容易漂移 | 一个 `BoundObservability` 环境上下文 + 一个 `RunScope` 关联上下文。 |
| 进程级重铸 `seq` | 破坏事件身份和因果引用 | 原样转发事件；全局 cursor 与事件 seq 分离。 |
| 每个投影各自安全判断 | 可见性和脱敏策略漂移 | `EventDescriptor` + `AttributePolicy` 的集中治理。 |

## 数据安全、保留与性能后果

所有字符串在账本提交边界经 `AttributePolicy` 规范化。`minimal` 删除预览；`standard` 限制预览长度；`verbose` 可保留更完整的允许内容；疑似密钥无条件脱敏。解释事件应优先保存 ID、计数、hash、协议、状态、受限摘要和内容引用，不能借 `attributes` / `output` 规避完整提示词、完整工具参数或完整响应的治理。

外部 OTel / Langfuse 投影只接收非 `restricted` 且非 `confidential` 的事件。这符合 OTel 作为互操作 tracing 层、而非秘密或 replay 内容数据库的定位。[2] Langfuse 的 trace 与 observation 层次可继续作为 agent、generation、tool、span、event 的外部视图，但不可成为账本的权威来源。[3]

当前 `RunStore` 是进程内 append-only 账本，JSONL durability 由专用投影实现。`required` / `best_effort`、受众和保留类已进入描述符，下一阶段 durable store 必须以此为唯一输入实现 backpressure、批处理、归档和清理。对于 token 流等高频事件，`best_effort` + `short` 是产品语义，不是投影器私自丢弃；未来异步批处理只能在不改变 `required` 事件提交顺序的条件下引入。

## 迁移与兼容性

本 ADR 不改变 typed 领域 payload 的名称、既有 JSONL `journal.v1` 记录基本形状或 `JournalProjector` 兼容协议。`StampedEvent.parent_seq` 以默认 `None` 增量加入，因此旧构造调用仍有效。`lca.diagnostic.v1` 文件继续由兼容投影产生，便于 `lca-ops debug trace` 和既有脚本逐步迁移；它被明确标记为视图，而非独立事实日志。

未来新增事件必须先登记 payload 类和唯一 `EventDescriptor`；未来新增后端必须实现投影，不得调用 `store.append()`。未来新增 Coding Agent 工具必须调用 `TraceInspector` 或同等只读服务，不得重建长期内存索引并作为第二真相源。

## PR 列表与落地顺序

| PR | 标题 | 范围与验收标准 | 状态 |
|---|---|---|---|
| **PR-1** | 统一事件元模型与封套因果 | 新增 `EventPlane`、`EventDescriptor`、`RuntimeKind`、`OperationOutcome`、`RuntimeObserved` 与 `parent_seq`；所有事件仍经唯一 `RunStore` 盖章。 | **已完成** |
| **PR-2** | 极简账本与投影注册表 | 重写 `RunStore` 为验证 → 策略 → 追加 → 提交后发布；新增 `ProjectionRegistry`；删除深拷贝、predicate 缓存、跟随事件回写和冗余读取 API。 | **已完成** |
| **PR-3** | 诊断流收敛与兼容 JSONL | 删除 `DiagnosticStream`；实现 `DiagnosticJsonlProjection`；`DiagnosticSink` 改用 `write()`；兼容 JSONL 的 seq 与主账本一致。 | **已完成** |
| **PR-4** | 投影安全与序列保真 | 由 `EVENT_DESCRIPTORS` 统一查询可见性、敏感性和外送许可；OTel 过滤 restricted / confidential；`ProcessJournal` 不再重铸 seq。 | **已完成** |
| **PR-5** | 运行边界埋点与单路径上下文 | Hook、LLM、工具、transport、sensor / memory 失败经 `RuntimeObserved` 解释；门面环境收束为 `BoundObservability`；删除 ContextManifest 双写。 | **已完成** |
| **PR-6** | Coding Agent 轨迹检查服务 | 实现 `TraceInspector`、失败解释、瓶颈排序、最小复现和 Mermaid 插件交互图；测试证明分析不写 `RunInsight`。 | **已完成** |
| **PR-7** | 描述符 source inversion | 将现有 `JOURNAL_CATALOG` / `JOURNAL_CATALOG_META` 的声明体进一步收敛为单一 `EventDescriptor` source，再生成兼容表，删除剩余双表定义。 | **下一阶段** |
| **PR-8** | Durable ledger、索引与流量控制 | 按 durability / retention 引入持久账本、流式 replay、独立 transport cursor、轻量索引和 backpressure；不得改变 I1–I4。 | **下一阶段** |
| **PR-9** | Agent 工具与轨迹产品化 | 将 `TraceInspector` 包装为 profile 可选工具：`inspect_trace`、`explain_failure`、`find_optimization_candidates`、`export_minimal_reproduction`；可选生成请求驱动的 `trajectory.md` 与 `diff_context`。 | **下一阶段** |
| **PR-10** | OTel GenAI 与评估投影深化 | 完成 request / response、TTFT、retry、permission、code execution 的 GenAI 语义映射，并以投影方式接入 Langfuse 评估。 | **下一阶段** |

## 验证与自动化约束

| 约束 | 自动化证据 |
|---|---|
| 账本连续序列、提交先于观察、未登记事件 fail-fast | `tests/test_journal_core.py`、`tests/test_journal_schema_fields.py` |
| 解释事件与因果父引用可供 Agent 消费 | `tests/test_journal_insight.py` 的 `TraceInspector` 失败链、交互图与最小复现用例 |
| 诊断兼容 JSONL 不再拥有独立流 | `tests/test_run_diagnostics.py` 验证主账本 seq、脱敏和 operation 终态 |
| content 与 external export 安全 | `tests/test_journal_content_policy.py`、`tests/test_journal_otel_projector.py` |
| ContextManifest 单路径与账本读取 | `tests/test_journal_reducer_apply_delta_equivalent_to_fold_events.py`、v3 / scenario 测试 |
| 实时传输不改写事件身份 | `tests/test_ops_journal_log.py`、`tests/test_live_tail.py`、`tests/test_run_live_sse.py` |
| 投影故障隔离与边界纪律 | `tests/test_observability_boundary.py`、`scripts/check_protocol_impl.py` |

本次重构范围的关键回归套件为 **177 passed**，静态检查与格式检查通过。完整仓库测试运行结果为 **1768 passed、15 skipped、16 failed**；剩余失败集中于未导入的 `OwnerAgentHandle`、冷启动 plugin context、scenario closed-set、外部 LobeHub 源目录和上游 OpenAI 兼容服务等非日志模块，未出现本 ADR 涉及的账本、投影、诊断或实时传输回归。

## 被否决的方案

| 方案 | 否决原因 |
|---|---|
| 保留 Journal 与 `DiagnosticStream` 两条并行事件流 | 两套 seq、关联、故障隔离、生命周期和查询语义必然漂移；Agent 也必须猜测应读哪一条。 |
| 将所有解释信息排除在 Journal 之外，只写 structlog | `stderr` 不具备 run 归属、可重放关联、稳定 schema 或 Coding Agent 查询能力。 |
| 让 OTel / Langfuse 成为主记录 | 它们是优秀的互操作 tracing / analysis 投影，不是 LCA 领域状态、恢复和审计的权威来源。[2] [3] |
| 每个插件自建 JSONL、logger 或 in-memory index | 破坏数据治理、seq、关联和保留策略，形成不可观察的插件旁路。 |
| 在投影器中自动写 `RunInsight` / `bottleneck` | 读路径反向写账本，造成循环、顺序歧义与第二份聚合状态；分析应按需派生。 |
| 为跨 run 实时日志重写 `seq` | 便利了单一 cursor，却破坏事件原始身份和 `parent_seq` 因果链；cursor 应属于 transport frame。 |
| 每一个运行细节都新建 typed 事实事件 | 会扩大词表且提高 replay 负担；通用 `RuntimeObserved` 已足以承载非状态性插件解释。 |

## 后果

正面后果是，运行过程从“多个 logger 与多条时间线”变为一个可读、可重放、可投影的因果账本。人类可以继续使用 console、JSONL、SSE 和 Langfuse；Coding Agent 则可直接读取结构化报告、失败路径、性能候选、最小复现和插件交互图，而无需解析控制台文本或猜测插件内部行为。

代价是，事件描述符与写入期数据治理成为更严格的架构边界；新增插件必须明确选择领域事实、结构事件还是 `RuntimeObserved`，并在需要新 payload 时完成注册。短期内 `JOURNAL_CATALOG` 与 `JOURNAL_CATALOG_META` 仍是兼容输入，因此 PR-7 必须完成 source inversion，避免它们再次成为消费者侧的双重真相。

## 参考

[1]: https://deepseek.com/harness/en/ "DeepSeek Harness：插件化 Harness、Session 事件和 Trajectory"
[2]: https://opentelemetry.io/docs/specs/semconv/gen-ai/ "OpenTelemetry GenAI Semantic Conventions"
[3]: https://langfuse.com/docs/observability/data-model "Langfuse Observability Data Model"
[4]: https://opentelemetry.io/docs/concepts/signals/traces/ "OpenTelemetry Traces"
