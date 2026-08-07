# ADR-0037: Journal-as-Truth —— 执行日志为唯一真相，span 树降级为投影

## 状态
Accepted

## 背景

### 生产 trace 复盘暴露的三个结构性病症

对 Langfuse 最新一条 board 协作 trace（`run.team`，45.7s，25 observations）的
独立复盘显示：数据完备（model/tokens/IO/父子链俱全），但人类不可读——必须
编写脚本做"trace 考古"才能还原"谁被咨询、谁用了工具、瓶颈在哪"。病症有三：

1. **拓扑倒置**：span 树的形状由 OTel context 传播（机制）决定，而非协作语义。
   `InternalTransport.send_task` 用 `asyncio.create_task` 调度成员，任务继承
   发射瞬间的 contextvars——成员 `run.agent` 因此永远挂在 **0 秒即关闭的
   `transport.request`** 之下。代码注释自认此债："transport.request 保留——
   它承载成员 run.agent 的父子链"（`langfuse_conventions.py`）。这是用补丁
   维护倒置结构。
2. **叙事层缺失**：一棵 span 树同时承担计时、成本、叙事、事件日志四种职责。
   `step.completed` 事件只能伪装成 0 秒 SPAN；委派（delegation）这一团队协作
   的核心动作没有一等公民表示；lead 路径的"收口综合"（synthesis）完全不可见。
3. **渲染外包**：期望通用后端（Langfuse 的 trace/span/generation 视图）呈现
   团队协作叙事，等于期望裸数据库呈现报表。关键路径、冗余调用、成本汇总全靠
   人眼考古。

### 隐藏 bug（复盘附带发现）

`facade.get_span_context()` 的 `parent_span_id` 恒返回 `None`，导致
`CognitiveAgent.top_level` 门恒为 True——**每个成员都错误发射自己的 solo
场景卡**（该 trace 中 5 张 run.plan，应为 1 张）。

### 业界范式对照

| 产品/范式 | 核心招数 | 本框架差距 |
|---|---|---|
| OpenAI Agents SDK tracing | `agent` / **`handoff`** / `tool` / `guardrail` / `generation` 一等 span 类型 | 委派是 0 秒 transport 化石 |
| LangSmith | 类型化 run + parent_run_id 关联 + thread 聚合 + 回放 | 父子靠 ambient context，无关联 ID |
| AgentOps | session replay：事件流重渲染 | 无持久化日志，无回放 |
| Arize Phoenix / OpenInference | 标准化 span kind 语义约定 | 词表已有（SpanName），但拓扑不跟词表走 |
| LobeHub/LobeChat | **过程即数据**：执行记录是主数据，UI 渲染白送 | 记录是遥测旁路，非数据 |
| Honeycomb / Observability 2.0 | 宽事件 + 查询优先 | 属性策略已具备此精神 |

公共范式：**结构化执行日志（journal）是唯一真相；span 树、时间轴、成本表、
序列图都只是它的投影。语义在写入期确定，视图是渲染出来的，洞察是计算出来的。**

## 决定

### 一、平面划分（依赖方向倒转）

```
协作运行时（team_handle / cognitive_agent / action_handlers / adapters / ...）
    │  只在语义边界 record(JournalEvent)
    ▼
执行日志 ExecutionJournal（append-only，关联 ID 为骨架）
    │
    ├─ OtelProjector      → OTel span/event（拓扑由关联 ID 显式生成）→ Langfuse/任何 OTel GenAI 后端
    ├─ ConsoleProjector   → 实时叙事 + Run Card（digest 终态卡）
    ├─ JsonlProjector     → journal 落盘（record schema 版本化，可回放）
    ├─ SequenceProjector  → Mermaid 序列图（协作叙事一目了然）
    └─ InsightEngine      → 计算洞察（冗余调用/关键路径/成本/循环）→ RunInsight 事件回注日志
```

- **叙事平面（journal）**：我们拥有的领域真相，contracts 层词表。
- **机制平面（span）**：认知相位（loop.phase.*）、hook 边界、memory 读写、
  transport 往返——保留现有 ambient span 发射，但降级为 verbose 档调试细节，
  标准档不进 Langfuse。
- **交换格式（OTel）**：对外仍是业界标准；对内只是 journal 的一个投影。
  "内部 journal 为真相，外部 OTel 为交换格式"——对齐 OpenInference/LangSmith
  哲学：拥有自己的模型，导出标准。

### 二、关联骨架（correlation spine）—— 父子关系不再依赖 ambient context

每个 journal 事件携带（引擎在 record 时从 ambient `RunScope` 盖章）：

| 字段 | 含义 |
|---|---|
| `trace_id` | 整次团队/单兵 run 的追踪 id |
| `run_id` | 一个 agent run 容器的 id（团队根、lead、成员各一个） |
| `parent_run_id` | 生成此 run 的 run（根为 None） |
| `delegation_id` | 生成此 run 的委派（无则 None） |
| `agent_role` | 当前 run 的角色（资源 span 身份盖章） |

`RunScope` 是 contracts 的 contextvar 记录，在 run 边界设置：
`CognitiveAgent.run` 生成 `run_id`，从调用方 scope 继承 `parent_run_id`/
`delegation_id`。委派方在发射 `DelegationIssued` 时生成 `delegation_id`，
经 `delegation_scope`（扩展 `delegator_scope`）穿透 `asyncio.create_task`
边界——成员任务在被调度时继承关联骨架。外部 transport（A2A/MCP）优雅
降级为仅 from_role。

**OtelProjector 定父（实现定稿）**：
- run/delegation 容器与资源 span 以关联骨架显式查表定父
  （`start_span(context=...)`），与事件到达顺序无关，并行委派不串线；
- delegation 父节点为混合判据：事件时刻 ambient 若非投影器自有容器
  （即策略层包络如 `team.round`）则就近挂载，否则退回 run 关联——
  swarm/debate 的轮次包络因此保住子树；
- run 容器额外 attach 进 ambient：机制平面 span（相位/记忆/传输，仍走旧
  `span()` API）以 run.agent 为最近附着祖先正确归位；
- 瞬时事实（决策/步/降级/短路/综合/洞察）投影为所属 run span 的 event，
  不再产生孤儿 0 秒 span；EventBus 桥接事件经 `drain()` 在容器关闭前落地。

**0 秒化石 span 与错挂父子链在构造上不可能再出现**。顺带修复 `top_level`
恒 True 的隐藏 bug（判据改为继承 scope 是否存在）。

### 三、Journal 事件词表（contracts 层，纯 dataclass，遵守 ADR-0015）

关联骨架由引擎盖章，事件本体只带领域字段：

| 事件 | 语义 | 关键字段 |
|---|---|---|
| `TeamRunStarted` | 团队 run 容器开 + 场景卡 | team_id, strategy_key, mandate?, lead_role?, members, objective_preview, plan_steps |
| `TeamRunFinished` | 团队 run 容器闭 | status, output_text, output_truncated?, steps |
| `AgentRunStarted` | agent run 容器开（根 run 兼场景卡） | agent_role, strategy_key, objective_preview, from_role? |
| `AgentRunFinished` | agent run 容器闭 | status, output_text, output_truncated?, steps, error? |
| `DelegationIssued` | **委派发起（一等公民）** | delegation_id, caller_role, callee_role, subtask_preview, mechanism(delegate\|handoff\|member_invoke), parallel_group? |
| `DelegationCompleted` | 委派回执 | delegation_id, ok, status, output_text, output_truncated?, task_id? |
| `DelegationCacheHit` | 委派幂等短路 | callee_role, subtask_preview, step |
| `SynthesisCompleted` | **收口综合（lead board 可见化）** | method, candidate_count, output_text, output_truncated? |
| `DecisionMade` | 决策事实 | step, action_type, rationale_preview, delegate_target?, tool_name?, confidence? |
| `LlmCallCompleted` | LLM 调用完成（投影为 generation） | model, ok, latency_ms, prompt_preview, response_preview, prompt_tokens?, completion_tokens? |
| `ToolInvoked` | 工具调用完成 | tool_name, arguments_preview, result_preview, ok, latency_ms, attempt |
| `ToolDenied` | 权限/校验拒绝 | tool_name, reason |
| `StepCompleted` | 步生命周期 | step, status, action_type? |
| `ActionDegraded` | 动作降级 | original_action_type, degraded_to, step |
| `RunInsight` | 计算洞察（InsightEngine 回注） | kind, summary, detail |

词表登记在 `JOURNAL_CATALOG`（emitter 前缀 + 必备字段），AST 守卫强制
"一事件一发射点"，与既有 `TELEMETRY_CATALOG` 同构。事件经 `record(...)`
发射（包根 ambient API，与 span/event 并列第四形态）。

### 四、Projector 契约（layer0，Protocol + 注册表）

```python
class JournalProjector(Protocol):
    def on_event(self, stamped: StampedEvent) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
```

- 投影器只读、幂等、故障隔离（单投影器异常不中断 run，沿用 `_IsolatedExporter`
  模式）。
- 后端选择串语义映射：`console` → ConsoleProjector；`jsonl` → JsonlProjector；
  `langfuse` / `memory` → OtelProjector（+ 既有导出器/桥）。多后端组合不变
  （`console+langfuse`）。
- **verbosity 贯穿两平面**：minimal=仅 Run Card 与错误；standard=+ 叙事行
  （委派/工具/决策/LLM）；verbose=+ 机制平面 span + Mermaid 序列图 + 全文预览。
- 属性策略（脱敏/截断）在 journal 写入期统一强制——发射点仍然不需要自觉。

### 五、OtelProjector 的 Langfuse 映射（接管既有约定）

| journal 事件 | OTel/Langfuse 形态 |
|---|---|
| TeamRunStarted/Finished | `run.team` span（根；session.id、tags、根 I/O 在此盖章） |
| AgentRunStarted/Finished | `run.agent` span（`langfuse.observation.type=agent`，metadata.agent_role） |
| DelegationIssued/Completed | **`delegation` span**（包住成员全程；callee/caller/mechanism 属性） |
| LlmCallCompleted | `llm.chat` generation（gen_ai.* 语义约定，token/成本自动核算；显式起止时间） |
| ToolInvoked | `tool.execute`（type=tool） |
| DecisionMade/StepCompleted/ToolDenied/ActionDegraded/RunInsight | OTel span event 挂所属 run span（不再是孤儿 0 秒 span） |
| SynthesisCompleted | `team.synthesis` span event / span（board 收口可见） |

既有 `run.plan` 空壳 span 废除：场景卡是 `*RunStarted` 事件的投影属性，
console 渲染卡片、Langfuse 落根/agent observation 的 input 与 plan 属性。
`team.strategy` 空壳 span 废除（strategy_key 已是 run.team 属性）。
`transport.request/response` 降级机制平面（verbose 可见；标准档 Langfuse 隐藏，
父子链改由 delegation span 承载）。`team.member_invoke` 由 `delegation`
span 取代（mechanism=member_invoke）。`team.round`（swarm/debate）保留为
attached span（策略层协作包络，本就正确）。

### 六、Insight 层（trace 的价值 = 计算出来的洞察）

`InsightEngine` 在根容器关闭时对 journal 做纯函数分析，产出 `RunInsight`
回注日志（所有投影器可见；异常类经 hub scorer 挂 Langfuse score）：

| 规则 | 检测 |
|---|---|
| `redundant_tool_call` | 同 run 内 (tool_name, arguments) 重复 |
| `critical_path` | 容器耗时链（谁卡住了全程） |
| `cost_summary` | LLM 次数/token 汇总（按 model） |
| `loop_warning` | 步数逼近预算 / 连续同质动作 |
| `slowest_calls` | top-N 最慢 LLM/工具调用 |

### 七、Run Card 与序列图（人类视图的终态形态）

根容器关闭时 ConsoleProjector 输出 Run Card：

```
╭─ run card ──────────────────────────────────────────────
│ team-lead · board · 45.7s · completed
│ members: 解决方案架构师✓(1 llm) 商务经理✓(3 llm·1 tool) 产品经理✓(1 llm)
│ llm: 6 calls · tokens 8.1k→4.3k
│ critical path: 商务经理 20.5s → lead 收口 24.7s
│ ⚠ redundant_tool_call: 商务经理 calculator("2400000 * 0.2") ×2
╰──────────────────────────────────────────────────────────
```

SequenceProjector 输出 Mermaid 序列图（lead ⇄ 成员 的咨询/回执/收口），
verbose 档 console 直出，journal 落盘后可由 replay 脚本重建——验收标准：
**把 Run Card + 序列图贴给未参与者，他不提问即可复述 run 全过程。**

### 八、分阶段路线（每阶段 pipeline 全绿）

| Stage | 内容 | 验收 |
|---|---|---|
| 0 | contracts journal 词表 + 引擎 + RunScope + 守卫测试 | 词表/守卫/引擎单测全绿，行为零变化 |
| 1 | OtelProjector（显式父子）+ hub 装配 | 投影器单测：事件流 → 正确拓扑 |
| 2 | 运行时语义边界改 record()（双写过渡） | 关联骨架贯通，delegation span 包住成员全程 |
| 3 | ConsoleProjector + Run Card | scripted 场景 console 快照 |
| 4 | InsightEngine 五规则 | 冗余调用/关键路径断言 |
| 5 | JsonlProjector + replay CLI | journal 落盘可重放出 Run Card/序列图 |
| 6 | 旧发射路径清除 + 机制平面降级 verbose + Langfuse 视图验收 | 真实 run 对照复盘标准 |

## 后果

- 正面：叙事与机制分治；父子链由关联 ID 构造性保证；委派/综合一等公民；
  洞察自动计算；journal 落盘可回放（LobeHub 式 record-as-data）；OTel 交换
  标准保留；后端可插拔性不变（新后端 = 新投影器）。
- 负面：breaking change（沿用 ADR-0030 约定，无 shim）——`run.plan` /
  `team.strategy` / `team.member_invoke` span 消失，`transport.request` 从
  Langfuse 标准视图退场，jsonl record schema 换代（`journal.v1`）；依赖旧
  拓扑断言的测试（trace_coherence / team_modes_scripted / noise_filter）按
  新拓扑刻意更新。
- 中性：机制平面数据不丢失（verbose 全量）；成本核算、脱敏、采样、故障隔离
  语义不变；`TeamSpec.observability` 字段与选择串 API 不变。

## 相关

- Keeps：OTel 骨干重建（ADR 前序 commit 1ee833b）、contracts 无行为类
  （ADR-0015）、封闭团队策略（ADR-0034）、TeamAwareness 统一会话（ADR-0035）、
  领域语言 Lead/Coordination（ADR-0030）。
- 对标：OpenTelemetry GenAI semantic conventions、OpenInference span kinds、
  OpenAI Agents SDK tracing taxonomy、LangSmith run model。
