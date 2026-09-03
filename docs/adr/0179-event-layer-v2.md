# ADR-0179 — 事件层 v2：单一发送者 + 闭集 category + typed 协议

## 状态

Proposed → 试点通过后转 Accepted。

## 背景

当前事件层由 7 类模块拼接：

| 模块族 | 数量 | 角色 |
|---|---|---|
| A. 业务方（构造 + 直送） | ~30 | 各自 import `JournalEvent` 子类 + `record()` 或 `emit_xxx` helper |
| B. 反射器 / helper | 9 文件 49 函数 | 按层切分，函数签名与 descriptor 表对不齐 |
| C. 消费者 / 派生 | cursor、reducer、projector、console | **部分仍兼发送者**（cursor 推 phase 同时 append spine） |
| D. 写日志 / 投影 | console projector、journal sink、sse | 多数不是插件，散在 infrastructure/ 与 plugins/transport/ |
| E. 注册表 / 描述符 | journal.py 49 子类、journal_catalog.py、event_descriptors_data.py、cordis_event_table.py | **两份等价注册表并存** |
| F. 兼容面 / 异常流 | `coord.emit_phase`、`CoordinatorAdapter.emit_phase`、`envelope_emitter._safe_emit` | 带 COMPAT 块，删除条件散落 |
| G. 插件 manifest / profile | `plugins/observability/spine/*` 整体 | **不是插件**，是普通模块 |

由此引发 4 个真问题：

1. **裸字符串多**：`emitter="lca.x.y"` 字符串路径、`cordis_name="agent.*"` glob、`type_name=cls.__name__` 字面量——三处字符串各自独立。
2. **构造权与发送权不分离**：业务方 `record(DelegationCacheHit(...))` 既构造又触发，"发送者 SSOT" 是字面口号。
3. **reducer / cursor / emit 不是同层抽象**：reducer 写 state、cursor 推 phase + append spine、emit 走 spine，三者平行实现。
4. **注册表两份**：`JOURNAL_EVENT_CLASSES`（`journal_catalog.py`）与 `build_default_registry()`（`event_descriptors_data.py`）表达同一事实，漂移风险高。

## 目标

事件层归位为 5 个 stage，每 stage 一个 owner：

```text
1. 构造（业务方）  ──typed factory──▶  2. 发布（EventSender）  ──查 descriptor──▶  3. 路由（EventRouter）
                                                                                       │
                       ┌───────────────────────────────────────────────────────────────┼───────────────────┐
                       ▼                                                               ▼                   ▼
                  4. 消费（消费者插件）                                       4. 消费                    4. 消费
                  - JournalSink                                              - PhaseCursor              - ConsoleProjector
                  - AgentStateReducer                                        - ApprovalSink             - ExceptionSink
                  - RuntimeTracer                                            - BootLogger               - ProjectionSink
```

## 不变量（11 条）

| ID | 不变量 |
|---|---|
| **E1** | 事件不允许裸字符串。`category` 是 `EventCategory` 枚举；`plane` 是 `EventPlane` 枚举；descriptor 中 `emitter` / `cordis_name` 由 category 推导，禁止字符串字面量。 |
| **E2** | 发送者是 SSOT 且负担轻。`EventSender.publish(event)` 唯一职责：查 descriptor → 路由 → 返回 `EventRef`。**不**校验 schema、**不**做路由决策、**不**感知消费者、**不**持久化。 |
| **E3** | Reducer / Cursor / Emit / Logger / Projector / Sink 全部是消费者，**不是**发送者。 |
| **E4** | 构造与发送分离。业务方只构造 `Event`，调 `sender.publish`；不 import `JournalEvent` 子类、**不** import `emit_xxx` 函数。 |
| **E5** | 协议与实现解耦。`contracts/event_v2.py` 不 import `plugins/`；`plugins/events/` 单向依赖 `contracts/`。 |
| **E6** | 闭集。`EventCategory` 在 `contracts/`，新增 category 必须有 ADR。 |
| **E7** | schema 与代码同源。descriptor 注册表是唯一来源；旧 `JOURNAL_EVENT_CLASSES` 删除。 |
| **E8** | 消费者不发送事件（防递归）。consumer 想触发新事件必须回 stage 1。 |
| **E9** | 写日志也是消费者。所有"事件描述型"日志（tracer、boot 启动、异常聚合、SSE 投影）按 `EventConsumer` 协议实现，不直接 `print()` / `logger.info()`。 |
| **E10** | 业务方只 import 一处。`from lca.contracts.event_v2 import Event, EventCategory, EventSender` + （必要时）`from lca.contracts.event_v2 import <Category>Fields`（TypedDict）。 |
| **E11** | 构造入口 typed。`sender.publish(Event(category=EventCategory.TOOL_STARTED, fields=ToolStartedFields(tool_name=..., invocation_id=...)))`。`fields` 是 TypedDict，IDE 提示完整。 |

## Event 模型（contracts 层）

```python
# lca/contracts/event_v2.py —— 不依赖 plugins/

class EventCategory(str, Enum):
    """事件类别的闭集；新增必须有 ADR。"""
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    TASK_CREATED = "task.created"
    TEAM_CASTING = "team.casting"
    TEAM_DELEGATION = "team.delegation"
    PERCEPTION = "perception"
    GATE = "gate"
    TOOL = "tool"
    LLM = "llm"
    SANDBOX = "sandbox"
    MEMORY = "memory"
    CONTROL = "control"
    PLUGIN = "plugin"
    BOOT = "boot"
    RUNTIME_OBSERVED = "runtime.observed"
    EXCEPTION = "exception"

class EventPlane(str, Enum):
    SURFACE = "surface"
    STRUCTURAL = "structural"
    EXPLANATION = "explanation"

@dataclass(frozen=True, slots=True)
class EventRef:
    event_id: str
    trace_id: str
    ts: float

@dataclass(frozen=True, slots=True)
class Event:
    category: EventCategory
    plane: EventPlane
    fields: Mapping[str, Any]
    trace_id: str = ""
    causation_refs: tuple[str, ...] = ()

class EventSender(Protocol):
    def publish(self, event: Event) -> EventRef: ...

class EventConsumer(Protocol):
    categories: frozenset[EventCategory]
    def on_event(self, event: Event, ref: EventRef) -> None: ...
```

**每个 category 一组 TypedDict**（如 `ToolStartedFields`, `DelegationCacheHitFields`）保证 IDE 提示与 descriptor schema 双向校验。

## 49 事件 → 8 category 映射

| 新 category | 现 descriptor（49 事件） | 关键字段 |
|---|---|---|
| `RUN_STARTED` / `RUN_FINISHED` | `TeamRunStarted/Finished`, `AgentRunStarted/Finished` | status, agent_role, strategy_key, members, mandate |
| `TASK_CREATED` | `TaskCreated` | task_id, session_id, objective |
| `TEAM_CASTING` | `CastingStarted/Completed/Failed` | objective_preview, governance_kind, selected_roles, error |
| `TEAM_DELEGATION` | `DelegationIssued/Completed/CacheHit`, `SynthesisCompleted`, `TeamMessagePublished` | delegation_id, callee_role, status, candidate_count, team_id, thread_id |
| `PERCEPTION` | `ContextManifested`, `PerceptionMerged`, `StepTextDelta`, `ReasoningDelta/Completed`, `RunActivity` | digest, delta_ref, step, seq, phase |
| `GATE` | `DecisionMade`, `StepCompleted`, `ActionDegraded`, `GateDecided` | action_type, step, gate, verdict, degraded_to |
| `TOOL` | `ToolStarted/Invoked/Denied/LifecycleEnded/AbandonedBeforeInvoke/RetryProgress`, `AttachmentStaging*` | tool_name, invocation_id, end_kind, phase_id, plane_id, file_count |
| `LLM` | `LlmCallStarted/Completed`, `SandboxOutputDelta`, `ToolCallResolved` | model, latency_ms, tokens, invocation_id, seq, tool_name |
| `MEMORY` | `MemoryCommitted`, `ContextCompacted` | layer, record_id, step |
| `CONTROL` | `ApprovalRequested/Resolved`, `RunPaused/Resumed`, `InboxFollowupCreated` | envelope_id, tool_name, step, reason, inbox_id |
| `PLUGIN` | `PluginAuthored/Mounted/MountRejected/Unmounted/Inspected`, `PresetPublished` | plugin_name, plugin_id, reason_code, preset_id |
| `BOOT` | `BootProfileResolved`, `BootPluginFiberSpawned`, `BootObservabilityAssembled` | profile_path, manifest_hash, plugin_id, stage, bound_seams |
| `RUNTIME_OBSERVED` | `RuntimeObserved` | kind, operation, source, outcome, attributes |
| `EXCEPTION` | 由 `RuntimeTracer` 消费者派生 | kind, source, message, traceback |

> 试点范围只覆盖 `TEAM_DELEGATION.DELEGATION_CACHE_HIT`（即原 `DelegationCacheHit`）。其余 48 事件待迁移 PR 逐个补字段 TypedDict + descriptor row。

## 试点范围（P2）

| 项 | 范围 |
|---|---|
| 业务方迁 | `lca/cognition/body/delegation_cache.py::cached_delegation_observation` — 改为 `sender.publish(Event(category=TEAM_DELEGATION, fields=DelegationCacheHitFields(callee_role=..., subtask_preview=..., step=...)))` |
| 消费者迁 | `lca/plugins/events/consumers/console_projector.py` — 订阅全量 category，渲染与现 `ConsoleJournalProjector._render_delegation_cache_hit` 等价 |
| 插件 manifest | `lca.plugins.events.sender` (provider) + `lca.plugins.events.consumer.console_projector` (sink) |
| profile | `profiles/web-standard.yaml` 增加两个插件条目 |
| 测试 | 4 个：`test_event_v2`、`test_sender_publish`、`test_consumer_subscription`、`test_pilot_delegation_cache` |
| **不在范围** | 其他 29 个 A 类、reducer、cursor、tool、llm、approval、boot、memory、其他 sink、runtime 内部事件 |

## 旧路径"删-when"清单

| 旧路径 | 删-when 草案 |
|---|---|
| `lca/contracts/models/observability/journal.py` 49 个 `JournalEvent` 子类 | 新协议覆盖全部 49 事件 + 17 业务模块全部迁完 + journal 双写 0 + 14 天 |
| `lca/contracts/models/observability/journal_catalog.py::JOURNAL_EVENT_CLASSES` | `rg "JOURNAL_EVENT_CLASSES" lca/ = 0` + `test_observability_boundary` 绿 |
| 4 个 reflector 文件（`cognition.py` `body_llm.py` `runtime.py` `agent_spawn.py`） | 30 个 A 类全部迁完 + `rg "from .reflectors" lca/ = 0` |
| `lca/cognition/body/tool_journal_emit.py` | `safe_executor` / `pipeline_safe_executor` 迁完 |
| `lca/runtime/envelope_emitter.py` `_safe_emit` 间接层 | reducer 直发 sender |
| `lca/infrastructure/observability/loop_cursor/coordinator_adapter.py::emit_phase` | cursor 改成纯消费者 |
| `lca/infrastructure/observability/writable_matrix/coordinator.py::emit_phase` | 已 `_block_ep_write`，仅留死代码 → 本 PR 删除 |
| `lca/infrastructure/observability/spine/transport_emit.py` | 改成 `KernelRunSender` 插件 |
| `lca/infrastructure/observability/spine/exception_emit.py` | 合并到 `RuntimeTracer` 消费者 |
| `lca/plugins/observability/spine/*`（13 个文件） | 整体下沉为 `plugins/events/` 子目录 + plugin manifest |
| `lca/contracts/observability/cordis_event_table.py`（字符串 glob） | 删除，由 category enum 推导 |
| 旧 descriptor 表 `emitter="lca.x.y"` 字符串 | 删除 |
| `docs/notes/implemented/contract/2026-09-03-exception-caught-single-emitter.md` | **吸收到本 ADR §3.3**，note 改 link |

## 取代与吸收

| 被取代/吸收 | 条款 |
|---|---|
| ADR-0063 PR-7（Journal SSOT + descriptor 注册表） | **取代** descriptor 注册表实现；保留"事件账本是 SSOT"原则 |
| ADR-0116（boot 事件） | 适用，boot 期走同一 `EventSender` |
| ADR-0168-final §D14（`EventDescriptor.cordis_name`） | **取代**：`cordis_name` 由 `category` enum 推导 |
| ADR-0169 §11（cursor 适配） | **取代**：`coord.emit_phase` 整体删除 |
| `exception-caught-single-emitter.md` | **吸收**为 §3.3（消费者单 emitter） |

## 迁移 PR 切分草案（试点通过后启动）

每 PR 一个 A 类业务模块，附"删-when"块：

| PR | A 类模块 | 事件 |
|---|---|---|
| 试点 PR（本 ADR） | `delegation_cache.py` | `DelegationCacheHit` |
| 2 | `safe_executor.py` | `ApprovalRequested/Resolved`, `ToolStarted/Invoked/Denied` |
| 3 | `pipeline_safe_executor.py` | `Tool*` |
| 4 | `simple_body.py` | `StepCompleted`, `ActionDegraded` |
| 5 | `action_handlers.py` | `DecisionMade`, `SynthesisCompleted` |
| 6 | `simple_memory.py` | `MemoryCommitted`, `ContextCompacted` |
| 7 | `perceive_hub.py` | `PerceptionMerged` |
| 8 | `context_manifest.py` | `ContextManifested` |
| 9 | `decision_gates/*.py` | `GateDecided` |
| 10 | `team_mode.py` | `Casting*` |
| 11 | `team_handle.py` | `TeamRun*`, `TeamMessagePublished` |
| 12 | `cognitive_agent.py` | `AgentRun*` |
| 13 | `dispatcher.py` | `TaskCreated` |
| 14 | `llm_turn/executor.py` | `ToolCallResolved` |
| 15 | `adapters/adapters.py` | `StepTextDelta`, `Reasoning*`, `LlmCall*` |
| 16 | `sandbox/*.py` | `SandboxOutputDelta` |
| 17 | `cordis_control.py` | `Plugin*` |
| 18 | `preset_authoring.py` | `PresetPublished` |
| 19 | `loop_drivers.py` | `InboxFollowupCreated` |
| 20 | `attachment_staging.py` | `AttachmentStaging*` |
| 21 | `phase_execution_policy.py` | `ToolLifecycleEnded`, `ToolAbandonedBeforeInvoke`, `ToolRetryProgress` |
| 22 | `runtime_loop.py` + `runtime_lifecycle*.py` | `RunPaused/Resumed`（runtime 内部事件后处理） |
| 23 | `lca_kernel/{source_resolve,boot,observability}.py` | `Boot*` |
| 24 | reducer / cursor | 消费者化 |
| 25 | 旧 reflector / envelope_emitter / journal_catalog 删除 | 收口 |

每 PR 同时删除该模块对 `JournalEvent` 子类的直接构造与对 `record()` 的直接调用；旧 `record()` 路径仍保留 `DeprecationWarning` + journal 计数直至 PR 25。

## 风险与回滚

- **风险 1**：试点双写期间旧 journal 行与新 journal 行格式不一致。**缓解**：试点期 `sender.publish` 内部委托给现 `JournalBackend.write`，让现 journal sink 写入；新协议与旧协议在同一 journal 行格式里并存。
- **风险 2**：消费者订阅语义不足（如需按 `fields["tool_name"]` 过滤）。**缓解**：试点期就验证；不足时扩 `EventConsumer.on_event` 接收完整 event。
- **风险 3**：`sender` 阻塞运行路径（journal I/O）。**缓解**：试点实现为 fire-and-forget；后续 PR 引入 batched queue。
- **回滚**：试点 PR 不删旧路径，回滚 = 撤回试点 PR 即可。

## 试点"盖章"判定

试点 PR 合并前必须回答 4 个问题：

1. **业务方调用形态**是否真的"负担轻"？字段 IDE 提示是否完整？
2. **消费者订阅语义**按 category 过滤是否够用？
3. **descriptor 路由** category 闭集 + TypedDict schema 校验是否足够？
4. **journal 双写期**旧 `record(DelegationCacheHit(...))` 与新 `sender.publish(...)` 是否产生相同 journal 行？

4 个问题都通过 → ADR 转 Accepted，进入 PR 2–25 灰度。
