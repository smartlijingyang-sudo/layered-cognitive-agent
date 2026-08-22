# ADR-0065: 可恢复的证据保真运行账本

## 状态

**Accepted — 2026-08-21**

Supersedes: ADR-0064（Journal v2 evidence sidecar，已删除）

Keeps: [ADR-0037](0037-journal-as-truth.md)、[ADR-0055](0055-run-fact-store.md)、[ADR-0061](0061-plugin-manifest-resolve-boot.md)、[ADR-0063](0063-run-trace-ssot.md)

> **核心决策：一次 run 由一个可验证、可重放、带证据引用的不可变账本定义。账本记录发生的事实；证据保存经治理的原始载荷；状态、索引、摘要、成本、诊断、实时流和外部遥测全部是带版本与输入水位的只读物化视图。**

## 背景

ADR-0063 已将 Journal 确立为唯一运行事实源，并将 JSONL、SSE、OTel、Langfuse、控制台和 Agent 工具收敛为提交后投影。ADR-0064 正确识别了截断预览、双层 JSON 编码、per-run 可读性和 gateway 直接构造等问题，但其方案仍把“完整记录”简化为“保存完整字符串”，同时让 `RunFinalizer` 在关闭路径同步生产摘要、索引和成本文件。这样会混淆事实、证据和读模型，也会让可恢复性、隐私治理、投影幂等与 schema 演进缺少同一套边界。

完整性不是无差别地复制所有数据。模型可见内容、工具输入输出、附件、代码执行回执和跨代理消息需要在可访问、可保留、可验证的证据平面中保存；账本本身需要保存稳定身份、因果关系、类型化业务事实和可验证引用。任何不能通过该引用读取或验证的“完整载荷”，都不是可恢复事实；任何可由账本重建的摘要，也不得成为第二事实源。

OpenTelemetry 将 trace、span、事件、链接与上下文传播定义为跨系统关联模型，适合成为 LCA 已提交账本的互操作投影，而不是替代领域账本。[1] CloudEvents 对核心上下文与扩展属性的分离说明，稳定身份、来源、时间、类型和 schema 必须具有唯一、受治理的定义；扩展也必须声明其名称、类型、语义与允许值。[2] 对跨进程调用，W3C Trace Context 提供 `traceparent` 与 `tracestate` 的标准传播边界，并明确要求处理隐私、安全与标识符生成风险。[3]

| 决策驱动因素 | 本 ADR 的回应 |
|---|---|
| 可恢复性与审计 | 将可重放账本、不可变证据引用和完整性校验定义为同一提交协议。 |
| 数据最小化与隐私 | 以分类、访问控制、保留与脱敏策略决定内联或引用；“完整”不等于向所有投影外送。 |
| 演进安全 | 以注册的事件描述符、payload 版本和显式兼容规则取代自由形状的 `data` / `meta` 字典。 |
| 投影可靠性 | 将摘要、索引、成本和诊断定义为可重建物化视图，记录输入高水位和生成器版本。 |
| 插件化组合 | 以声明的 capability 组装 run-scoped 账本对象，消除 gateway 对 projector、tail 和进程日志实现的直接构造。 |
| 跨系统可观测性 | 内部因果身份保持 LCA 语义；OTel 与 W3C 上下文仅通过受控映射关联。 |

## 决策

### 一、账本、证据与物化视图是三个不同平面

一个 run 的**账本平面**是唯一的事实提交序列。其记录描述某一语义事件已经发生，并拥有稳定的 `run_id`、严格递增的 `run_seq`、全局 `event_id`、时间、作用域、因果关系、描述符和类型化 payload。`run_seq` 是该 run 的唯一顺序；任何进程级流、SSE cursor 或查询分页令牌都属于运输或读取协议，绝不覆盖它。

**证据平面**保存由账本引用的原始或规范化载荷，例如完整 prompt、模型响应、工具参数、工具结果、文件回执和二进制附件。证据由内容摘要、媒体类型、字节数、分类、保留策略和访问策略描述。它可存于文件系统、对象存储或受控数据库，但必须由同一 `EvidenceStore` 契约提供可验证读取。

**物化视图平面**包含 JSONL 导出、SSE、OTel、Langfuse、控制台、索引、`summary.md`、成本报告、轨迹报告和 Coding Agent 查询结果。它们只读取已提交的账本和已解析的证据；任何视图均可删除并从账本重新生成。视图的输出必须声明 `ledger_high_watermark`、`generator_id` 和 `generator_version`，使消费者能够判断它是否过期。

| 平面 | 权威对象 | 可否作为恢复输入 | 可否反向追加事实 | 典型产物 |
|---|---|---:|---:|---|
| 账本 | `JournalRecord` 的有序集合 | 是 | 否 | `journal.jsonl` 或等价 durable backend |
| 证据 | 经过完整性验证的 `EvidenceRef` | 是 | 否 | prompt、response、工具结果、附件 |
| 物化视图 | 账本的版本化只读投影 | 否 | 否 | index、摘要、OTel、SSE、成本、诊断 |

### 二、不可变约束

| 编号 | 约束 | 规定 |
|---|---|---|
| **L1** | 一次发生，一次提交 | 每个事实只经 `RunLedger.append()` 提交一次；写入路径不存在私有 JSONL、独立诊断流或投影回写。 |
| **L2** | 提交先于观察 | `required` 记录及其被引用的 required 证据完成 durable commit 后，才可通知任何投影或实时消费者。 |
| **L3** | 身份与顺序不可重铸 | `event_id` 全局唯一；`(run_id, run_seq)` 唯一且连续。投影与 transport 只能添加自身 cursor。 |
| **L4** | 描述符先于实例 | 事件类型、payload schema、分类、保留、受众、外送资格和兼容规则只在 `EventDescriptor` 注册表定义。未登记类型或不匹配版本 fail-fast。 |
| **L5** | 证据引用可验证 | 任何指向完整载荷的引用都携带算法、摘要、字节数、媒体类型、分类和保留信息；读取时必须验证完整性。 |
| **L6** | 视图永不成为事实 | 投影、摘要、索引、成本、诊断和外部 exporter 不得调用 `append()`；它们的状态仅是可重建缓存。 |
| **L7** | 终态封存 | 终态 run 事件提交后，账本以终态事件和高水位封存；随后只能执行不改变历史的物化、校验、归档或受治理的删除。 |
| **L8** | 策略先于持久化和外送 | 分类、脱敏、访问、保留和外部导出许可在提交边界确定，并由证据读取与每个 exporter 共同强制。 |
| **L9** | 组合根唯一 | 运行期账本、证据、投影和实时输出只由已解析的 capability 图组装；gateway 不得直接构造具体实现。 |

### 三、Journal v2 信封与 payload 契约

`StampedEvent` 演进为逻辑上的 `JournalRecord`。持久化格式可以是 JSONL、数据库行或对象存储对象，但所有格式必须无损表达下列契约。`data` 是注册的 frozen dataclass payload 的规范化序列化，不是允许插件随意扩张的 `dict`；可扩展字段必须通过命名空间化的 descriptor schema 注册。

```json
{
  "schema": "lca.journal/2",
  "event_id": "evt_01J...",
  "run_id": "run_01J...",
  "run_seq": 42,
  "occurred_at": "2026-08-21T04:22:00.123Z",
  "committed_at": "2026-08-21T04:22:00.129Z",
  "scope": {
    "trace_id": "trace_...",
    "parent_run_id": null,
    "delegation_id": null,
    "agent_role": "researcher",
    "turn": 3,
    "step": 2
  },
  "causation": {
    "parent_event_id": "evt_01J...",
    "links": []
  },
  "descriptor": {
    "type": "lca.llm.completed",
    "version": 2
  },
  "data": {
    "model": "example-model",
    "outcome": "ok",
    "prompt_tokens": 7388,
    "completion_tokens": 79,
    "prompt_ref": "sha256:...",
    "response_ref": "sha256:..."
  },
  "evidence": [
    {
      "ref": "sha256:...",
      "media_type": "text/plain; charset=utf-8",
      "byte_length": 30234,
      "classification": "restricted",
      "retention_class": "run-default"
    }
  ]
}
```

`occurred_at` 表示事件源认定的发生时间，`committed_at` 表示账本接受该记录的时间。二者不可互换；其差值可揭示离线缓冲、时钟漂移或延迟采集。单进程实现可以让二者相等，但不得依赖这一偶然性。`parent_event_id` 表示直接因果，`links` 表示非树形关联，例如重试、并行委派、外部 trace 或跨 run 证据。这样可避免以 ambient context 或重写序列号伪造因果拓扑。

当前 `RunScope` 的 `trace_id`、`run_id`、`parent_run_id`、`delegation_id`、`agent_role` 和 `step` 保留为 LCA 的业务关联骨架。`turn` 在相应生命周期语义已登记时进入 scope。现有 `AgentRunStarted`、`TeamRunStarted`、`AgentRunFinished` 和 `TeamRunFinished` 保持 run 生命周期语义；v2 不再另造含义重复的 `RunOpened` / `RunClosed` 词表。任何新增 turn、step 或控制事件必须先完成 descriptor 登记与闭集评审。

### 四、EvidenceStore：完整载荷的受治理引用

`*_preview`、`result_preview` 和以 JSON 字符串承载结构化结果都不再作为账本事实字段。兼容性投影可以在必要时生成受策略限制的 preview，但 preview 仅是视图，不能用于恢复、比较、审计或前端二次解析。结构化工具结果、文件清单和 UI 所需状态必须使用已登记的类型化字段或 `EvidenceRef`，而非自由形状的 `plugin_state` 逃逸口。

Evidence 写入采用“准备、验证、引用、提交”的协议。`EvidenceStore.prepare()` 先按分类策略执行规范化、脱敏和加密，写入暂存对象并生成不可变 receipt；receipt 至少包含摘要算法、摘要、媒体类型、字节数、分类、保留类和内部定位符。`RunLedger.append()` 只接受已经验证的 receipt，并将其引用与账本记录一起提交。若跨存储介质无法提供分布式原子事务，读取端必须把缺失或摘要不匹配视为明确的完整性状态，不能静默降级为“无内容”；后台回收器仅可清理没有账本引用的暂存对象，且必须幂等。

内联还是引用由 `EvidencePolicy` 按事件 descriptor、分类、媒体类型、访问受众和容量预算决定，而不是由一个全局“超过 64 KB”阈值决定。小型机密内容同样应引用而非内联；大型但公开的流式增量可以按 descriptor 标为 `best_effort`。引用的摘要用于完整性验证，不授予读取权限；证据解析必须再次执行租户、角色、分类、保留和导出检查。

| 载荷类别 | 账本保存内容 | 证据保存内容 | 默认投影规则 |
|---|---|---|---|
| LLM 请求与响应 | 模型、token、结果、prompt/response ref、prompt 版本摘要 | 经策略处理的完整文本或结构化消息 | restricted 内容不得进入 SSE、OTel 或 Langfuse |
| 工具调用与结果 | 工具名、invocation、幂等键、结果状态、evidence ref | 规范化参数、结构化结果、stdout/stderr、文件回执 | 仅经 descriptor 允许的摘要可外送 |
| 附件与工件 | 附件 ID、媒体类型、摘要、来源、evidence ref | 原始二进制或受控副本 | 依据访问策略返回受签名读取能力或拒绝 |
| 运行解释 | 稳定 operation、结果、因果引用、受控错误码 | 可选的受限诊断片段 | 默认仅 operator；不得携带未治理的完整敏感载荷 |

### 五、写入、恢复与终态封存

`RunLedger` 是每个 run 的唯一提交仲裁者。它在单一临界区内完成 descriptor 校验、调用方 capability 校验、scope 与因果盖章、分类与策略处理、证据 receipt 验证、`run_seq` 的 expected-version 比较、durable append 以及提交标记。只有在成功提交之后，`ProjectionRegistry` 才能收到记录。`required` 事件的 durable backend 失败必须使调用失败或触发已登记的恢复策略；不得以已向 SSE 发送或已写内存为成功。

恢复从账本而不是摘要或索引开始：读取全部已提交记录，验证 `run_seq` 连续性、descriptor 版本、因果引用和所需 evidence receipt，然后由 reducer 纯函数重建状态。外部副作用恢复仍以 `invocation_id` 与 `idempotency_key` 判断，不得因重放再次执行。每个 terminal event 都生成可验证的 `RunManifest` 物化视图，其中含 `run_id`、终态 `event_id`、账本高水位、账本摘要、materializer 版本与证据完整性状态；它是导航和校验入口，不是新的事实 owner。

`gateway/runs/terminalizer.py:RunTerminalizer` 是执行入口与恢复入口共享的终态封存 module。它以 `terminalize(session, workspace, success)` 统一工件 closure、运行资源关闭、Journal 派生状态、registry 清理、manifest 物化与 exporter flush 的顺序。该 module 只在终态事件后生成物化与完整性检查；它不得把 manifest、registry 状态或 exporter 结果提升为账本事实。

`SourceLocation` 不是账本写入热路径的隐式 `inspect.stack()` 副作用。需要源码定位时，受控 instrumentation 可以显式记录构建修订、模块、符号和可选行号，并由 descriptor 分类为诊断数据；调用栈采集仅能作为按需诊断物化，不得对每条业务记录默认执行或泄露绝对路径。

### 六、物化视图、成本与 Coding Agent 查询

每个 projector 从 `run_seq` 水位自拉已提交记录，并以 `(run_id, run_seq, event_id)` 幂等消费。它保存自己的 checkpoint、输入高水位、生成器版本和失败状态；失败、重试、重建或版本升级都不影响账本。`LiveTail` 是低延迟投影，必须在提交后发布；断线恢复使用账本水位而非 process-global 序号。

`summary.md`、trajectory、decision tree、causal chain、索引和 Mermaid 图统一归入 `materializations/<generator-id>/<generator-version>/`。它们可以按显式 CLI、UI 请求或异步作业生成，但不得被 run 关闭同步地视为完成前提。索引只加速查找，必须能从账本重建；索引损坏不会改变 run 的恢复结果。

成本是使用量事件的可再计算视图。每个 `LlmCallCompleted` 记录必须关联不可变 `pricing_ref` 或明确的“未定价”状态；`CostProjector` 根据该版本化价目和账本高水位生成报告。任何“当前默认价格”不得追溯改写历史成本。Coding Agent 工具只依赖 `TraceInspector`、账本读取和已授权证据解析，提供检查、失败解释、优化候选、插件交互图、最小复现和 run diff；这些能力均为 read-only，不拥有 `journal.write` 旁路。

### 七、目录、定位与组合根

文件系统是默认 backend，不是架构边界。默认 `RunLocator` 使用不可猜测的 `run_id` 作为目录名，并将路径视为实现细节；本地时间字符串、部分哈希和人类命名不承担身份语义。一个符合本 ADR 的文件后端可以呈现为：

```text
traces/
├── latest.json                         # 原子更新的便利指针；非事实来源
└── runs/
    └── <run_id>/
        ├── journal.jsonl               # JournalRecord 的 durable 序列化
        ├── manifest.json               # terminal materialization + 完整性状态
        ├── evidence/                   # 内容寻址对象；不得用业务文件名泄露语义
        ├── indexes/<index-version>/    # 可丢弃、可重建
        └── materializations/<id>/<v>/  # 摘要、报告、图；带输入高水位
```

`latest.json` 必须通过临时文件加原子替换更新，并包含目标 `run_id` 与校验值；它仅提供人机导航，不能作为重放、恢复或审计输入。Windows、Linux 和 macOS 的差异由 `RunLocator` 实现封装，不向调用方暴露双路径分支。

run-scoped 资源由一个 `run_ledger_factory` capability 创建为 `RunLedgerHandle`，该 handle 显式拥有 ledger、evidence resolver、投影注册表和关闭顺序。`evidence_store`、`run_locator`、`projection_registry` 与 `materialization_store` 是独立声明的 capability；它们通过 manifest 的 `provides` / `requires` 组成 DAG。`gateway/runs/` 只能请求 `run_ledger_factory` 和面向命令的服务，不得直接 `new` `JsonlJournalProjector`、`LiveTail`、`ProcessJournal` 或具体文件布局对象。该设计遵循 ADR-0061 的 Resolve-before-Boot、声明依赖和逆拓扑释放规则。

### 八、外部遥测与跨边界关联

OTel、Langfuse 和控制台 exporter 只投影已提交的 `JournalRecord`。它们以 LCA 的 `run_id`、`event_id` 与因果边构造 spans、events 和 links；外部 span 并不反向定义业务父子关系。由于 OpenTelemetry 的 span links 可以表达非树形关联，跨 run、重试、并行委派和外部调用不应被强制塞进单一父 span。[1]

A2A、MCP、HTTP 或队列边界可以携带 W3C `traceparent` / `tracestate`。入站上下文属于不可信数据，必须经过格式、长度、来源和隐私策略校验；通过校验后仅作为 `causation.links` 中的外部关联或 exporter 映射。它不得覆盖 LCA 的 `trace_id`、`run_id`、`run_seq` 或授权身份。[3] 所有 `restricted` / `confidential` payload 与 evidence 都必须在 exporter 前被拒绝或生成经批准的最小摘要。

## 后果

| 维度 | 正面后果 | 代价与约束 |
|---|---|---|
| 事实与恢复 | 可从连续账本和可验证证据重建 run；摘要和索引损坏不影响恢复。 | 写入协议与 evidence receipt 比单纯 JSONL append 更严格。 |
| 安全与合规 | 完整载荷按分类、访问和保留治理；外部投影不再意外成为敏感内容副本。 | 每个新事件与证据类型都需要明确 descriptor 和 policy。 |
| 性能与可靠性 | 低延迟投影与 durable 事实解耦；失败投影可按水位追赶。 | required 事件的持久化路径需要容量、重试和故障演练。 |
| 可演进性 | schema、价目、物化器和索引版本独立演进，可比较历史结果。 | 旧 v1 record 必须经显式迁移或兼容 reader 读取，不能与 v2 隐式混读。 |
| 插件架构 | run-scoped 依赖从组合根显式获得，gateway 不再拥有隐藏的具体构造。 | 需要为新 capability 提供 manifest、测试和生命周期声明。 |

## 验证约束

| 约束 | 必须证明的自动化证据 |
|---|---|
| L1–L3 | 并发 append 下 `(run_id, run_seq)` 连续且唯一；投影、SSE 与 process stream 不改写身份。 |
| L2 与 L5 | required evidence 缺失、摘要不匹配或持久化失败时不发布记录；无引用暂存对象可被安全回收。 |
| L4 与 L8 | 未登记 payload、未知扩展、分类绕过、敏感 evidence 外送和自由形状 JSON 都被拒绝。 |
| L6 | 删除任意索引、摘要、成本或图后，能从相同账本得到等价的版本化视图；任何 projector 调用 `append()` 都被架构测试拒绝。 |
| L7 | terminal event 后禁止追加领域事实；恢复使用 terminal event、账本高水位与证据验证，而不依赖 manifest 或 `latest`。 |
| L9 | profile resolve 能给出 ledger capability 图；gateway 路径不存在具体 projector、tail、process journal 或 layout 的直接实例化。 |
| 外部映射 | OTel/Langfuse 只接收获准的数据；W3C 入站上下文不能覆盖 LCA 账本身份，异步关联映射为 links。 |
| 成本可重复 | 相同账本与 `pricing_ref` 生成相同成本；价格表升级不改变历史物化结果。 |

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 将所有完整内容直接内联到 JSONL | 无法区分访问、保留、二进制、加密和外送边界；会把账本变成无治理的数据湖。 |
| 维持 preview 与 `plugin_state` 双通道 | 语义与类型继续漂移，恢复和 UI 都必须猜测哪个字段可信。 |
| 将 `summary.md`、索引和成本作为关闭时的同步事实 | 投影失败会阻塞 run，且派生数据会形成第二事实 owner。 |
| 让 OTel、Langfuse 或外部 trace 成为账本 | 它们服务于互操作与观测，不能承担 LCA 的领域恢复、证据治理和业务因果语义。[1] [3] |
| 为每类对象新增独立 factory seam | 会以构造细节替代领域 capability，扩张依赖图；一个 run-scoped ledger handle 已足以表达对象生命周期。 |
| 依赖 `inspect.stack()` 默认记录完整代码 trace | 增加热路径开销并泄露部署路径，且不能提供稳定的构建级可重现定位。 |

## 实施序列(2026-08-21 plan-mode 产出)

10 个 PR,每 PR 独立可合。前 3 PR 是契约地基,后 7 PR 是行为实现。

| PR | 标题 | 跨层 | blast radius | 验证锚点 |
|---|---|---|---|---|
| **PR-1** | ADR-0065 文档(本章节)| docs | 无 | git grep |
| **PR-2** | EvidenceStore 契约 + 默认 fs 实现 | contracts + layer0 + plugins | contracts 全局 | L5 / L8 |
| **PR-3** | `JournalRecord` v2 envelope + 删 `*_preview` + `plugin_state` + descriptor schema versioning + v1→v2 migration | contracts + layer0 + layer1 | layer1 全部 emit 点 | L1 / L3 / L4 / L8 |
| **PR-4** | `RunLedger` 重写:单一临界区 + expected-version + L7 终态封存 + filesystem backend | layer0 + plugins | layer0 journal | L1 / L2 / L7 |
| **PR-5** | 6 个新 seam + `run_ledger_factory` + gateway `new` 清零 + RunLocator fs | contracts + layer0 + gateway + plugins | gateway/runs/ + seam_definitions | L9 |
| **PR-6** | RunManifest + `materializations/<id>/<v>/` + `latest.json` 原子 rename + CostProjector with `pricing_ref` | contracts + layer0 + plugins + gateway | gateway/finalize + cli/cost | L6 / 决策第六节 |
| **PR-7** | OTel GenAI 语义映射完成 + W3C trace context 不可信入站校验 + `causation.links` 映射 | contracts + layer0 + plugins + gateway | exporters + SSE 入站 | L8 / 决策第八节 |
| **PR-8** | Coding Agent Tools bundle(7 工具,只读,无 `journal.write` 旁路)| contracts + layer0 + plugins + bundles | bundle / profile | L6 / L9 / 决策第六节 |
| **PR-9** | Viewer + CLI 子命令(`lca-ops logs --replay` / `cost` / `diff-runs` / `graph` / `explain` / `minimal-repro` / `diagnose`) + ErrorCode 字典(10 大类 ~30 稳定码)| contracts + layer0 + gateway + cli | lca-ops + lobehub UI | 决策第六节 |
| **PR-10** | 全量验证 + 8 篇 doc(`docs/observability/`)+ 7 个 check 脚本 + v1→v2 migration 测试 + lobehub patch 适配 + 收尾 | docs + scripts + tests + deploy | 全部 | 0065 验证约束表全部 7 条 |

### 故意丢弃(本 ADR 显式否决)

| 否决项 | 否决依据 |
|---|---|
| `RunOpened` / `RunClosed` 新词表 | §三:"v2 不再另造含义重复的 RunOpened/RunClosed 词表",保留 `AgentRunStarted/Finished` |
| `TurnOpened` / `TurnClosed` / `StepOpened` 新结构事件 | §三:"任何新增 turn、step 或控制事件必须先完成 descriptor 登记与闭集评审" |
| `EventMeta` 自动 `inspect.stack()` 热路径副作用 | §五:"`SourceLocation` 不是账本写入热路径的隐式副作用";按需受控 instrumentation |
| `RunFinalizer` 同步写 summary/index/cost | §六:"不得被 run 关闭同步地视为完成前提" |
| `result_preview` / `*_preview` / `plugin_state` 字典逃逸口 | §四:"不再作为账本事实字段" |
| Lobehub `lcaJournal.ts` 的 `JSON.parse(result_preview)` | §四:配套 lobehub patch 改走 typed 字段 |
| `traces/latest` symlink(双 OS 行为差异外露) | §七:"通过临时文件加原子替换更新" |

### 不在本 ADR 实施序列范围(明确承诺,后续 ADR / PR)

| 章节 | 触发条件 |
|---|---|
| `journal.write` capability(收紧任意 plugin 可 emit) | 单独 ADR v3 引入 |
| 远程 EvidenceStore / S3 backend | 单独 PR;fs 默认已足够 |
| OTel GenAI 评估 scorer / Langfuse scorer hooks | 单独 PR;评估指标通道成熟时 |
| 生产监控 / 健康检查 / 告警 / 触发器 | 单独 PR;metrics 通道设计完成后 |
| 高吞吐采样 / token 流超阈值批处理 | 单独 PR;`best_effort` + 流式批处理 |
| Multi-run 关联视图(跨 `trace_id` UI) | 单独 PR;`causation.links` 已就位但 UI 未动 |
| 第三方 trace 集成(Jaeger / Tempo) | 单独 PR;OTel 已支持,policy 待配 |

### 跨 PR 依赖图

```
PR-1 (ADR doc,本章节)
   │
PR-2 (EvidenceStore 契约)
   │
PR-3 (JournalRecord v2 + 删 preview + descriptor version)
   │
PR-4 (RunLedger + L7 seal)
   │
PR-5 (6 seam + run_ledger_factory + gateway new 清零)
   │
   ├──> PR-6 (manifest + materializations + cost)
   │
   ├──> PR-7 (OTel strict + W3C 入站校验)
   │
   └──> PR-8 (Coding Agent Tools bundle)
            │
            └──> PR-9 (CLI + diagnose + ErrorCode 字典)
                     │
                     └──> PR-10 (全量验证 + 8 篇 doc + 7 个 check + lobehub patch)
```

PR-6 / PR-7 / PR-8 可并行;PR-9 等 PR-8;PR-10 收尾。

### 详细 plan

完整 plan 文件(含每 PR 改动文件清单、关键 API 签名、测试套件、check 脚本、验证锚点、风险与缓解):

`/home/lichao/.grok/sessions/%2Fhome%2Flichao%2Flayered-cognitive-agent/01a02296-ced1-7f90-acbe-45d421255c9f/plan.md`(665 行,2026-08-21 产出)

## 参考

[1]: https://opentelemetry.io/docs/concepts/signals/traces/ "OpenTelemetry: Traces"
[2]: https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md "CloudEvents Specification"
[3]: https://www.w3.org/TR/trace-context/ "W3C Trace Context"
