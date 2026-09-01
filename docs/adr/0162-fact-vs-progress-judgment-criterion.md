# ADR-0162：事实 vs 进度 判别准则 + UI 实时驱动收口

## 状态

**Accepted — 2026-09-01**

由 ADR-0159 / 0160 / 0161 跨 ADR 评审发现的元问题:同一组 reviewer 在 24 小时内对"该事件是否属于事实流"做出不同裁决(ToolLifecycleEnded 落 journal ✅ / StepAdvanced 落 journal ❌),但**判别准则散落各 ADR,无统一标准**。本 ADR 给出准则 + 收口两条悬空依赖。

Refines: ADR-0063 §I6 (动态扩展不扩张核心原语)、ADR-0037 (journal-as-truth)、ADR-0156 (清退三处架构泄漏)、ADR-0157 (ToolCallStreaming 合并)

## 背景

### 1. 三个 ADR 暴露的双标

| ADR | 提议事件 | 落 journal? | 理由 |
|---|---|---|---|
| ADR-0159 | `ToolLifecycleEnded` | ✅ | 「tool 生命周期结束」是事实 |
| ADR-0159 (end_kind=NOT_INVOKED_AFTER_STREAM) | 同上 | ✅ | 同上 |
| ADR-0161 (已撤回) | `StepAdvanced` | ❌ | 「step 推进 UI 实时驱动」是进度 |
| ADR-0157 (修订) | `ToolCallStreaming` | ✅,但加 best_effort + `_delta_key` 合并 | 「live preview 既是事实也是进度,落 journal 但限合并」 |

同一原则(ADR-0063 §I6「动态扩展不扩张核心原语」)被引 4 次,结论不一致。

### 2. ADR-0063 §I6 原文

> **动态扩展不扩张核心原语**:新插件可发 `RuntimeObserved` 或新增已登记类型;不得再建立第二个 EventBus、第二条诊断序列或自建 JSONL。

§I6 关心的是**不要平行建第二个总线**,不关心**单条事件该不该入 fact 流**。这是 ADR-0159 / 0161 反复争议的根因 —— 援引的条文与争议无关。

### 3. ADR-0159 / 0161 真正在问的问题:

> **这条事件是「事实」还是「进度」?**
> - 「事实」= 入 journal,可重放,source of truth(ADR-0037)
> - 「进度」= 可丢,可重建,LiveTail/SSE 即可

## 第一性原理:三判别准则

**准则 1:用户能感知 → 事实**

事件若在用户视角可被观测到(看到、听到、读到、被打断),入 journal。

- ✅ `ToolLifecycleEnded.failed`:用户看到「工具调用 X 失败」——事实
- ✅ `ToolLifecycleEnded.cancelled`:用户(或上层)发起了 cancel——事实
- ⚠️ `ToolLifecycleEnded.not_invoked_after_stream`:用户**没看到**这次调用(占位但未落地),只看到「X 标了 X」——**存疑**
- ❌ `StepAdvanced`(撤回):用户看不到 step 数字,只感知到「正在重试 attempt 2」——进度

**准则 2:重放一致性 → 事实**

事件若影响 checkpoint 重放后的状态语义,入 journal。
- ✅ `ToolLifecycleEnded.failed` 重放后:占位仍在 + 失败事件可被读到
- ❌ `StepAdvanced` 重放后:UI 重放时 step 显示当前值即可,不需重放「每次推进」

**准则 3:成本阈值 → 进度**

事件若以高频发射且 payload 不可逆(累积式 / 实时流),即使语义上是事实,也用 `EventDurability.best_effort` + `_delta_key` 合并键。

- ✅ `ToolCallStreaming`:3800/31MB,合并键后落盘次数大幅下降;语义是事实(占位预览),但成本上是进度
- ❌ `StepTextDelta`:每字符一条,`_delta_key` 已合并;语义是进度,落盘但合并

## 决策(三个收口)

### 一、ToolLifecycleEnded.end_kind NOT_INVOKED_AFTER_STREAM 拆出独立事件(收敛双标)

**问题**:依据准则 1,`not_invoked_after_stream` 用户感知弱,混在 `ToolLifecycleEnded` 内是把「事实」和「进度」打包。

**方案**:从 `ToolLifecycleEndKind` 拆出 `not_invoked_after_stream` 为独立 `ToolAbandonedBeforeInvoke` JournalEvent,**durability = "best_effort"**(准则 3),不入 narrative sidecar(可选 metadata):

```python
@dataclass(frozen=True)
class ToolAbandonedBeforeInvoke(JournalEvent):
    """Tool 调用占位存在,但 phase 在 ToolInvoked 发射前已退出。

    end_kind 语义:用户没看到这次调用,只是占位被回收。
    落 journal 但 best_effort,不入 narrative,UI 投影可忽略。
    """

    tool_call_id: str = ""
    phase_id: str = ""
    reason: Literal["phase_retried", "phase_failed_fast", "phase_cancelled"] = "phase_retried"
```

`ToolLifecycleEnded` 仅保留三种 end_kind:`cancelled` / `failed` / `superseded`,语义收窄为「用户能感知的事实」。

### 二、UI 实时驱动走 LiveTail 订阅 best_effort 流(解决 ADR-0161 悬空依赖)

**问题**:ADR-0161 真方案引用 `progress.emit(ProgressFrame)`,但 ADR-0157 已撤销 ProgressStream Protocol —— 悬空依赖。

**方案**:**不走新 Protocol,直接复用 ADR-0157 的 `_delta_key` + LiveTail 机制**:

LobeHub 端 `lcaJournal.ts` 订阅 LiveTail best_effort 流(`LlmCallStarted` / `ToolRetryProgress`):

```typescript
// lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts
case 'tool-retry-progress':  // 来自 ADR-0157 best_effort 流
  const { attempt, of } = payload;
  baseState.retryIndicator = { attempt, of };  // UI 实时显示"重试 2/3"
  break;
```

LCA 后端 `phase_execution_policy.py` 不发新 JournalEvent,**复用 `_delta_key` 合并键** emit `ToolRetryProgress`(同一通道、合并语义、可丢):

```python
# phase_execution_policy.py 顶部 import
from lca.infrastructure.observability.facade.facade import record

# phase_execution_policy.py:PhaseExecutionRunner.execute 循环顶部
async def execute(self, ...):
    for attempt in range(1, policy.max_attempts + 1):
        # 仅 emit best_effort 增量,不动 state.step
        record(ToolRetryProgress(
            tool_call_id=last_active_tool_call_id or "",
            phase_id=node_id,
            attempt=attempt,
            of=policy.max_attempts,
        ))
        ...
```

新事件 `ToolRetryProgress` 走 ADR-0063 §I6 登记,**durability = "best_effort"**,与 ADR-0157 `ToolCallStreaming` 走同一通道(不新建总线,符合 §I6)。

### 三、ADR-0063 §I6 增补「事实 vs 进度」判别子条款

修订 `docs/adr/0063-run-trace-ssot.md` §I6 行,改为:

> **I6** | **动态扩展不扩张核心原语,新增事件需走三准则判别**
> 新插件可发 `RuntimeObserved` 或新增已登记类型;不得再建立第二个 EventBus、第二条诊断序列或自建 JSONL。新增 JournalEvent 必须回答三问:① 用户能感知? ② 重放后状态语义一致? ③ 高频低成本? 三问答案为「事实 / 事实 / 进度」任一组合即按对应语义配置(`durability` + `_delta_key` 合并)。详见 ADR-0162。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| ADR-0156 闭环 | ToolLifecycleEnded 拆 ToolAbandonedBeforeInvoke 后,事实/进度分离彻底 | 新增 1 条 JournalEvent |
| ADR-0161 闭环 | 不依赖 ProgressStream Protocol(已撤),复用 ADR-0157 best_effort 流 | 新增 1 条 JournalEvent(ToolRetryProgress) |
| ADR-0063 §I6 增补 | 三准则消除未来争议 | §I6 文案修订 |
| 总新增 JournalEvent | 2 条 | — |
| 总新增 Protocol | 0 | — |
| 总新建总线 | 0 | — |
| 跨 ADR 双标 | 消除 | — |

## 替代方案(已否决)

| 方案 | 否决理由 |
|---|---|
| 不动 ADR-0063 §I6,留各 ADR 自行判断 | 当前已证明会导致双标;不治理 |
| 重启 ProgressStream Protocol | 与 ADR-0157 减法原则冲突;与 ADR-0063 §I6「不扩张核心原语」冲突 |
| 用 `EventDurability` 单独字段,不拆事件 | 无法表达「占位未落地」的事实-进度边界 |
| 把 ToolRetryProgress 加进 ToolLifecycleEnded.end_kind | 准则 1 不通过:用户感知弱,应走 best_effort |

## 验证约束(机械可执行)

```bash
# 1. ToolAbandonedBeforeInvoke 落 journal_catalog
uv run pytest tests/contracts/test_journal_catalog_closure.py -v

# 2. ToolRetryProgress best_effort + _delta_key 合并
uv run pytest tests/observability/test_tool_retry_progress_delta_coalesce.py -v

# 3. ADR-0063 §I6 增补文案检查(grep 验证)
grep -n "三准则" docs/adr/0063-run-trace-ssot.md

# 4. phase_execution_policy 不发 state.step,只 emit ToolRetryProgress
uv run pytest tests/declarative/test_phase_retry_emits_tool_retry_progress.py -v

# 5. LobeHub 端订阅 ToolRetryProgress
cd lobehub-ui && bun test src/store/chat/agents/transports/LcaRunDriver.toolRetryProgress.test.ts

# 6. 跨 ADR 双标消解:无「同事件类同时承担事实+进度」
uv run pytest tests/contracts/test_no_dual_role_event_classes.py -v
```

## 修改清单

| 修改位置 | 修改内容 |
|---|---|
| `docs/adr/0063-run-trace-ssot.md` §I6 | 文案增补「事实 vs 进度三准则」,引用 ADR-0162 |
| `lca/contracts/models/observability/journal.py` | 新增 `ToolAbandonedBeforeInvoke` dataclass;`ToolLifecycleEndKind` 删除 `NOT_INVOKED_AFTER_STREAM` |
| `lca/contracts/models/observability/journal.py` | 新增 `ToolRetryProgress` dataclass + `ToolRetryProgressKind` StrEnum |
| `lca/contracts/models/observability/journal_catalog.py:JOURNAL_EVENT_CLASSES` | 增 ToolAbandonedBeforeInvoke + ToolRetryProgress |
| `lca/infrastructure/observability/events/event_descriptors_data.py` | 加 2 个 `_descriptor`(ToolAbandonedBeforeInvoke best_effort / ToolRetryProgress best_effort) |
| `lca/infrastructure/observability/journal/jsonl/projector.py:_delta_key` | 新增 `ToolRetryProgress` 合并键(同 ADR-0157 范式) |
| `lca/harness/declarative/compile/phase_execution_policy.py:PhaseExecutionRunner.execute` | attempt 入口 emit ToolRetryProgress,不动 state.step |
| `lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts:applyProjected` | 新增 `case 'tool-retry-progress'` |
| ADR-0159 同步修订 | `ToolLifecycleEndKind` 移除 `NOT_INVOKED_AFTER_STREAM`,迁移到 `ToolAbandonedBeforeInvoke` |

## 新增清单

2 条 JournalEvent + 1 个新增 StrEnum + ADR-0063 §I6 文案增补。

## 落地顺序

5 个 commit(顺序敏感):

1. **commit 1**:ADR-0063 §I6 文案增补(治理先行)
2. **commit 2**:`journal.py` 新增 `ToolAbandonedBeforeInvoke` + `ToolRetryProgress` + 各自 enum
4. **commit 3**:`journal_catalog.py` 注册 + `event_descriptors_data.py` 加 descriptor + `_delta_key` 增合并键
5. **commit 4**:`phase_execution_policy.py` 删 `last_tool_call_id` 旧字段(从 ADR-0159)、改 emit `ToolAbandonedBeforeInvoke`(失败路径)和 `ToolRetryProgress`(attempt 入口)
6. **commit 5**:LobeHub `applyProjected` 新增 `case 'tool-retry-progress'` + `case 'tool-abandoned-before-invoke'`(best_effort 可忽略)

每步跑相关 journal_catalog / declarative / lobehub 测试。

## 风险

- **风险 1**:ToolLifecycleEnded 删 `NOT_INVOKED_AFTER_STREAM` 是破坏性事件 schema 变更。**缓解**:在 journal_catalog 标 deprecated 警告一个版本,迁移完成后再移除。
- **风险 2**:ToolRetryProgress 走 best_effort,UI 端 LiveTail 订阅可能因客户端断网漏帧。**缓解**:LobeHub 端有 retryIndicator 兜底态(显示「正在重试…」直至 next event);本地 SSE 客户端用 `LiveGap` 协议提示缺失(已有 seam)。
- **风险 3**:ADR-0063 §I6 文案增补可能让现有 ADR 在新准则下重新判定。**缓解**:本 ADR 不追溯,仅治理未来新增事件;现有事件保持原状。
- **风险 4**:三准则的「用户能感知」判定主观。**缓解**:每条新事件登记时显式回答三问并写入 ADR「新增清单」段,作为可审计的判例。

## 与其他 ADR 的对齐

| ADR | 对齐 |
|---|---|
| ADR-0156 | ToolLifecycleEnded 拆 ToolAbandonedBeforeInvoke 兑现「事实/进度分离」 |
| ADR-0157 | ToolRetryProgress 复用 `_delta_key` 合并 + best_effort,通道不增加 |
| ADR-0158 | 不涉及;独立 |
| ADR-0159 | ToolLifecycleEnded 收窄;`NOT_INVOKED_AFTER_STREAM` 迁出 |
| ADR-0160 | 不涉及;独立 |
| ADR-0161 | 撤销的修复被收口到 ToolRetryProgress best_effort 流,UI 实时驱动闭环 |
| ADR-0063 §I6 | 文案增补,引用本 ADR |
| ADR-0069 §G3 | factsensor 职责更清晰:事实 vs 进度的判别由三准则承担 |
| ADR-0075 | phase graph 退出语义更精确:`failed` / `cancelled` 入事实,`abandoned` 入 best_effort |

## 历史

- **2026-09-01 v1**:本文初版,基于 ADR-0159/0160/0161 跨评审共识。