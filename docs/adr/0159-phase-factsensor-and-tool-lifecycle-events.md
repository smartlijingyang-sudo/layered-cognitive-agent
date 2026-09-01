# ADR-0159：ToolLifecycleEnded 单事件 + phase_execution_policy 内联收口

## 状态

**Revised v2 — 2026-09-01**(第二轮 subagent 评审发现 v1 仍有 3 处设计缺陷，本版本全部纠正)

- **v1 → v2 修正 1**：end_kind 由 `str` 改为 `ToolLifecycleEndKind` StrEnum(领域语义必须使用枚举,AGENTS.md §5)
- **v1 → v2 修正 2**：命名漂移 `last_known_tool_call_id` / `last_tool_call_id` 统一为 `last_tool_call_id`
- **v1 → v2 修正 3**：`from lca.infrastructure.observability.facade import record` 改为真实路径 `from lca.infrastructure.observability.facade.facade import record`,并在 docstring 写明 lazy import 的循环依赖理由

Supersedes: ADR-0156 §「决策 三」 / ADR-0159 v1

Refines: ADR-0063 §I6 (动态扩展不扩张核心原语)、ADR-0069 G3 (Facts / State / Knowledge)、ADR-0075 (Phase Graph 退出语义)

## 背景

`run_b1294a33e55d` RCA 暴露 phase 退出时 `ToolCallStreaming` 占位无收口事件:
- LobeHub `tool-start` case 创建占位,但 phase 失败时 `tool-invoked` 永远不来,spinner 不收敛
- 工具标题 `description` 缺失(无 `ToolStarted.arguments.description`),UI 显示 `shinyText` 占位

## 第一性原理:为什么不需要 PhaseFactsensor Protocol

subagent 评审发现关键事实:

1. **`interpreter.py` 根本没有 `_exit_phase` 方法**(全文 grep 0 命中):
   - 现有 phase 退出在 `_drive` 内有 3 条路径(成功终止 / 治理终止 / 异常),但都是"phase result → outcome"两步
   - **所谓"phase 退出事件"中间环节根本不存在**

2. **`recovery.py:39-66` 不是反弹逻辑,是 Pydantic 配置**:
   - 是 `@plugin` 装饰器 + `RecoveryLoopConfig` 配置类
   - 真正反弹由 `reflect.py:88` 写 `admit_recovery: True` 触发

3. **重试真实路径在 `phase_execution_policy.py:60-110`**:
   - `PhaseExecutionRunner.execute` 的 for 循环
   - 已有 `execute_with_policy` (:159-179) 是 phase 退出 seam

4. **delegation / approval / reasoning_delta 没有"占位无收口"**:
   - `DelegationIssued` / `ApprovalRequested` 是成对生命周期事件,无流式中间状态
   - `ReasoningDelta` 有 `ReasoningCompleted` 自然收口
   - **唯一真有"占位无收口"的是 ToolCallStreaming + 无 ToolInvoked**

5. **`OpenSlot` / OpenSlotRegistry / factsensor 默认实现仅覆盖 tool_call**:
   - ADR 自承"其他类型 plugin 实现"
   - **"通用 seam"是臆想的统一性,实际不需要**

## 原方案错在哪里

ADR-0159 v1 错误地:

- 引用 G4 范畴作为 factsensor 的宪法依据——**G4 原文是"Perception & Grounding"**,与"fold 占位为结束事件"无关(同作者在 ADR-0161 自承 G3 才是 factsensor 归属)
- 拆分 ToolCancelled / ToolFailed 两个事件——单事件 `ToolLifecycleEnded` + payload `end_kind` 完全够
- 新建 PhaseFactsensor Protocol + ToolCallPhaseFactsensor 默认实现——三处集成会双发
- 引用 `_collect_open_slots_from_failure` 兜底——`PhaseExecutionExhaustedError.failure` 不含 `last_tool_call_id`,**承认现有 phase failure 路径没存占位快照**
- 声称要"取消通用 seam 覆盖 delegation/approval/reasoning_delta"——**这三类根本不存在占位问题**

总计 4 个新文件、零行为改善、引入双发风险。

## 决策(单事件 + 内联)

### 一、新增 ToolLifecycleEndKind 枚举(领域语义)

`lca/contracts/models/observability/journal.py` 与 `ToolLifecycleEnded` 同一文件新增:

```python
class ToolLifecycleEndKind(str, Enum):
    """Tool 调用生命周期终结原因。

    NOT_INVOKED_AFTER_STREAM 已在 ADR-0162 收窄中迁出至独立
    ToolAbandonedBeforeInvoke 事件(用户感知弱,best_effort 流)。
    本枚举仅保留「用户能感知」的三类终结。
    """

    CANCELLED = "cancelled"
    FAILED = "failed"
    SUPERSEDED = "superseded"
```

枚举优先于裸字符串:AGENTS.md §5「领域语义必须使用枚举」。

### 二、新增 ToolLifecycleEnded 单事件(C1 闭集登记)

`lca/contracts/models/observability/journal.py` 新增:

```python
@dataclass(frozen=True)
class ToolLifecycleEnded(JournalEvent):
    """Tool 调用生命周期终结(事实)。

    仅在 phase 退出时,phase_execution_policy 已尝试但 ToolInvoked 未能落地
    的情况下发射。配合 ADR-0157 的 _delta_key 合并,ToolCallStreaming 占位
    在 journal 中即可被收口。
    """

    tool_call_id: str = ""
    end_kind: ToolLifecycleEndKind = ToolLifecycleEndKind.FAILED
    error: str = ""
    phase_id: str = ""
```

> **注**:phase 重试期间 `not_invoked_after_stream` 类的「占位已回收但用户没感知」事件,按 [ADR-0162](0162-fact-vs-progress-judgment-criterion.md) 三准则收口到 `ToolAbandonedBeforeInvoke`(`durability="best_effort"`)。本事件保持「用户能感知的事实」语义,枚举收窄为 3 种 end_kind。

`lca/contracts/models/observability/journal_catalog.py:JOURNAL_EVENT_CLASSES` 注册。

`lca/infrastructure/observability/events/event_descriptors_data.py` 加 `_descriptor(...)`:

```python
_descriptor(
    ToolLifecycleEnded,
    domain=VocabDomain.RESOURCE,
    emitter="lca.harness.declarative.compile.phase_execution_policy",
    required=("tool_call_id", "end_kind", "phase_id"),
    description="Tool call lifecycle ended without completion",
    durability="required",
    audience="end_user",
    sensitivity="public",
)
```

**闭集走 ADR-0063 §I6 + ADR-0069 §治理门禁流程**(本 ADR 即登记)。

### 三、`phase_execution_policy.py` 内联 5 行 emit

**import 处理**:`facade.facade.record()` 是 no-op safe(journal 未 bound 返回 None),与 `phase_execution_policy` 无循环依赖;**直接顶层 import**:

```python
# phase_execution_policy.py 顶部新增
from lca.infrastructure.observability.facade.facade import record
```

```python
# phase_execution_policy.py:_phase_error_result(失败路径)
async def _phase_error_result(self, *, node_id, failure, last_tool_call_id):
    if last_tool_call_id is not None:
        record(ToolLifecycleEnded(
            tool_call_id=last_tool_call_id,
            end_kind=ToolLifecycleEndKind.FAILED,
            error=str(failure.attempts[-1].error_type) if failure.attempts else "phase_failed",
            phase_id=node_id,
        ))
    return PhaseResult(result_kind="phase_error", ...)
```

```python
# phase_execution_policy.py:CancelledError 分支(取消路径)
except asyncio.CancelledError:
    if last_tool_call_id is not None:
        record(ToolLifecycleEnded(
            tool_call_id=last_tool_call_id,
            end_kind=ToolLifecycleEndKind.CANCELLED,
            error="phase_cancelled",
            phase_id=node_id,
        ))
    raise
```

`last_tool_call_id` 由 `PhaseExecutionFailure` 扩展字段(增加 `last_tool_call_id: str | None = None`),由 `PhaseExecutionRunner` 在每次 `attempt` 后从 `tool_slots` 注册表读取并写入 failure。

### 四、LobeHub `applyProjected` 新增单 case

`lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts:applyProjected`:

```typescript
// 端到端契约:ToolLifecycleEnded.end_kind 序列化为字符串,与 ToolLifecycleEndKind 字面量保持一致
type ToolLifecycleEndKindPayload =
  | 'cancelled'
  | 'failed'
  | 'not_invoked_after_stream'
  | 'superseded';

case 'tool-lifecycle-ended':
  const endKind = payload.end_kind as ToolLifecycleEndKindPayload;
  if (endKind === 'cancelled' || endKind === 'failed') {
    dispatchMessage({
      ...baseState,
      status: 'failed',
      error: payload.error,
    });
  }
  break;
```

### 五、PhaseExecutionFailure 扩展字段

`lca/harness/declarative/compile/phase_execution_policy.py:PhaseExecutionFailure` 新增字段:

```python
@dataclass(frozen=True)
class PhaseExecutionFailure:
    node_id: str
    attempts: tuple[PhaseAttemptFailure, ...]
    last_tool_call_id: str | None = None  # ← 新增
```

由 `PhaseExecutionRunner` 在每次 attempt 失败时,从当前 phase 的 `tool_slots` registry 取最近活跃的 `tool_call_id`(executor 已维护 `tool_slots: dict`,直接复用)。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| ADR-0063 §I6 兑现 | 新增1 条闭集事件(走登记流程);不污染 envelope | ToolLifecycleEnded 需登记 + EventDescriptor + 测试 |
| ADR-0069 G3 落实 | 事实层 fold 占位为结束事件 | — |
| phase 收口 | 单点(`phase_execution_policy.py`)emitsingle 事件,无双发 | — |
| LobeHub spinner | 占位在 phase 失败时有终止事件 | `applyProjected` 新增 case |
| **新增代码量** | **~32 行**(新事件 + 枚举 17 行 + 内联 10 行 + LobeHub 5 行) | — |
| **新增 Protocol** | **0** | — |
| **新增 Plugin** | **0** | — |
| **新增 OpenSlot 类** | **0** | — |
| **多点集成双发** | **不存在** | — |
| **命名一致性** | end_kind 与 last_tool_call_id 全栈统一(v1 有 `last_known_tool_call_id` 漂移) | 强制类型为枚举,前端用 payload union 类型 |
| **import 真实性** | `from lca.infrastructure.observability.facade.facade import record` | v1 路径 `lca.infrastructure.observability.facade` 不存在 |

## 替代方案(已否决)

| 方案 | 否决理由 |
|---|---|
| 新建 PhaseFactsensor Protocol + ToolCallPhaseFactsensor 默认实现 | 过度工程;同一职责在 phase_execution_policy.py 5 行内闭合 |
| 拆 ToolCancelled + ToolFailed 两个事件 | 单事件 + end_kind payload 完全够;LobeHub switch 一处分发 |
| OpenSlot / OpenSlotRegistry 抽象 | 占位 ID 已在 journal(ToolCallStreaming.tool_call_id);TraceInspector 重放即可,无需新数据结构 |
| 引用 ADR-0069 G4 作为 factsensor 依据 | G4 原文是 Perception & Grounding;G3 才是 factsensor 归属(同作者 ADR-0161 自承) |
| end_kind 用 `str` 而非 StrEnum | 违反 AGENTS.md §5「领域语义必须使用枚举」;失去类型守卫 |
| 在 phase_execution_policy.py 顶层 import facade.facade | 触发循环依赖(phase_execution_policy 在 harness boot 早期 import,run_context 尚未就绪) |

## 验证约束(机械可执行)

```bash
# 1. journal_catalog 含 ToolLifecycleEnded
uv run pytest tests/contracts/test_journal_catalog_closure.py -v

# 2. phase 失败时 ToolLifecycleEnded 必出
uv run pytest tests/declarative/test_phase_retry_emits_tool_lifecycle.py -v

# 3. phase 取消时 ToolLifecycleEnded 必出
uv run pytest tests/declarative/test_phase_cancel_emits_tool_lifecycle.py -v

# 4. ToolLifecycleEnded 走 EventDescriptor 完整登记
uv run pytest tests/observability/test_event_descriptor_tool_lifecycle.py -v

# 5. LobeHub tool-lifecycle-ended case
cd lobehub-ui && bun test src/store/chat/agents/transports/LcaRunDriver.toolLifecycle.test.ts

# 6. PhaseExecutionFailure 含 last_tool_call_id
uv run pytest tests/declarative/test_phase_execution_failure_last_tool_call.py -v
```

## 修改清单

| 修改位置 | 修改内容 |
|---|---|
| `lca/contracts/models/observability/journal.py` | 新增 `ToolLifecycleEndKind` StrEnum + `ToolLifecycleEnded` frozen dataclass |
| `lca/contracts/models/observability/journal_catalog.py:JOURNAL_EVENT_CLASSES` | 增 ToolLifecycleEnded 登记 |
| `lca/infrastructure/observability/events/event_descriptors_data.py` | 加 `_descriptor(ToolLifecycleEnded, ...)` |
| `lca/harness/declarative/compile/phase_execution_policy.py:PhaseExecutionFailure` | 新增 `last_tool_call_id: str \| None` 字段 |
| `lca/harness/declarative/compile/phase_execution_policy.py:_phase_error_result` | 函数级 import + 内联 5 行 emit |
| `lca/harness/declarative/compile/phase_execution_policy.py:CancelledError` 分支 | 函数级 import + 内联 5 行 emit |
| `lca/harness/declarative/compile/phase_execution_policy.py:PhaseExecutionRunner` | 每次 attempt 后更新 `last_tool_call_id` |
| `lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts:applyProjected` | 新增 `case 'tool-lifecycle-ended'` + ToolLifecycleEndKindPayload union 类型 |

## 新增清单

1 个 StrEnum + 1 条 JournalEvent + 1 个 EventDescriptor;无 Protocol / Plugin / Registry。

## 落地顺序

3 个 commit:

1. commit 1:`journal.py` 新增 `ToolLifecycleEndKind` StrEnum + `ToolLifecycleEnded` frozen dataclass + `journal_catalog.py` 注册 + `event_descriptors_data.py` 加 `_descriptor`。
2. commit 2:`PhaseExecutionFailure` 扩 `last_tool_call_id` 字段;`PhaseExecutionRunner` 每次 attempt 后写入;`_phase_error_result` 与 `CancelledError` 分支各 emit(函数级 lazy import)。
3. commit 3:LobeHub `applyProjected` 新增 `case 'tool-lifecycle-ended'` + 端到端 payload union 类型。

每步跑 `tests/contracts/test_journal_catalog_closure.py tests/declarative/test_phase_retry_emits_tool_lifecycle.py`。

## 风险

- **风险 1**:`ToolLifecycleEnded` 是 C1 闭集变更,需走 ADR-0063 §I6 + ADR-0069 §治理门禁流程。**缓解**:本 ADR 即为登记,落地时同步更新 `JOURNAL_CATALOG` 与 EventDescriptor。
- **风险 2**:`last_tool_call_id` 扩展字段需 PhaseExecutionRunner 维护 tool_slots 引用,若 executor 未来重构 tool_slots 数据结构,需同步更新。**缓解**:executor 的 `tool_slots: dict[str, dict[str, object]]` 已是稳定 seam(ADR-0066 引用)。
- **风险 3**:LobeHub `applyProjected` 现有 case 分支结构(LcaRunDriver.ts:500-655)是单 switch,新增 case 不破坏既有路径。**缓解**:`toolLifecycle.test.ts` 覆盖。