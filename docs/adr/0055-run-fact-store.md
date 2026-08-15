# ADR-0055: Run Fact Store — 以不可变事件为事实源的 Agent 运行时遥测与证据平台

## 状态

Accepted（取代 ADR-0037 的实现路径；保留 Journal-as-Truth 哲学，升级为事件平台架构）

## 背景

### 从第一性原理重新审视

ADR-0037 确立了 Journal-as-Truth 的哲学：叙事平面为唯一真相，span 树降级为投影。它解决了 OTel 拓扑倒置、叙事层缺失、渲染外包三个结构性问题。

但 ADR-0037 的实现路径在三个点上不够彻底：

1. **写入顺序不保证持久先于观察**：`ExecutionJournal.record()` 内存 append → fan-out 所有 projector。若 JsonlProjector 写入失败，SSE/OTel 已观察到该事件。对调试日志可接受；对需要可恢复、可审计的业务 Agent Runtime，这是正确性边界问题。
2. **终态双 owner**：`execute_dsh_session()` 的 `finally` 调用 `projector.finish()`，gateway `finalize()` 调用 `_write_terminal_status()`。两条路径独立设置终态，可漂移。
3. **InsightEngine 在 fan-out 路径内回写**：`drain_followups()` 在所有 projector 看到事件后 `record(RunInsight)`——读路径反向修改写路径的结构性例外。

更深层的问题是：**我们没有从 Agent 运行的本质出发设计日志，而是在「更好的 observability」框架内打补丁。**

### Agent 运行不是日志的收集，而是事实系统的构建

Agent 的复杂性不来自「日志量大」，而来自执行具有异步性、非确定性、长时运行、跨模型/工具/服务、可并行/可递归、且常常需要审计与回放。因此，系统的第一能力不是「记录文本」，而是可靠地回答：

> **谁在什么上下文中，以什么策略，做了什么尝试，调用了什么能力，产生了什么结果，为何发生、能否复现、是否可信。**

这要求我们从第一性原理出发，构建一个**以不可变事件为事实源、以因果关系为组织方式、以策略为边界、以多种读模型为服务形态的遥测与证据平台**。

### 代码评估：什么保留、什么重建

对现有代码的逐模块评审结论：

| 模块 | 评估 | 决策 |
|---|---|---|
| `JournalEvent` 词表（frozen dataclass） | **优雅**：纯数据、无行为、语义清晰、metadata 标记内容字段 | **保留** |
| `StampedEvent`（4 字段 envelope） | **优雅**：seq + ts + scope + event，最小且完整 | **保留为内核**，渐进扩展 |
| `RunScope`（关联骨架） | **优雅**：显式 ID 构造，不依赖 ambient OTel context | **保留**，补充因果键层次 |
| `JOURNAL_EVENT_CLASSES` 词表治理 | **优雅**：一事件一登记，AST 守卫强制 | **保留**，叠加分类元数据 |
| `AttributePolicy`（脱敏/截断） | **优雅**：写入期强制，不靠自觉 | **保留** |
| `_IsolatedProjector` 故障隔离 | **优雅**：异常只记 log，不传播 | **保留**，语义升级为 subscriber |
| `facade.record()` ambient API | **优雅**：业务层唯一发射面，Null Object 降级 | **保留** |
| `ExecutionJournal.record()` 流水线 | **结构性缺陷**：append-before-observe 不保证 | **重建为 RunStore** |
| `InsightEngine.drain_followups()` | **结构性缺陷**：读路径回写事实流 | **重建为普通 subscriber** |
| `DshJournalProjector.finish()` | **结构性缺陷**：终态双 owner | **删除，终态由 reducer 推导** |
| `FacadeJournalSink` + ContextVar | **结构性缺陷**：跨线程 ContextVar 不可靠 | **重建为显式 RunHandle** |

**结论**：contracts 层的 dataclass、词表治理、属性策略是真正的架构资产，一行不改。engine 层的写入流水线、fan-out 模型、终态管理和上下文传递需要按第一性原理重建。

## 决定

### 第一性原理：六条不可违反的不变量

从「Agent 运行时的遥测系统到底要解决什么问题」出发：

| # | 不变量 | 含义 | 违反后果 |
|---|---|---|---|
| **N1** | **Append-before-observe** | 事件在 log 中原子落地后，观察者才能看到它 | 观察者看到「幽灵事件」——持久化失败但 SSE/OTel 已发出 |
| **N2** | **seq = log.length** | 序号由 log 长度唯一确定，连续不跳跃 | 重连/回放丢失事件或重复消费 |
| **N3** | **State is derived** | Run 状态是 log 的纯函数，不存在独立的 mutable state | 日志与状态漂移（journal 说 completed，gateway 说 failed） |
| **N4** | **Projection is read-only** | 投影器/subscriber 只消费事件，不产生事件 | 读路径回写导致因果混乱 |
| **N5** | **Schema metadata is declarative** | durability / audience / sensitivity 是 schema 级声明，不是实例级字段 | 每条记录携带 15 个字段的 envelope 是在用基础设施承载领域语义 |
| **N6** | **Classification before storage** | 数据分类（诊断/运行/审计/敏感载荷）在写入前确定，决定投递保证、保留策略和访问控制 | 所有事件混入同一索引，无法独立治理保留期、访问权和灾备等级 |

这六条不变量是所有架构决策的推导起点。N1-N5 继承自 ADR-0055 v1，N6 来自 Manus 指南的核心洞察：**日志既用于排障，也可能构成审计证据、成本凭据、评估样本和产品行为数据——必须从第一天起区分诊断事件、运行事件、审计事件、敏感载荷。**

### 因果键层次：三级关联体系

Agent 运行不是单一 HTTP 请求。系统必须原生存储三层因果关系：

| 关系层 | 关键标识 | 解决的问题 | 现状 |
|---|---|---|---|
| **分布式技术调用链** | `trace_id`、`span_id` | 请求跨进程、跨服务时如何连起来 | ✅ `RunScope.trace_id` |
| **Agent 业务执行图** | `run_id`、`parent_run_id`、`delegation_id`、`agent_role` | 用户目标如何被拆解、委派、重试与收敛 | ✅ `RunScope` 已有 |
| **外部副作用与证据链** | `tool_call_id`、`invocation_id` | 某个工具调用是否真的发生、是否经过授权 | ⚠️ 散落在事件字段中，未统一 |

**决策**：`RunScope` 保持当前设计（trace + run + parent + delegation + role），不引入额外因果键到 envelope。工具副作用的 `invocation_id` 保留在事件 payload 中（`ToolStarted.invocation_id`、`ToolInvoked.invocation_id`）。未来引入 Effect Ledger 时（ADR-0056），`effect_id` 和 `idempotency_key` 作为 effect 层独立标识。

### 架构总览：一主干，多平面

```
┌─────────────────────────────────────────────────────────────────┐
│  生产面：Telemetry Facade（facade.record / span / event）        │
│  ├── 业务层只依赖一个稳定门面，不知道后端                         │
│  ├── DSH Adapter：DshJournalProjector → RunHandle.store.append  │
│  └── Native Adapter：facade.record(JournalEvent)                │
├─────────────────────────────────────────────────────────────────┤
│  写入面：RunStore（唯一写入仲裁）                                 │
│  ├── ① 词表校验 ② RunScope 盖章 ③ AttributePolicy 策略          │
│  ├── ④ 原子入 log（commit boundary）                            │
│  └── ⑤ post-commit 通知所有 subscriber（失败隔离）               │
├─────────────────────────────────────────────────────────────────┤
│  读取面：Post-commit Subscribers（纯只读）                        │
│  ├── JsonlBackend（jsonl 持久化——N1 的关键：此步骤在 commit 后）  │
│  ├── LiveTail（SSE 实时推送）                                    │
│  ├── OtelProjector（OTel/Langfuse 交换格式）                     │
│  ├── ConsoleProjector（开发期终端输出）                           │
│  └── InsightEngine（聚合事件，run 收尾时 append RunInsight）      │
├─────────────────────────────────────────────────────────────────┤
│  派生面：Run State Reducer + Projection                          │
│  ├── fold_run_state(events) → RunState（终态唯一推导）           │
│  ├── stamped_to_sse_frame()（SSE 投影）                         │
│  └── run_narrative / plan_narrative（叙事投影）                  │
└─────────────────────────────────────────────────────────────────┘
```

### 一、RunStore —— 唯一写入点（不变量 N1, N2）

`ExecutionJournal` 重命名并收敛为 `RunStore`。**一个 run 的所有事实只通过一个入口写入**。

```python
class RunStore:
    """Append-only run fact log。不变量 N1 + N2。

    设计来源：DSH Session.append()（同步原子 + post-commit 通知）、
    EventStore expected-version CAS（并发控制）、
    Kafka consumer-managed offset（观察者自拉）。
    """

    def append(self, event: JournalEvent) -> StampedEvent:
        """原子写入：校验 → 盖章 → 策略 → 入 log → post-commit 通知。

        关键：subscriber 通知在 append 成功后，subscriber 失败不影响返回值。
        """

    def events(self) -> tuple[StampedEvent, ...]:
        """已提交事件的只读快照。"""

    @property
    def seq(self) -> int:
        """下一条事件的 seq（= len(log)）。"""

    def read_from(self, after_seq: int) -> Sequence[StampedEvent]:
        """观察者自拉：返回 seq > after_seq 的所有已提交事件。"""

    def flush(self) -> None: ...
    def close(self) -> None: ...
```

**写入流水线**：

```
append(event)
  ├── ① 校验（schema 在 JOURNAL_EVENT_CLASSES 中）
  ├── ② 盖章（RunScope —— 来自显式 RunHandle 或 ContextVar）
  ├── ③ 策略强制（AttributePolicy 脱敏/截断）
  ├── ④ 查 catalog 获取 durability（required / best_effort）
  ├── ⑤ 原子入 log（self._log.append → seq 递增）  ← commit boundary
  └── ⑥ 通知所有 subscriber（快照当前列表，逐个通知，失败记 log 不传播）
       └── subscriber 异常 → structlog.warning，不影响 append 返回值
```

**与现有 `ExecutionJournal.record()` 的关键区别**：

步骤 ⑤ 和 ⑥ 之间有明确的 **commit boundary**。现有代码的 `_events.append` 和 `projector.on_event` 在同一个循环体内，没有这个边界。新增步骤 ④ 按 schema 分类决定持久化失败的降级行为。

**与现有 `ExecutionJournal` 的关键区别**：

| 维度 | 现有 ExecutionJournal | RunStore |
|---|---|---|
| 写入模型 | 内存 append → 主动 fan-out | 原子 append → post-commit 订阅通知 |
| 观察者角色 | projector 被 engine push | subscriber 被通知（失败隔离，不影响 append） |
| 分类感知 | 无 | 按 catalog durability 决定 best_effort 降级 |
| 读取模型 | `events` property 返回内部 list 的 tuple | 同 + `read_from(after_seq)` 支持水位自拉 |
| 回写 | `drain_followups` 在 fan-out 路径内 record | **禁止**——产生事件走正常 `append` |

### 二、数据分类与投递保证（不变量 N6）

借鉴 Manus 指南的 L0/L1/L2 分级，适配 LCA 当前单进程规模：

| 等级 | 适用事件 | 投递保证 | 实现机制 |
|---|---|---|---|
| **L0: best_effort** | `StepTextDelta`、`ReasoningDelta`、`RunActivity`、`SandboxOutputDelta` | 高压时可丢，必须产生聚合丢弃计数 | 非阻塞内存队列、限额、优先丢弃 |
| **L1: required** | `TeamRunStarted/Finished`、`AgentRunStarted/Finished`、`DelegationIssued/Completed`、`DecisionMade`、`ToolInvoked`、`LlmCallCompleted` | 可重复；可定义 RPO；不能静默丢失 | 批处理、重试、逐行 flush、subscriber 幂等 |
| **L2: audit** | （当前无独立审计事件；`ToolDenied`、`CastingCompleted` 接近） | 写入未被确认前不得宣称操作已被可审计记录 | 写前持久化、独立证据库（未来 Phase） |

**在 catalog 中声明**：

```python
@dataclass(frozen=True)
class JournalSchemaMeta:
    """Schema 级声明：所有该类型的实例共享同一份元数据。"""
    durability: Literal["required", "best_effort"]
    audience: Literal["end_user", "operator", "auditor", "restricted"]
    sensitivity: Literal["public", "internal", "confidential"]
    retention_class: str  # e.g. "default", "short", "permanent"

JOURNAL_CATALOG_META: dict[str, JournalSchemaMeta] = {
    "TeamRunStarted":    JournalSchemaMeta("required",    "auditor",    "internal",     "default"),
    "TeamRunFinished":   JournalSchemaMeta("required",    "auditor",    "internal",     "default"),
    "AgentRunStarted":   JournalSchemaMeta("required",    "auditor",    "internal",     "default"),
    "AgentRunFinished":  JournalSchemaMeta("required",    "auditor",    "internal",     "default"),
    "StepTextDelta":     JournalSchemaMeta("best_effort", "end_user",   "public",       "short"),
    "ReasoningDelta":    JournalSchemaMeta("best_effort", "operator",   "confidential", "short"),
    "ReasoningCompleted":JournalSchemaMeta("best_effort", "operator",   "confidential", "short"),
    "RunActivity":       JournalSchemaMeta("best_effort", "end_user",   "public",       "short"),
    "ToolInvoked":       JournalSchemaMeta("required",    "operator",   "internal",     "default"),
    "ToolDenied":        JournalSchemaMeta("required",    "auditor",    "internal",     "default"),
    "LlmCallCompleted":  JournalSchemaMeta("required",    "operator",   "internal",     "default"),
    "DelegationIssued":  JournalSchemaMeta("required",    "auditor",    "internal",     "default"),
    "DelegationCompleted":JournalSchemaMeta("required",   "auditor",    "internal",     "default"),
    "DecisionMade":      JournalSchemaMeta("required",    "operator",   "internal",     "default"),
    "RunInsight":        JournalSchemaMeta("best_effort", "operator",   "internal",     "default"),
    "CastingCompleted":  JournalSchemaMeta("required",    "auditor",    "internal",     "default"),
    # ... 其余事件逐一声明
}
```

**实现含义**：
- `RunStore.append()` 查 `JOURNAL_CATALOG_META` 获取 durability
- `best_effort` 事件的 subscriber 持久化失败降级为 warning，不记入丢弃计数
- `required` 事件的 JsonlBackend 写入失败记入丢弃计数 + 告警
- `audience=restricted` 的事件（`ReasoningDelta`）默认不进 SSE live 帧
- `audience=end_user` 的事件才能进入 LobeHub LiveTail

### 三、Event Envelope —— 4 字段核心 + scope 盖章（保留现有设计）

```python
@dataclass(frozen=True)
class StampedEvent:
    """最小 envelope：seq + ts + scope + event。

    seq 和 ts 是基础设施关注点（写入时分配）。
    scope 是关联骨架（写入时从 RunHandle / ContextVar 盖章）。
    event 是领域载荷（调用方提供）。

    不在 envelope 上放的：
    - event_id (UUID)：未来 multi-worker 时再加，当前单进程不需要
    - correlation_id / causation_id：在 payload 或 scope 中按需携带
    - durability / audience / sensitivity：schema 级元数据，在 catalog 声明（N5 + N6）
    - manifest_hash：Phase 2 作为 scope 扩展引入
    """
    seq: int
    ts: float
    scope: RunScope
    event: JournalEvent
```

**设计原则**：envelope 只承载**写入基础设施**需要的信息。领域关联（correlation、causation、delegation）在 `RunScope` 中按需盖章。分类信息（durability、audience、sensitivity）在 schema catalog 中声明，不在每条记录上重复。

**渐进演进路径**：当引入多 worker / Effect Ledger 时，envelope 可扩展为：

```
@dataclass(frozen=True)
class EventEnvelope:  # 未来，非本 ADR 范围
    event_id: str          # UUIDv7，全局唯一
    schema_version: str    # e.g. "1.0"
    occurred_at: float     # 事件源认为的发生时刻
    observed_at: float     # 平台接收/观察到它的时刻
    seq: int
    scope: RunScope
    event: JournalEvent
```

`occurred_at` 与 `observed_at` 并存是 Manus 指南的关键洞察：二者的偏差是识别时钟漂移、离线缓存和延迟采集的基础。当前 `StampedEvent.ts` 等价于 `observed_at`；`occurred_at` 在单进程场景下可认为相等。

### 四、Post-commit 订阅 —— 观察者不再在写入路径中（不变量 N1, N4）

**Subscriber 接口**（沿用 `JournalProjector` Protocol，语义从「被 push 的投影器」变为「被通知的订阅者」）：

```python
class JournalProjector(Protocol):
    """Post-commit 订阅者。通知失败不影响 log。"""
    def on_event(self, stamped: StampedEvent) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
```

Protocol 签名不变，但**语义契约变了**：`on_event` 不再是「engine 推给你」，而是「你已经错过 commit 了，这是通知」。

**`_IsolatedProjector` 重命名为 `_IsolatedSubscriber`**（语义对齐，代码结构不变）：

```python
class _IsolatedSubscriber(JournalProjector):
    """故障隔离包装：subscriber 异常只记日志，永不向上传播。"""

    def __init__(self, inner: JournalProjector) -> None:
        self._inner = inner

    @property
    def inner(self) -> JournalProjector:
        return self._inner

    def on_event(self, stamped: StampedEvent) -> None:
        try:
            self._inner.on_event(stamped)
        except Exception:
            _log.warning(
                "journal_subscriber_failed",
                subscriber=type(self._inner).__name__,
                event_type=type(stamped.event).__name__,
            )

    def flush(self) -> None: ...
    def close(self) -> None: ...
```

### 五、Run State Reducer —— 纯函数推导终态（不变量 N3）

```python
@dataclass(frozen=True)
class RunState:
    """Run 的派生状态——纯函数 fold(events) 的结果。"""
    status: RunStatus  # running | completed | failed | canceled | waiting_input
    finished_at: float | None = None
    error: str | None = None

def fold_run_state(events: Sequence[StampedEvent]) -> RunState:
    """从事件流推导 run 终态。纯函数，无 I/O。

    规则（按优先级）：
    1. 存在 AgentRunFinished(status=error) 且无 parent_run_id → failed
    2. 存在 TeamRunFinished → 其 status 即终态
    3. 存在 AgentRunFinished 且 parent_run_id is None → completed
    4. 否则 → running
    """
```

**取代的代码**：
- `_write_terminal_status()` —— 不再独立写 status，由 reducer 推导
- `DshJournalProjector.finish()` —— 不再由 projector 写终态，由 driver 通过 `append(AgentRunFinished(...))` 写入
- `RunSession.status` 的直接赋值 —— 改为 `session.status = fold_run_state(hub.store.events).status`

### 六、单一终态写入点 —— 消灭双 owner

**问题根源**：DSH 路径有两个终态写入点：

1. `execute_dsh_session()` 的 `finally` → `projector.finish(status=...)` → `FacadeJournalSink.emit(AgentRunFinished)`
2. `execute.py` 的 `finalize()` → `_write_terminal_status(session, success)` → 直接设置 `session.status`

两者独立判断 status，可漂移。

**修复**：

```python
async def execute_dsh_session(session: RunSession) -> None:
    """DSH driver。终态通过 append 写入，不通过 projector.finish。"""
    ...
    # 在 execute 完成后：
    final_status = "failed" if session.error else "completed"
    hub.store.append(AgentRunFinished(
        status=final_status,
        output_text=result.final_response if result else "",
        steps=...,
        error=session.error or "",
    ))
    # 不再调用 projector.finish()

async def finalize(session, registry, workspace, success):
    """唯一的 teardown。终态从 journal 推导，不另外写。"""
    try:
        if session.hub is not None:
            _emit_artifact_closure_if_needed(workspace, session, session.hub)
        await finalize_run(session.run_id)
    except Exception:
        _log.exception(...)
    finally:
        try:
            if session.hub is not None:
                session.hub.release()
        finally:
            # 终态从 journal 推导——不再独立写 status
            if session.hub is not None:
                derived = fold_run_state(session.hub.store.events)
                session.status = derived.status
            else:
                _write_terminal_status(session, success)  # fallback: hub 不存在时
            session.closed_at = time.time()
            registry.clear_inflight(session.run_id)
            registry.prune()
            _record_doctor(session)
            if session.hub is not None:
                await _dispose_export(session.hub)
```

### 七、InsightEngine —— 从 fan-out 回写者变为普通 subscriber（不变量 N4）

**当前问题**：`InsightEngine` 在 fan-out 路径中通过 `drain_followups()` 回写 `RunInsight`。这违反了「投影器只读」原则。

**修复**：InsightEngine 变为普通的 post-commit subscriber。在收到 finish 事件时分析已聚合的事件流，产出的 `RunInsight` 通过 `store.append()` 正常写入——与任何其他事件走同一路径。

```python
class InsightEngine(JournalProjector):
    """Post-commit subscriber：聚合事件，收尾时产出 insight。

    不再通过 drain_followups 回写。改为在收到 finish 事件时
    直接调用 store.append(RunInsight(...))。
    装配顺序须 insight 先于 otel/console，保证洞察在 run span 关闭前注入。
    """

    def __init__(self, store: RunStore) -> None:
        self._store = store
        self._summaries: dict[str, dict] = {}

    def on_event(self, stamped: StampedEvent) -> None:
        event = stamped.event
        if isinstance(event, RunInsight):
            return  # 防自激
        self._aggregate(stamped, event)
        if self._is_finish(stamped, event):
            self._emit_insights(stamped)

    def _emit_insights(self, stamped: StampedEvent) -> None:
        trace_id = stamped.scope.trace_id or "(unknown)"
        summary = self._summaries.pop(trace_id, None)
        if summary is None:
            return
        for kind, message, detail in insight_rules.run_all_rules(summary):
            self._store.append(RunInsight(kind=kind, summary=message, detail=detail))
```

**`drain_followups` 路径删除**。`ExecutionJournal._emit_followups()` 不再需要。

### 八、RunHandle —— 显式传递替代 ContextVar

**问题**：DSH 在子线程 + 新 event loop 中运行，`ContextVar` 传播不可靠，导致主 journal 0 字节（P0）。当前 workaround 是 `FacadeJournalSink` 接受显式 `hub` 参数。

**根本修复**：引入 `RunHandle`，在 run 边界构造，显式传递到所有需要写入的组件。

```python
@dataclass(frozen=True)
class RunHandle:
    """Run 的执行上下文——显式传递，不依赖 ContextVar。

    DSH 跨线程 ContextVar 丢失的根因是 ContextVar 绑定到 event loop。
    RunHandle 是普通对象引用，可安全跨线程/跨 loop 传递。
    """
    run_id: str
    trace_id: str
    scope: RunScope
    store: RunStore  # 显式持有 store 引用
```

**ContextVar 保留为便利层**：主线程的 `facade.record()` 仍通过 ContextVar 获取当前 hub/store（因为主线程传播没问题）。但**任何可能跨线程的写入必须使用显式 RunHandle**。

### 九、DSH 边界 —— 从 observability 子树迁出

当前 `lca/layer0_infra/dsh/` 与 `observability/journal/` 并列，暗示 DSH 是可观测性组件。实际 DSH 是 **execution driver**。

```
目标布局（渐进迁移）：

lca/layer0_infra/
  observability/
    journal/
      engine.py          → RunStore（重命名）
      jsonl_projector.py → post-commit subscriber（语义更新）
      insight_engine.py  → 普通 subscriber（去 drain_followups）
      sse_frames.py      → 不变
    policy.py            → 不变
    hub.py               → ObservabilityHub（store 替代 journal 属性名）

  adapters/
    drivers/
      dsh/
        projector.py     → DshFolder（纯函数 fold）
        archive.py       → 不变
        sink.py          → HandleJournalSink（显式 RunHandle）
        mapping.py       → 不变
        models.py        → 不变
```

**Phase 0 不做目录迁移**——只修代码路径。目录迁移在 Phase 3（当 DshJournalProjector 重构为 DshFolder 时一并迁移）。

### 十、Schema 演进纪律

当前 `JOURNAL_EVENT_CLASSES` + `JOURNAL_CATALOG` 提供了词表治理，但缺少版本和兼容性规则。借鉴 Manus 指南的三层 Schema 规范：

| 层级 | 变更节奏 | LCA 示例 | 规则 |
|---|---|---|---|
| **核心信封** | 极慢 | `StampedEvent`（seq/ts/scope/event） | 只允许架构变更流程修改 |
| **领域语义** | 中等 | `JournalEvent` 子类、`RunScope` | 新增字段必须可选（向后兼容）；删除字段须弃用期 |
| **分类元数据** | 较快 | `JournalSchemaMeta` | 声明式，不影响运行时行为 |

**兼容性规则**：
- **向后兼容**：新增可选字段 → 同一版本可接受
- **可转换变更**：字段重命名 → 提供双写期，记录转换版本
- **破坏性变更**：类型变更、语义完全改变 → 新事件名 + 弃用期
- **非法变更**：将敏感原文加入公开事件 → 阻断发布，必须经过数据策略审批

### 十一、内容载荷分离原则

Prompt、模型输出、工具参数可能包含敏感信息。借鉴 Manus 指南的数据最小化原则：

| 数据类型 | 事件字段中保留 | 原始内容处理 | 默认保留 |
|---|---|---|---|
| 认证信息、密钥、Cookie | 绝不保留，仅记录检测/拒绝结果 | `AttributePolicy.sanitize()` 不可逆脱敏 | 0 天 |
| Prompt / 输出文本 | 长度、摘要、哈希（`output_truncated`） | `journal_kind=content` 字段受 `_CONTENT_STR_MAX` 截断 | 随 run 保留期 |
| 工具参数 / 返回体 | `arguments_preview`（截断）、`plugin_state`（UI 一等字段） | 敏感字段由 `AttributePolicy` 脱敏 | 随 run 保留期 |

**当前代码已部分实现**：`AttributePolicy.prepare_content()` 做 50k 字符安全截断，`sanitize()` 做密钥正则替换。本 ADR 不改变这些机制，但明确其原则：**结构事件可以广泛用于运维，原始内容只在明确用途、明确授权、明确期限下保留**。

### 十二、明确不做的事

| 不做 | 原因 | 何时重新审视 |
|---|---|---|
| RunController 中心化实体 | 仲裁应内嵌于 RunStore.append 的原子性，不应提升为独立 god object | 多 worker / 多进程写入时 |
| Effect Ledger / Outbox | 独立关注点，与本 ADR 的日志架构正交 | ADR-0056 |
| 15 字段 EventEnvelope | 在 envelope 上叠加领域语义是过度设计；4 字段 + scope 盖章已覆盖当前需求 | 多 worker + 跨进程关联时按需加字段 |
| Recovery Worker | 当前单进程单 run，崩溃即终止，不需要 lease / fencing | 多 worker 持久化时 |
| Postgres RunStore backend | 当前 JSONL + 内存已满足单节点需求 | 多 worker / 持久化需求出现时 |
| Snapshot + Tail SSE | 当前 LiveTail 的 per-run seq 够用 | 前端需要断线重连无丢失时 |
| ExecutionManifest 固化 | 当前配置不频繁变化，hash 开销大于收益 | 配置谱系成为审计需求时 |
| record_class 枚举（Fact/Command/Observation） | schema catalog 的 durability + audience 已覆盖分类需求，增加一层枚举是冗余 | 需要 API 级类型区分时 |
| command candidate 间接层 | Insight 直接 append 即可，不需要「提议 → 裁决」的间接路径 | 多 writer 竞争时需要仲裁策略时 |
| 持久事件流（Kafka/Pulsar） | 当前单进程规模，内存 + JSONL 足够 | 多 worker / 跨进程事件路由时 |
| Schema Registry 服务 | 当前 `JOURNAL_CATALOG` 内存注册 + CI 守卫足够 | 多团队/多仓库事件生产时 |
| W3C Trace Context 传播 | 当前单进程，OTel 内部传播够用 | 跨服务/跨进程 trace 传播时 |

### 十三、SSE 演进（渐进，不破坏 run-live.md）

当前 `LiveTail` 是 RunStore 的 subscriber，`stamped_to_sse_frame()` 将事件转为 SSE frame。本 ADR 不改变 SSE 协议，只改变 LiveTail 的接入方式：

```
现有：ExecutionJournal → fan-out → LiveTail.on_event(stamped)
目标：RunStore → post-commit notify → LiveTail.on_event(stamped)
```

`Last-Event-ID` 对齐 `StampedEvent.seq`（当前已是如此，本 ADR 明确此为契约）。

`audience` 分类驱动 SSE 过滤：`audience=restricted` 的事件（如 `ReasoningDelta`）默认不进 SSE live 帧；`audience=end_user` 的事件才推送。这取代了当前在 `stamped_to_sse_frame()` 中硬编码的 `redact` 逻辑。

### 十四、OTel 投影

`OtelProjector` 变为 RunStore 的 subscriber。不变量 N1 保证：OTel 看到的事件一定已经在 log 中。OTel 是**交换格式**，不是第二真相（ADR-0037 §一已确立，本 ADR 加强写入保证）。

## 后果

### 正面

- **N1 保证**：subscriber 永不可见未提交事件。注入持久化失败 → SSE 无帧 → 正确。
- **N3 保证**：run status 永远与 journal 一致。不存在「journal 说 completed，session 说 failed」的漂移。
- **N4 保证**：subscriber 是纯读者。InsightEngine 的回写走正常 append 路径，因果链清晰。
- **N6 保证**：数据分类在 catalog 声明，驱动投递保证、SSE 过滤和保留策略，不靠各 projector 重复 `if isinstance`。
- **P0 修复**：显式 RunHandle 消除 DSH 跨线程 ContextVar 丢失。
- **向后兼容**：`JournalProjector` Protocol 签名不变，现有 projector 实现只需改名为 subscriber 语义。`ExecutionJournal` 保留为别名，渐进迁移。
- **认知负荷降低**：4 字段 envelope + catalog 声明式元数据，比 15 字段 envelope + 实例级分类字段更简洁。

### 负面

- `drain_followups` 路径删除需要 InsightEngine 重写（小，~30 行）。
- `_write_terminal_status` 被 `fold_run_state` 替代，需要确保 reducer 覆盖所有终态路径（测试保证）。
- `DshJournalProjector.finish()` 删除后，DSH 终态写入路径需要重构为 `store.append(AgentRunFinished(...))`（已在 execute_dsh_session 中控制）。
- `JOURNAL_CATALOG_META` 需要为所有 29 个事件逐一声明分类元数据（一次性工作，约 60 行）。

### 风险

- `fold_run_state` 必须覆盖所有事件组合——遗漏会导致 run 卡在 `running`。通过 property-based test 穷举事件序列验证。
- Post-commit 通知的 subscriber 失败只记 log——可能丢失 SSE 帧。当前 LiveTail 已无重连机制，需后续 ADR 补 snapshot+tail。
- Schema 兼容性规则当前靠人工约定，无 CI 自动检测。未来需引入 schema 兼容性 CI 守卫。
- `RunStore._events` 内存无界增长——所有事件在 hub 生命周期内全量保留于内存。对于长时间运行的 gateway（多 run 并发），这是生产级内存风险。Phase 1 实施时须评估是否需要引入 bounded ring buffer 或 per-run 释放策略（run 终结后释放非活跃 run 的事件列表）。

## 分阶段实施

### Phase 0 — 止血（不改架构，只修正确性）

**目标**：消灭 P0 bug，不改数据流。

- [x] `FacadeJournalSink` 显式 hub 传递（**已完成**）
- [ ] **单一 finish owner**：删除 `DshJournalProjector.finish()` 中的终态写入；DSH 终态只在 `execute_dsh_session()` 中通过 `hub.journal.record(AgentRunFinished(...))` 写入
- [ ] `_write_terminal_status()` 改为**读取 journal 最后一个 finish 事件**推导 status（最小改动版 fold_run_state）
- [ ] `DshJournalProjector` 在 DSH 线程中使用显式 sink（不依赖 ContextVar）

**验收**：
- DSH fixture 主 journal 非空
- 双退出路径只产生一个 `AgentRunFinished`
- `session.status` 与 journal 最后一个 finish 事件的 status 一致

### Phase 1 — RunStore + post-commit（核心重构）

**目标**：`ExecutionJournal` → `RunStore`，建立 commit-before-observe 不变量。

- [ ] `ExecutionJournal` 重命名为 `RunStore`，`record()` 别名为 `append()`
- [ ] 明确 commit boundary：`_events.append` 和 subscriber 通知之间是 commit 点
- [ ] `JsonlJournalProjector` 语义从 fan-out 成员变为 post-commit subscriber（代码不变，语义文档化）
- [ ] `_IsolatedProjector` 重命名为 `_IsolatedSubscriber`
- [ ] 注入持久化失败测试：mock JsonlBackend 抛异常 → append 成功 → SSE frame 正常发出（Jsonl 失败不阻塞）
- [ ] 新增 `read_from(after_seq)` 方法
- [ ] `ObservabilityHub.journal` 属性别名为 `hub.store`

**验收**：
- 现有全量测试通过
- 新增测试：持久化失败 → append 返回值正常 → subscriber 通知正常
- 新增测试：`read_from(N)` 返回 seq > N 的事件

### Phase 2 — 纯函数 reducer + InsightEngine 清理 + 数据分类

**目标**：状态推导纯函数化，消除读路径回写，引入 schema 级分类。

- [ ] 实现 `fold_run_state(events) → RunState`
- [ ] `_write_terminal_status()` 替换为 `fold_run_state` 调用
- [ ] `InsightEngine` 接受 `store` 引用，`drain_followups` 路径删除
- [ ] InsightEngine 的 `_emit_insights` 直接 `store.append(RunInsight(...))`
- [ ] `ExecutionJournal._emit_followups()` 删除
- [ ] 引入 `JournalSchemaMeta`，为所有事件声明 `durability` / `audience` / `sensitivity`
- [ ] SSE 投影按 `audience` 过滤（取代硬编码 redact）

**验收**：
- 全量测试通过
- 新增测试：`fold_run_state` property-based（随机事件序列 → 终态一致性）
- 新增测试：InsightEngine 不通过 drain 路径写入
- 新增测试：每个已登记事件有 `JournalSchemaMeta` 声明

### Phase 3 — RunHandle + DSH 迁移

**目标**：显式上下文传递，DSH 归位。

- [ ] 引入 `RunHandle` dataclass
- [ ] `HandleJournalSink` 替代 `FacadeJournalSink`（显式 store 引用）
- [ ] `lca/layer0_infra/dsh/` 迁至 `lca/layer0_infra/adapters/drivers/dsh/`
- [ ] `DshJournalProjector` 重命名为 `DshFolder`（纯函数 fold 语义）

**验收**：
- DSH 跨线程零 ContextVar 依赖
- `import lca.layer0_infra.dsh` 有 deprecation warning 指向新路径
- lint-imports 通过

## 架构检验清单

借鉴 Manus 指南的优雅性检验问题，适配 LCA 当前规模：

| 检验问题 | 合格答案 |
|---|---|
| 新接入一个 Agent 框架（如 AutoGen），是否需要改核心 Schema？ | 不需要；只新增 Adapter + facade.record() 调用 |
| 更换日志后端（如从 JSONL 换到 SQLite），业务代码是否需要修改？ | 不需要；只替换 JsonlBackend subscriber |
| 新增一个事件字段，会不会破坏 SSE 帧？ | 不会；字段是可选的，SSE 投影按需取 |
| 发生下游故障时，能否解释哪些事件会丢？ | 可以；best_effort 事件可丢，required 事件记丢弃计数 |
| 能否从一个错误回答追到所有工具调用和委派链？ | 可以；`run_id` + `parent_run_id` + `delegation_id` 因果图完整 |
| 推理原文（ReasoningDelta）是否默认出现在 SSE live 帧里？ | 不会；`audience=restricted` 事件不进 end_user 投影 |
| 平台自身故障会不会拖垮 Agent 业务？ | 不会；`_IsolatedSubscriber` 故障隔离，append 永不因 subscriber 失败而抛异常 |
| 某项新指标能否从历史事实重算？ | 可以；`events()` 返回完整事件流，`fold_run_state` 可重放 |

## 相关

- **取代**：ADR-0037 的实现路径（保留 Journal-as-Truth 哲学，升级写入架构）
- **保持**：ADR-0015（contracts 无行为类）、ADR-0030（领域语言）、ADR-0034（封闭团队）、ADR-0038（LLM stream event contract）、ADR-0045（canonical intent shape）
- **借鉴**：
  - DSH Harness Session/Persistence（append-only + post-commit + pure function derive）
  - EventStore（expected-version CAS）
  - Temporal（history as truth, state as replay）
  - Kafka（consumer-managed offset）
  - OpenTelemetry Logs Data Model（Resource vs Attributes 边界、occurred_at vs observed_at）
  - W3C Trace Context（跨服务 trace 传播标准）
  - Google Dapper（低开销、应用透明、广泛覆盖的可观测性基础设施原则）
  - OWASP Logging Cheat Sheet（数据分类、完整性、不可抵赖边界）
- **后续 ADR**：
  - ADR-0056: Effect Ledger + 幂等执行（本 ADR 明确不做）
  - ADR-0057: Snapshot + Tail SSE（断线重连无丢失）
  - ADR-0058: Recovery Worker + Attempt Lease（多 worker 时）
  - ADR-0059: Schema 兼容性 CI + 版本化契约
  - ADR-0060: 敏感载荷加密存储与访问策略
