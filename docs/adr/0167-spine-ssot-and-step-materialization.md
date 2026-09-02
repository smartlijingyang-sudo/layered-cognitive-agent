# ADR-0167: Spine 唯一耐久真值、Step 物化视图与 Model-Visible 轨迹组织

- 状态: Accepted
- 日期: 2026-09-02
- 作者: coding-agent
- 取代 / 收束: ADR-0165（正文曾缺失，见下方 stub）的 SSOT 意图；ADR-0164 的 bridge 双写路径；ADR-0166 中「StepLifecycleStore 为耐久唯一写者」的所有权表述
- 继承且不重开: ADR-0063 I1–I7；ADR-0165-execution-point-enforcement D12 / EXECUTION_POINTS；ADR-0166 D1–D7 词汇与 S1–S6 硬化；ADR-0122 debug CLI 产品位
- 对照: DeepSeek Harness `docs/architecture.md` §Session log / §Turn flow（Model-visible means logged；`request/header`；`deriveMessages()`）

## 一句话

**`events.jsonl`（EventSpine）是唯一 append-only 耐久真值。** Step 树是可重建的物化视图：唯一写入 API（`StepCoordinator`）同时打 spine EP + 更新内存累加器，finalize 写出 `journal.json`（`lca.journal/3.1`），且 **live 物化 ≡ events 重放**。轨迹对人清晰的前提是：**模型所见一切皆有记录、按 step 可打开**——对齐 DSH 的 `request/header` + surface 注入，而不是把整段 prompt 塞进 `objective` 字符串。

## 背景

### 已批准的合题（计划评审）

用户确认第一性原理：

> Spine 唯一耐久真值 + Step 树是可重建物化视图（内存累加器允许，但必须 replay 等价）。

并追加评审要求：

1. **日志格式要像 DSH trajectory 一样清晰**（按 turn/step 可读，而不是 phase 噪音 + token 碎片）；
2. **模型所见一切都要有记录**（含 system prompt、skill、tool schema、context injection 等），并说明如何组织到日志文件。

### 现状痛点（样本 `run_bb1b9570ef94`）

| 问题 | 表现 |
|---|---|
| Step 边界漂移 | `total_steps=8`（phase-as-step）；应为 steps=3 / segments=5 / phases=8 |
| 叙事不可读 | `reasoning_delta` 逐 token 展开；`context_before.objective` 塞入截断 prompt |
| Model-visible 空洞 | `ContextManifested` 多只有 `digest` + `item_kinds`，`item_refs=()`，`persist_full_prompt=False`；skill 只见 kind 名 |
| 双写垃圾 | `step_emitter` 同时 `facade.record` + `step_lifecycle`；工具 decision/invocation 双层 EP |
| SSOT 打架 | 0164 说 journal 主存储；0165-execution-point-enforcement 说 events 主真值；deriver `step_tree` 仍是 stub |

### DSH 为何清晰（可直接抄的组织原则）

DSH 不是「多写几个文件就清楚」，而是：

1. **一条 session log**，消息历史用 `deriveMessages()` **重推导**，禁止平行 `messages[]` 真相；
2. **Model-visible means logged**：进模型请求的任何输入必须能从 log 重建，运行时不变量断言；
3. **`request/header`**（`EpochHeader`）显式承载本步（或本 series）的 **system prompt + tool schemas**；变更才再写 header；
4. **注入（skill / AGENTS.md / 通知）** 进 surface `user/message`（带来源），不是偷偷拼进黑盒字符串；
5. **Trajectory UI 只是投影**：按 Turn 粗线、Step 标记平铺账本 + inspector；不改写 log。

## 决策

### D1. 双平面所有权（合题）

| 平面 | 工件 | 角色 |
|---|---|---|
| **执行真值** | `traces/runs/<run_id>/events.jsonl` | 唯一 append-only SSOT；EventSpine 写入；run-local monotonic `sequence` |
| **认知物化视图** | `journal.json`（`lca.journal/3.1`） | Step / segment / phase 故事；由累加器 finalize 或 `replay(events)` 重建 |
| **人读轨迹** | `journal.narrative.md` | deriver；合并 reasoning；**禁止**逐 token span 列表 |
| **模型可见正文** | `model_visible/step_<NN>/` + `evidence/` | 完整 prompt / tools / manifest / skills；journal 只持 **digest + rel path** |

不变量：

- **I-MV1（Model-visible ≡ logged）**：每一次真实 LLM 请求，必须存在可解析的 `RequestHeader` 记录（spine EP + model_visible 文件），使得离线可重建「当时发给模型的 system / tools / messages」。
- **I-MV2（No parallel messages SSOT）**：禁止另存一份不可从 events/journal 推导的权威 `messages[]`。
- **I-MV3（Replay ≡ finalize）**：同一 `events.jsonl` → `replay()` 得到的 `JournalDocument` 与 live finalize 在 totals 与关键 refs 上等价（契约测试）。
- **I-MV4（投影不回写）**：narrative / SSE / OTel / UI 不得 append events 或改 journal 真值语义。

### D2. 唯一写入 API

```text
Agent loop / phase driver
  └── StepCoordinator   # 唯一允许 open/close step|segment|phase
        ├── EventSpine.append(...)
        └── StepTreeAccumulator (原 StepLifecycleStore 演进)

Brain / Body / Perceive
  └── StepWriter only: record_thinking / record_tool_* / append_delta / record_reflect
      / record_request_header / record_context_manifest
```

- **删除** `lca/runtime/step_emitter.py`（存在性否定，非改职责）。
- cognition **禁止** `step_open` / `open_step`。
- 业务侧 **停止** 对 step 内部 LLM/Tool/Delta 的 `facade.record` 双写；SSE 走 progress / deriver（ADR-0157）。

切步规则继承 ADR-0166 D4（perceive 不开 step；一步 = 一次 LLM + 其工具）。

### D3. Run 目录布局（清晰轨迹的文件组织）

取代过时的「仅 `journal.jsonl`」叙述（见 `docs/observability/run-layout.md` 同步更新）：

```text
traces/runs/<run_id>/
  events.jsonl                 # SSOT：执行点账本（短 payload + ref）
  journal.json                 # 物化视图：lca.journal/3.1 step 故事
  journal.narrative.md         # 人读轨迹（Turn/Step 表 + 因果链 + 摘要）
  manifest.json                # 封印 / 高水位
  profile_snapshot.json        # boot 组合快照
  evidence/                    # 内容寻址大对象（sha256-…）
  model_visible/
    step_001/
      request-header.json      # 元数据：digests、路径、model、token 预算
      system-prompt.md         # 本步 system（完整，可脱敏策略）
      tool-schemas.json        # 本步工具 schema 快照
      context-manifest.json    # ContextManifest items（含 skill_catalog 全文或 evidence ref）
      messages.json            # 实际送入 LLM 的 messages[]（可重建断言用）
    step_002/
      ...
  # 可选遗留
  journal.raw.jsonl            # 旧 stream 兼容；非新 run 主路径
```

**什么进哪个文件（强制分工）：**

| 内容 | 落点 | 不要 |
|---|---|---|
| EP 生命周期、耗时、outcome、invocation_id | `events.jsonl` | 把整段 prompt 打进每条 EP |
| step/segment/phase、decision、合并后 reasoning、tool 摘要 | `journal.json` | 把 skill 全文塞进 `objective` |
| 完整 system / tools / manifest / messages | `model_visible/step_N/`（大块可改存 `evidence/` + ref） | 只留 digest 却声称可审计 |
| 给人看的故事线 | `journal.narrative.md` | 展开 `reasoning_delta` 碎片 |
| 工具 stdout 全文 | `evidence/` + journal 头摘要 | 无上限塞进 narrative |

**叙事默认形态（对齐 DSH Trajectory 信息架构）：**

```markdown
# Trajectory — <objective 短标题>
steps=3 segments=5 phases=8  duration=…  outcome=…

| step | think | tools | tokens | ms | outcome |
| 1 | … | bash, read | p/c | … | ok |

## Step 1
### Model saw
- system: model_visible/step_001/system-prompt.md
- tools:  model_visible/step_001/tool-schemas.json (N tools)
- context: skill_catalog, workspace_instructions, memory… (digest=…)
### Thought
<merged reasoning>
### Did
- tool X(args_summary) → ok / err
### Result
<reflect summary>
```

### D4. RequestHeader —— LCA 版 `request/header`

每个 **think segment**（即将发起的模型请求）必须经 Coordinator 记录：

```text
RequestHeader
  step_id
  reason: "initial" | "next_step" | "series" | "change"
  model
  system_digest / system_path
  tools_digest / tools_path
  messages_digest / messages_path
  manifest_digest / manifest_path
  token_estimate?
```

- spine EP 建议名：`llm.request.header`（start 侧）与既有 LLM complete EP 配对。
- **skill**：作为 `context-manifest.json` 中 `kind=skill_catalog`（及若注入正文则为独立 instruction item）完整可还原；禁止「只在 narrative 写感知到 skill_catalog」。
- **workspace_instructions / memory / inbox**：同属 manifest items，全文或 evidence ref。
- 变更检测：system/tools 未变时可复用上一 header 的路径并在 header 标 `inherited_from=step_K`（对齐 DSH header 继承），但 **messages + manifest 每步仍落盘**（本步所见不同）。

运行时断言（debug / oii profile 默认开，standard 可采样）：

`assert_model_visible(reconstruct(header) == actual_llm_request)`.

### D5. journal.json 3.1 中的引用形状

在 ADR-0166 的 `JournalStep` 上增量（不把正文打进树）：

```text
JournalStep
  context_before:
    objective_short          # 用户目标短标题，不是整段 prompt
    manifest_digest
    manifest_path            # model_visible/step_N/context-manifest.json
    …
  thinking:
    request_header: RequestHeader  # 或等价字段
    reasoning                  # coalesced
    decision / tokens / …
  tool_calls[] / tool_results[]
  segments[] / …
```

旧把截断 prompt 塞进 `objective` 的写法 **废弃**。

### D6. 插件职责（spine 为主）

| Plugin / 模块 | 职责 |
|---|---|
| `spine.core` + sinks | EventSpine 装配；run-bound `events.jsonl` |
| `StepCoordinator`（runtime + contracts Protocol） | 唯一写入口 |
| `spine.deriver.step_tree` | **不再 stub**：订阅/协同 flush → `journal.json`；提供 `replay` |
| `spine.deriver.narrative` | 轨迹 markdown（D3 形态） |
| `spine.deriver.live_tail` / graph / anomaly | 只读投影 |
| model_visible writer | Coordinator 内或专用 L0 helper；大对象走 evidence |

### D7. 删除与禁止清单

| 删除 / 禁止 | 原因 |
|---|---|
| `lca/runtime/step_emitter.py` | bridge 双写 + 错误切步主人 |
| cognition 调用 `open_step` | 违背 driver 切步 |
| 无 RequestHeader 的生产 LLM 调用（新 run） | 违反 I-MV1 |
| narrative 默认展开 per-token delta | 轨迹不可读 |
| 平行权威 `messages[]` 黑盒缓存 | 违反 I-MV2 |

### D9. 多种观测视图插件化（不锁死单一形态）

DSH 的「`ENTRY → AGENT → STEP → LLM/TOOL`」是其中一种**投影**，不是唯一形态。LCA spine `EventRecord` 已带 `span_id / parent_span_id / sequence / epoch / prev_event_hash / step_id / run_id`，足以支持多视图并存；由 **profile** + **bundle** 选装。

| 视图 | 用途 | Plugin / 形态 | 默认 |
|---|---|---|---|
| 平坦账本 | writer / stream / 默认落地 | `spine.sink.file` → `events.jsonl` | ✓ |
| Step 故事树 | Agent 自解释 / narrative | `spine.deriver.step_tree` → `journal.json` + `narrative.md` | ✓ |
| OTel 风格 trace | 跨服务审计 / Langfuse | `spine.deriver.otel_trace`（新）→ OTLP/HTTP | oii-debug |
| Waterfall（DSH 风格 trajectory） | 本地 step / token / 耗时可视化 | `spine.deriver.waterfall`（新）→ `journal.trajectory.html` | oii-debug |
| Mermaid 交互图 | plugin 协作关系 | `spine.deriver.graph` | oii-debug |
| LiveTail SSE | 实时传输 | `spine.deriver.live_tail` | ✓ |
| Anomaly 报告 | 不变量违例 | `spine.deriver.anomaly` | ✓ |

`spine.deriver.otel_trace` 最小职责：

- 按 `parent_span_id` 构树；映射 GenAI `SpanKind`：`ENTRY=INTERNAL`、`AGENT/STEP=INTERNAL`、`LLM=CLIENT`、`TOOL=INTERNAL`；
- LLM 重试各自独立 span；tool 用 `invocation_id` 关联 start / result；
- 子 agent → 独立 trace，attribute `parent_session_id / delegation_id`；
- 不持有全局 `TracerProvider`（不抢 DSH/进程级 OTel）；通过既有 OTLP/HTTP exporter 配置。

`spine.deriver.waterfall` 最小职责：

- 按 `run_id` 折叠 `events.jsonl`，产出 `journal.trajectory.html`（静态、host 离线可打开）；
- 时间轴 + 状态色 + 折叠展开；think/act 切片；每个 think 段链接到 `model_visible/step_N/`；
- 不绑 LobeHub / WebServer；CLI 仅 `lca-ops journal trajectory <run_id>`。

不变量：

- **I-VIEW1**（视图只投影）：deriver **不得** append events / 改 journal 真值；故障由 spine FD-2 隔离。
- **I-VIEW2**（DSH 风格不绑内核）：新增 deriver 仅 plugin/bundle 加一行，不动 SSOT。
- **I-VIEW3**（trace/span 关联稳定）：重试独立 span、tool start/result 通过 `invocation_id` 关联；错误的 `*_end` 必带 `outcome ≠ success` 与 `failure_envelope`。

### D10. 零 token 确定性回放：`ReplayCursor` + `StepContextAt`

**目标**：不调真模型、不跑真工具，重建「当时模型看到了什么 + 当时采取了什么动作」。原料来自 spine + `journal.json` + `model_visible/step_NN/` + `evidence/`（ADR-0167 D3/D4 已铺设）。

#### 10.1 contracts（`lca/contracts/observability/replay.py`）

```text
StepContextAt
  step_index / step_id
  request_header            # RequestHeader 字段
  messages: tuple[Message, ...]    # 真实送入 LLM 的 messages
  tool_schemas: tuple[ToolSchema, ...]
  context_manifest: ContextManifest
  actions: tuple[ActionRecord, ...]  # 工具调用 + 工具结果（事实 record）
  source: Literal["live", "replayed"]
  inferred: bool                       # True 表示由 journal/events 推导
  digest_verified: bool                # request-header digest 与 msgs/tools/manifest 一致

ReplayCursor(Protocol)
  at(*, run_id, step_index) -> StepContextAt
  messages(step_index) -> tuple[Message, ...]
  actions(step_index) -> tuple[ActionRecord, ...]
  with_override(step_index, tool_args_overrides=...) -> StepContextAt   # diff only
  fork_diff(other_run_id, at=step_index) -> CursorDiff
```

#### 10.2 算法（零 LLM / 零 tool）

```text
ReplayCursor.at(run_id, K):
  doc = load_journal(run_id)                       # or replay(events.jsonl)
  step_K = doc.steps[K-1]
  header = read(model_visible/step_K/request-header.json)
  msgs    = read(model_visible/step_K/messages.json)       # 优先：ground truth
              ↓ if missing
            build_inferred_messages(step_K)                # 标 inferred=True
  tools   = read(model_visible/step_K/tool-schemas.json)
  manifest= read(model_visible/step_K/context-manifest.json)
  actions = step_K.tool_calls[], step_K.tool_results[]     # 已是事实记录
  digest_verified = sha256(msgs) == header.messages_digest
                                and sha256(tools) == header.tools_digest
                                and sha256(manifest) == header.manifest_digest
  return StepContextAt(..., source="replayed",
                       inferred=(msgs is None),
                       digest_verified=...)
```

#### 10.3 零 token 含义

- **不调 LLM**：无 completion、无 reasoning_delta 重建。
- **不跑 tool**：用 `tool_results` 的 record + `evidence/` 替代实跑；`with_override(...)` **只算 diff**，绝不私自执行。
- 唯一代价：从 `events.jsonl` + `model_visible/` 读文件 → O(每步文件大小)，磁盘 I/O + JSON 解析。

#### 10.4 性能

- 默认 cursor 只填 summary（与 `journal steps` 同表）；`expand(K)` 才加载 `messages` / `tool-schemas`；
- `xxhash` 预存 header digest；
- 同一 `run_id` 一次 materializes，跨 step 复用。

#### 10.5 CLI / debug 入口

```sh
lca-ops journal replay <run_id> --step K                 # 打印 StepContextAt
lca-ops journal verify-model-visible <run_id>            # 跑 I-MV1 全 run 校验
# 注意: fork-diff (跨 run 同 step 对比) 由 `diff-runs <a> <b> --step N` 接管;
# `journal replay-diff` 未实现,使用会得到 `No such command`。
```

#### 10.6 与 DSH capability 对照

| DSH | LCA |
|---|---|
| `stepContextAt` | `ReplayCursor.at(step_index)` |
| `ReplayCursor` | `ReplayCursor` Protocol |
| Fork diff | `ReplayCursor.fork_diff` |
| `model-visible ≡ logged` 断言 | `verify-model-visible` + `digest_verified` |

### D11. 写路径五面可替换矩阵（架构优雅 / 第一性原理）

> **原则**：Agent 不写 EP。Agent 只表达 **意图**；意图 → Coordinator Protocol → (Emitter → Driver → Coalescer → Serializer → Storage) **五个独立插件面**，每面有独立 Protocol + 默认实现 + 可替换实现 + profile 装配开关。

#### 11.1 五面矩阵

| 面 | Protocol | 默认实现 | 可替换实现示例 | 默认提供方 |
|---|---|---|---|---|
| **Emitter** | `EventEmitter` | `SpineEmitter` (EventSpine.append) | `OTelEmitter`、`NullEmitter`、`StdoutEmitter`、`MockEmitter` | `spine.core` |
| **Driver** | `StepDriver` | `StandardDriver`（step/segment/phase 分组） | `SimpleDriver`（无 segment）、`TurnDriver`、`SubagentLaneDriver` | `step_coordinator` |
| **Coalescer** | `Coalescer` | `LineCoalescer`（per-EP buffer） | `Passthrough`、`WindowedCoalescer`、`TopicCoalescer` | `spine.coalesce` |
| **Serializer** | `Serializer` | `NdjsonSerializer`（含 digest + envelope） | `Protobuf`、`Arrow`、`Msgpack`、`ZeroSerializer`（仅 metadata） | `spine.serializer` |
| **Storage** | `EventStorage` | `RoutingFileSink`（per-run events.jsonl + sidecars） | `SQLiteStore`、`S3Sink`、`KafkaTopic`、`MultiSink`、`NullSink` | `spine.sink.file` |

附加（0167 D9/D10 已有但需登记到矩阵）：

| 面 | Protocol | 默认 | 替换示例 |
|---|---|---|---|
| Model-visible Recorder | `ModelVisibleRecorder` | `FilesystemRecorder` (model_visible/step_N/) | `EvidenceOnlyRecorder`、`MemoryRecorder`（测试） |
| Replay Cursor | `ReplayCursor` | `StandardCursor` | `CursorStub`（开发） |

#### 11.2 写路径链路（每节独立可替换）

```text
Agent intent  →  Coordinator.emit_*(...)
                     │
                     ▼
                  Emitter          (Protocol: EventEmitter)
                     │
                     ▼
                  Driver           (Protocol: StepDriver)        ← 切步/段/相位
                     │
                     ▼
                  Coalescer        (Protocol: Coalescer)         ← 流式去抖
                     │
                     ▼
                  Serializer       (Protocol: Serializer)         ← 序列化
                     │
                     ▼
                  Storage          (Protocol: EventStorage)       ← 写到哪里
```

#### 11.3 不变量

- **I-PLUG1（Agent 不写 EP）**：Agent / Brain / Body / Perceive **只**调 `Coordinator.emit_*`；禁止直接 import EventSpine / Serializer / Storage。
- **I-PLUG2（每面独立 Protocol + registry）**：每面一个 Protocol；registry 由 `StepCoordinatorPluginRegistry` 统一管理，profile 可分别替换。
- **I-PLUG3（链上任一节可独立替换）**：换 `Serializer` 不动 Driver；换 Storage 不动 Coalescer。链上不共享可变状态；只通过 `EventRecord` 传值。
- **I-PLUG4（默认朴素、无副作用）**：默认实现 = 当前最朴素形态（spine append + StandardDriver + LineCoalescer + ndjson + RoutingFileSink），**不抢全局**，**off-by-default**。
- **I-PLUG5（不影响 SSOT）**：替换任一面不改变 SSOT 不变量（0063 I1–I7 / 0167 I-MV1-4）。`Coordinator.emit_*` 仍经 `events.jsonl`。
- **I-PLUG6（profile 装配）**：每面 plugin 在 Profile / Bundle / Patch 体系下装配（同 ADR-0096 / 0119 的 webserver plugin 模式）。同一运行可由不同 profile 组合五面。

#### 11.4 装配示例

```yaml
# profiles/web-standard.yaml —— 默认五面
plugins:
  - spine.core               # EventSpine + Emitter = SpineEmitter
  - step_coordinator.std     # StandardDriver
  - spine.coalesce.line      # LineCoalescer
  - spine.serializer.ndjson  # NdjsonSerializer
  - spine.sink.file          # RoutingFileSink
```

```yaml
# profiles/oii-debug.yaml —— 本地调试面
plugins:
  - spine.core
  - step_coordinator.std
  - spine.coalesce.line
  - spine.serializer.ndjson
  - spine.sink.file
  - spine.deriver.otel_trace          # 跨服务审计视图（0167 D9）
  - spine.deriver.waterfall           # DSH trajectory 视图
  - spine.deriver.graph               # plugin 交互图
```

```yaml
# bundles/observability-archive.yaml —— 归档型
plugins:
  - spine.core
  - step_coordinator.turn             # 按 turn 而非 step 分组
  - spine.coalesce.windowed           # 窗口化去抖
  - spine.serializer.protobuf         # 跨语言兼容
  - spine.sink.s3                    # S3Sink 归档
  - spine.sink.kafka                 # KafkaTopic 同步
```

```yaml
# bundles/observability-test.yaml —— 测试型（零副作用）
plugins:
  - step_coordinator.simple
  - spine.coalesce.passthrough
  - spine.serializer.zero             # 仅 metadata，不写内容
  - spine.sink.null
```

#### 11.5 不被五面矩阵触碰

- Agent **仍**不直接调任何写。
- `events.jsonl` 与 `journal.json` 的**事实语义**不变。
- `model_visible/` 与 `evidence/` 的**位置**仍是默认 Storage 的约定，替换 Storage 后可重定义（README 标注）。
- 原有 deriver（narrative / graph / live_tail / anomaly / step_tree）继续作为**只读投影**，不进入「写路径五面」。

#### 11.6 与既有 ADR 关系

| 既有 | 五面矩阵落点 |
|---|---|
| ADR-0063 I1–I7（SSOT） | 不变；Storage 只是 emitter 末端 |
| ADR-0165 D11 / 0165.1 D12（plugin 化 spine） | Emitter / Coalescer / Serializer 由 spine plugins 装配 |
| ADR-0166 D3（Coordinator 唯一写） | 升级为「Coordinator + 五面矩阵」 |
| ADR-0167 D9/D10（视图 + Replay） | ModelVisibleRecorder 与 ReplayCursor 加入矩阵 |
| ADR-0112 / 0119（gateway plugin） | 同模式：每面 registry = 一个 plugin |

### D12. 不做的事

- 本 ADR 不实现完整 trajectory-debug UI / 断点 / fork diff（挂在同一 SSOT 上的下一里程碑）。
- 不强制历史 run 自动迁移；提供 `journal migrate --to 3.1` + model_visible 尽力重建。
- 不让 OTel 成为 SSOT。
- 不在 standard 默认把密钥原文写入 model_visible（脱敏策略继承 AttributePolicy；完整明文仅 oii-debug 或显式 `persist_full_prompt`）。
- **`spine.deriver.otel_trace`** 默认不开（除非 oii-debug / audit profile 显式加载）；不要把 OTel 当成真值层。
- **`ReplayCursor.with_override` 不私自执行工具**；diff 是只读输出，重跑必须显式 `lca-ops journal rerun ...` 才到 sandbox。
- **不把「每条 EP 一个 manifest」**——五面矩阵就够，再细就是过度抽象。
- **不让 Coordinator 直接 import 任何具体实现**；永远是 Protocol + registry 解引用。
- **不绑 LobeHub / WebServer**；Storage 默认仍是文件系统。

### D13. 设计尊严条款（不在垃圾上堆垃圾）

清理 PR-9 起草期发现的具体垃圾后，写入强制度条款。任何后续 PR 不得违反：

| 禁令 | 反例（已删除） |
|---|---|
| **B1 唯一装配**：同一默认构造不允许两份 | 删 `default_registry()` 与 plugin `setup()` 的双写 |
| **B2 禁伪防御**：未配置就抛错的死路径 | 删 `SpineEmitter not bound` 抛错；改为强制 bind |
| **B3 显式数据结构**：禁止「用 N 个 dict 假装栈」 | `StandardDriver` 用 `_StepFrame` / `_SegmentFrame` 列表栈 |
| **B4 不假装语义**：签名分桶就按分桶实现 | `LineCoalescer` 不假装按 channel 分桶 |
| **B5 跟 dataclass 同寿命**：禁止手抄字段映射 | `NdjsonSerializer.serialize()` 用 `dataclasses.asdict` |
| **B6 符号一致**：`__all__` 必须与导出匹配 | 删 coordinator 里不存在的 `MissingWritableFace` 导出 |
| **B7 一个 plugin 一目录**：禁止把不相关 plugin 塞一文件 | `replacements.py` 拆成 `emitter/otel` `coalescer/passthrough` `storage/multi` `serializer/label` |
| **B8 不起假名**：禁止「起名 Protobuf 输出文本」 | `ProtobufSerializer` 改名 `LabelSerializer` |
| **B9 禁过渡期两边写** | 删 `perceive_coordinator_adapter`「永远 False 分支」 |
| **B10 `Any` 必带理由**：协议边界可 `Any`，其它用具体类型 | `SpineEmitter._spine: SpineLike`（Protocol）替代 `Any` |

不变量集：**I-DIGNITY1–10** ↔ B1–B10。审计 `scripts/check_writable_matrix_boundaries.py` 持续检查；PR-3 完成后改为 fail-fast。

## 后果

### 正面

- SSOT 单一，journal/narrative/UI 可丢可重建。
- 轨迹按 DSH step 语义可读；prompt/skill/tools **可打开核对**。
- 审计「模型当时看见什么」有文件级答案，不必 grep 截断 objective。

### 负面 / 风险

- 每步多写 model_visible 文件（磁盘与隐私面扩大）——用 digest + 策略档位控制。
- Coordinator 成为关键路径，必须有完备测试。
- 旧 CLI / 文档仍提 `journal.jsonl` —— PR-4/PR-5 一并改。

## 验收

1. 新跑 DSH 拓扑：`totals.steps=3 segments=5 phases=8`。
2. 每个 think step 存在 `model_visible/step_NN/{request-header,system-prompt,tool-schemas,context-manifest,messages}.json|md`（或 evidence 等价 ref），且 header digests 与文件一致。
3. `skill_catalog`（及本步注入的 skill/instruction 正文）可从 `context-manifest.json` 或 evidence **完整还原**，不仅出现在 kinds 列表。
4. `replay(events.jsonl).totals == finalize.totals`；关键 `*_digest` 一致。
5. `journal.narrative.md` 无逐条 `reasoning_delta`；含 Model saw 链接区。
6. 仓库无 `step_emitter`；cognition 无 `open_step`。
7. ADR 链无互相矛盾的「主真值」表述（以本 ADR 为准）。
8. `spine.deriver.otel_trace` / `spine.deriver.waterfall` 作为可选 profile 装配存在；不装时不生效；装了也不影响 SSOT。
9. `ReplayCursor` Protocol 与 `StepContextAt` 在 contracts 落地；CLI `journal replay / verify-model-visible` 可用；fork-diff 走 `diff-runs <a> <b> --step N`，**不调 LLM 不跑 tool**。
10. **五面矩阵 Protocol + 默认实现 + registry** 落地；任一面可被 profile 替换，**不动其他面、不影响 SSOT**（D11 I-PLUG1–6）。
11. **Agent 端不直接 import `EventSpine` / `Serializer` / `Storage`**；架构测试锁死（D11 I-PLUG1）。
12. **D13 设计尊严 10 条禁令**全部满足：B1 唯一装配 / B2 禁伪防御 / B3 显式栈 / B4 不假装语义 / B5 asdict / B6 符号一致 / B7 一 plugin 一目录 / B8 不起假名 / B9 无过渡期两边写 / B10 `Any` 最小化。

## 实施分期

| PR | 内容 |
|---|---|
| **PR-0** | 本 ADR + 0165 stub + 修订 0164/0166 指针 + 更新 run-layout / step design spec |
| **PR-1** | 合约 3.1 + `RequestHeader` + `StepWriter`/`StepCoordinator` Protocol |
| **PR-2** | Coordinator + Accumulator + Replay + model_visible writer + deriver.step_tree 实装 |
| **PR-3** | 删 `step_emitter`；loop 切步；Brain/Body 只 Writer |
| **PR-4** | Spine S1–S6；CLI/doctor/narrative 轨迹形态 |
| **PR-5** | migrator / 死代码 / 文档清理 |
| **PR-6** | TraceInspector 工具最小面（可选） |
| **PR-7** | 多形态视图 deriver：`spine.deriver.otel_trace` + `spine.deriver.waterfall`；profile 开关（D9 / I-VIEW1-3） |
| **PR-8** | 零 token 回放：`ReplayCursor` Protocol + `StepContextAt`；CLI `journal replay / verify-model-visible`（D10） |
| **PR-9** | 写路径五面插件化：`EventEmitter` / `StepDriver` / `Coalescer` / `Serializer` / `EventStorage` Protocol + 默认实现 + registry + profile 装配 + Agent 不直接 import 测试（D11 I-PLUG1–6） |
| **PR-10** | 可替换实现示例：OTelEmitter / PassthroughCoalescer / ProtobufSerializer / SQLiteStore / S3Sink（示范，不强依赖） |

## 参考

- DeepSeek Harness: `docs/architecture.md` §Session log（Model-visible means logged）；§Turn flow（`request/header`、step/start|end）
- LCA: [ADR-0063](0063-run-trace-ssot.md)、[ADR-0164](0164-journal-step-tree.md)、[ADR-0165](0165-event-spine-unified-log.md)、[ADR-0165-execution-point-enforcement](0165-execution-point-enforcement.md)、[ADR-0166](0166-step-segment-phase-and-spine-hardening.md)
- 样本: `traces/runs/run_bb1b9570ef94/`
- Spec: `docs/superpowers/specs/2026-09-02-step-segment-phase-design.md`
