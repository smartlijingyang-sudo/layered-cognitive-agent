# ADR-0156：清退三处架构泄漏 —— facts/progress 分离、projection 隔离、phase 收口

## 状态

**Superseded by ADR-0157 / 0158 / 0159 — 2026-09-01**

ADR-0160 / 0161 因**所提议的问题根本不存在**而**撤销**(见各 ADR 「状态: Withdrawn」段)。

本文档保留作为问题陈述与 RCA 索引,**修复方案不再维护**,统一引用 ADR-0157 / 0158 / 0159。

### 引用链

| 重构段 | 独立 ADR | 评审关键发现 |
|---|---|---|
| A. ToolCallStreaming 31 MB | [ADR-0157](0157-progress-stream-and-retire-toolcallstreaming.md) | LCA 已有 `_delta_key` 合并键 + `EventDurability.best_effort`;3 行 projector 改动即可;**砍 7 个新文件**(原 ProgressStream 方案作废) |
| B. Projection 隔离 / reducer 私改 status | [ADR-0158](0158-projection-isolation-and-finalizer-cleanup.md) | reducer.py:285 删 1 行 + finalizer 调顺序 + 删 `AgentState.final_output` + 删 `Result.from_state`;**零新 Protocol**(原 ArtifactClosureProjection 方案作废) |
| C. Phase 退出 tool 占位无收口 | [ADR-0159](0159-phase-factsensor-and-tool-lifecycle-events.md) | 新增 `ToolLifecycleEnded` 单事件 + `phase_execution_policy.py` 内联 5 行;**砍 PhaseFactsensor Protocol**(原 OpenSlot / 默认实现方案作废) |
| D. LlmCall 流断流 | [ADR-0160](0160-llm-call-stream-finalize-on-exit.md) | **撤销** —— TelemetryLLMAdapter 的 try/except/finally 已闭合三条路径;`executor.py` 不直接发 LlmCallCompleted;问题诊断是错的 |
| E. Phase 重试期间 step 不递增 | [ADR-0161](0161-step-advance-on-phase-retry.md) | **撤销** —— phase_retry 不该推进 step(同一回合内重试);UI 实时驱动应走 ADR-0157 ProgressStream,不走 journal 留痕 |

### 第一性原理修订(基于 subagent 深度评审)

原 ADR-0156 的 A/B/C/D/E 五段方案,在 subagent 并行深度评审下被逐段挑战。核心发现:

| 原方案 | 真实问题 | 评审后的本质修复 |
|---|---|---|
| 新建 ProgressStream Protocol 双通道 | best-effort 语义已由 `EventDurability.best_effort` 表达 | 复用 `_delta_key` 合并键机制,3 行改动 |
| 新建 ArtifactClosureProjection Protocol | 与旧 ArtifactClosure 同语义,只是改名 | 删 reducer.py:285 一行 + 删 finalizer 折叠 |
| 新建 PhaseFactsensor Protocol + 默认实现 | interpreter.py 没有 `_exit_phase` 方法;占位 ID 已在 journal | 单一 `ToolLifecycleEnded` 事件 + phase_execution_policy.py 内联 |
| 新建 LlmCallLifecycleGuard Protocol | TelemetryLLMAdapter 已闭合;executor.py 不直接发事件 | 撤销 ADR,加 1 条不变量断言 |
| 新建 StepClock Protocol + StepAdvanced factsensor | 重试本就不该推 step;UI 实时驱动要走 ProgressStream | 撤销 ADR,走 ADR-0157 ProgressStream 通道 |

### 历史 Refines

ADR-0037（journal-as-truth）、ADR-0069（agent primitive system）、ADR-0070（reducer-as-plugin）、ADR-0075（declarative phase graph & MTK）、ADR-0077（TerminalOutcome as Sole Terminal Truth）、ADR-0063（run trace SSOT）。

Supersedes: ADR-0101 PR-2 / PR-3 关于 ToolCallStreaming 双字段并列的设计。

## 背景

2026-09-01 对 `run_b1294aab-a5e2-7a83-b349-e35174e6bd52` 的复盘暴露了 **3 个独立的架构泄漏点**。每一处都不是单一文件 bug，而是**宪法的某一层 seam 在代码中没有插件 / 协议承接**，导致下游实现以补丁形式绕过，进而累积出今日的多症状（journal 膨胀、UI 折叠错位、run failed 仍推 answer 流、tool 占位无收口、reducer 私自改 status 等）。

### 三处泄漏

| 泄漏 | 现状 | 后果 |
|---|---|---|
| **A. Progress 信号污染 Facts 流** | `ToolCallStreaming` 是 journal event（3800 条 / 31 MB），但它只是 provider 流的中转快照，不是事实 | journal 体积、narrative 淹没、UI 折叠面板错位、LobeHub 必须自行累积 `arguments_preview.code` |
| **B. Projection 偷偷写 State** | `reducer.apply_artifact_closure` 把 closure 文本塞入 `state.final_output` 并把 `status=WORKING` 改为 `COMPLETED` | reducer-as-plugin（C4）失效；TerminalOutcome 单写（ADR-0077）失效；UI 看到 `status=failed` 与 `final_output="已生成 4 张图"`并存 |
| **C. Phase 退出无 factsensor 收口** | phase 重试失败时，3800 条 ToolCallStreaming 占位没有对应 ToolCancelled/ToolFailed 收口事件 | LobeHub 不知道 tool 占位已死、spinner 不收敛、`pluginState.success` 永远 undefined、UI 显示 X |

### 错误的应对（必须避免）

把 13 个症状映射成 10 个补丁式 PR，是错的。

- 补丁 1：「把 `ToolCallStreaming.arguments_preview.code` 改成 delta」——半补丁；它修症状但**保留事件本身错位在 journal**。
- 补丁 2：「删 `apply_artifact_closure` 的 status 副作用」——半补丁；它删一行但**保留 artifact closure 仍在 reducer 流**。
- 补丁 3：「phase 退出时多发 ToolCancelled」——半补丁；它加事件但**保留 factsensor seam 缺失**。

补丁 1+2+3 都修了当前 run 的症状，但是**下一次再出现类似泄漏，仍得写补丁**。

## 第一性原理

ADR-0037 已经把核心命题定下：**journal 是事实流，projection 不可回写事实。** ADR-0075 §一 MTK 表已经明确"Reducer 唯一 State writer"、"Journal 提交边界"、"通用 Plan 解释器"是内核不变量；这些不变量靠**协议 + 插件 seam** 强制，不靠注释与约定。

**关键洞察**：

- 同一份数据有三种存在形态：facts（不可变、最小）、progress（可变、可丢、可重建）、projection（派生、视图）。三者**必须物理分离**。
- Factsensor 是 G4 范畴：把 progress 信号收口为 facts。**Phase 退出必须调 factsensor**。
- Reducer 是 state 唯一 writer。**Projection（artifact closure）不能进 reducer**。

ADR-0063 §I4 已经规定"投影永不回写"——但当前 `apply_artifact_closure` 实际把 projection 写回 state。**这是 ADR-0063 §I4 的违反，需要按本 ADR 正式清退**。

## 决策

### 一、ADR-0156-A：**双通道流 —— facts 与 progress 物理分离**

#### 1. 协议层新增 `ProgressStream`

```python
# lca/contracts/observability/progress_stream.py（新文件）
from typing import Any, AsyncIterator, Protocol
from dataclasses import dataclass

@dataclass(frozen=True)
class ProgressFrame:
    """Phase contribution 的实时进度信号。不进 journal fact 流。"""
    seq: int                              # progress-local seq,与 journal seq 独立
    scope_run_id: str
    scope_trace_id: str
    channel: str                          # "tool_arg_delta" | "reasoning" | "text" | "step" | "tool" | ...
    kind: str                             # slot kind: "ToolCallStreaming" | "ReasoningDelta" | ...
    payload: Mapping[str, Any]             # 已脱敏、可丢
    occurred_at: float
    emitted_by: str                       # plugin id / builtin id,可静态校验

class ProgressStream(Protocol):
    """Phase contribution 的进度通道。订阅者必须假设丢帧、可乱序、可压缩。"""
    async def emit(self, frame: ProgressFrame) -> None: ...
    def subscribe(self, *, since_seq: int = 0) -> AsyncIterator[ProgressFrame]: ...
    def snapshot(self) -> Sequence[ProgressFrame]: ...    # 调试/诊断;不可作 source of truth
```

#### 2. ProgressStream 与 JournalStore 的关系

| 维度 | JournalStore | ProgressStream |
|---|---|---|
| 写入主体 | Reducer fold 后 / / / phase exit factsensor | phase 内部 transform / observe contribution |
| Schema | lca.journal/2 envelope（ADR-0063） | ProgressFrame（无 envelope） |
| 持久化 | 必存、可重放、source of truth | 默认内存缓存；落盘可由可选 `ProgressReplayStore` 提供 |
| 序列号 | run-local `seq` | progress-local `seq`,与 journal 独立 |
| 一等公民 | 是事实 | **不是事实**；语义由 JournalEvent 在 phase 退出时被 factsensor 折叠 |

#### 3. `ToolCallStreaming` 从 journal catalog 移除

- `lca/contracts/models/observability/journal.py:393-413` `ToolCallStreaming` dataclass 删除
- `lca/contracts/models/observability/journal_catalog.py:71,104` 移除登记
- 任何 `record(ToolCallStreaming(...))` 调用改为 `progress.emit(ProgressFrame(channel="tool_arg_delta", kind="ToolCallStreaming", payload={...}))`
- `lca/cognition/brain/llm_turn/executor.py:106-122` 改为通过 ProgressStream emit

**影响**：journal catalog 不再增加新事件类型，符合 ADR-0069 G4 + ADR-0063 §I6「动态扩展不扩张核心原语」。ToolCallStreaming 的事实版本（`ToolStarted.arguments`）由 `ToolInvoked` 落地，journal fact 体积降至 ~200 KB / run。

#### 4. SSE 端点扩展 progress 通道

```python
# lca/plugins/transport/webserver/handlers/runs/api/routes.py
# stream_run_live 新增 progress 通道订阅,与与
async def stream_run_live(request):
    ...
    async def _gen():
        # facts 通道:journal events（StampedEvent → SSE frame）
        async for frame in iter_journal_sse(session.tail, after_seq=after):
            yield frame
        # progress 通道:ProgressStream → SSE event:progress
        async for frame in iter_progress_sse(session.progress, since_seq=after_progress):
            yield frame
```

**LobeHub 端** `lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts` 拆为：

- `lcaJournalFacts.ts`（仅 journal event 投影）
- `lcaProgressStream.ts`（仅 progress 帧消费）

### 二、ADR-0156-B：**Projection 隔离 —— `apply_artifact_closure` 退出 reducer 流**

#### 1. Reducer Protocol 收紧

```python
# lca/contracts/protocols/state/reducer.py
class Reducer(Protocol):
    # 全部纯函数;返回新 AgentState;不持有 view / closure / projection
    def apply_perception(self, state, manifest) -> AgentState: ...
    def apply_turn(self, state, turn) -> AgentState: ...
    def apply_memory(self, state, writes) -> AgentState: ...
    def apply_error(self, state, error) -> AgentState: ...
    def apply_paused(self, state, cursor) -> AgentState: ...
    def apply_terminal(self, state, stop_decision, *, plan_ref, journal_seq_end, resume_cursor=None) -> AgentState: ...
    # 删除:
    #   - apply_artifact_closure(self, state, closure) -> AgentState
```

#### 2. `ArtifactClosureProjection` 改为纯 projection seam

```python
# lca/contracts/observability/artifact_closure_projection.py（新文件，替代旧 ArtifactClosure）
class ArtifactClosureProjection(Protocol):
    """G12 范畴:派生视图。不写 state,不写 journal facts。只 emit progress。"""
    def synthesize(self, *, workspace: Workspace, state: AgentState) -> ClosureProjection | None: ...

@dataclass(frozen=True)
class ClosureProjection:
    text: str
    artifact_refs: tuple[ArtifactRef, ...]
    plan_ref: str
```

#### 3. `finalizer` 重写

```python
# lca/runtime/result_finalizer.py
async def finalize(self, *, interpretation, plan_ref, journal_sequence):
    final_state = interpretation.state
    await self._hooks.trigger("on_complete", final_state)   # 仅触发 hook;hook 不得改 status

    outcome = interpretation.outcome
    if outcome.kind == "failed":
        final_state = self._reducer.apply_error(final_state, outcome.as_exception())
    elif outcome.kind == "paused":
        final_state = self._reducer.apply_paused(final_state, outcome.cursor)

    # projection 在 state fold 之后 emit,不出
    if ( proj := self._artifact_closure_projection.synthesize(workspace=..., state=final_state) ) is not None:
        await self._progress.emit(ProgressFrame(
            seq=..., channel="artifact_closure", kind="ClosureProjection",
            payload={"text": proj.text, "plan_ref": proj.plan_ref}, ...))
    # terminal 折叠:Reducer 仍是唯一终态写者
    terminal_outcome = self._reducer.apply_terminal(
        final_state, outcome.stop, plan_ref=plan_ref, journal_seq_end=journal_sequence,
        resume_cursor=_resume_cursor(outcome, journal_sequence),
    )
    return await self._result_projection.project(final_state, terminal_outcome=terminal_outcome, ...)
```

#### 4. 删 `phase_graph/stop_policy.py` 借代 `_artifact_closure.synthesize()`

```python
# 删除:_budget_exhausted_decision 中
#     final_output = self._artifact_closure.synthesize()
# 替换为:
#     final_output = decision.response_text    ( ( 与)
```

#### 5. 删 `plugins/transport/.../artifact_closure.py` 的 state/journal 副作用

- 整段 `store.append(StepTextDelta(step=-1, channel=answer, text_delta=closure))` 删除
- 改为 `await progress.emit(ProgressFrame(channel="artifact_closure", ...))`
- `session.status` FAILED 时不再发 closure（被 progress 通道取代）；前端 SSE 按 channel=artifact_closure 显式渲染

#### 6. TerminalOutcome 重写 `final_output` 语义

按 ADR-0077 §三 "Result 只读 TerminalOutcome 与 projection"——`state.final_output` 字段**移除**，改由 `TerminalOutcome.final_output_ref` 持有 `TextRef` 或 `ArtifactRef`，projection 在结果投影时调用 resolver。

### 三、ADR-0156-C：**PhaseFactsensor Protocol —— phase 退出自动收口**

#### 1. Factsensor 协议

```python
# lca/contracts/observability/phase_factsensor.py（新文件）
from typing import Protocol

class OpenSlot(Protocol):
    """任何 phase contribution 在收尾前未关闭的占位。"""
    slot_id: str
    kind: str                         # "tool_call" | "delegation" | "approval" | ...
    last_emit_at: float
    last_payload: Mapping[str, Any]

class PhaseFactsensor(Protocol):
    """G4 范畴:phase 退出时把未收口的占位折叠成 facts。"""
    @property
    def name(self) -> str: ...
    async def on_phase_exit(
        self,
        *,
        phase_id: str,
        outcome: DeclarativeRunOutcome,
        open_slots: tuple[OpenSlot, ...],
    ) -> tuple[JournalEvent, ...]:
        """返回该 phase 退出时需要 record 的事件;默认 no-op 返回空 tuple。"""
```

#### 2. 默认实现：tool_call 收口

```python
# lca/plugins/observability/phase_factsensor_default.py（新文件）
@plugin(
    id="phase.factsensor.tool_call",
    provides=("phase.factsensor",),
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/observability/test_phase_factsensor_tool_call.py",
)
class ToolCallPhaseFactsensor:
    """把 open tool_call slots → ToolCancelled / ToolFailed / ToolSucceeded。
    
    优先级:phase outcome 决定主要事件;每个 open slot 单独一条 facts。
    """
    async def on_phase_exit(self, *, phase_id, outcome, open_slots):
        events = []
        for slot in open_slots:
            if slot.kind != "tool_call":
                continue
            if outcome.kind == "failed":
                events.append(ToolFailed(
                    tool_call_id=slot.slot_id,
                    error=outcome.error_message or "phase_failed",
                    phase_id=phase_id,
                ))
            elif outcome.kind == "canceled":
                events.append(ToolCancelled(
                    tool_call_id=slot.slot_id,
                    reason="phase_canceled",
                    phase_id=phase_id,
                ))
            elif outcome.kind == "completed":
                # 正常完成但 tool 未落地 → 也必须收口
                events.append(ToolFailed(
                    tool_call_id=slot.slot_id,
                    error="tool_not_invoked_after_stream",
                    phase_id=phase_id,
                ))
        return tuple(events)
```

#### 3. PhaseInterpreter 集成

```python
# lca/harness/declarative/execute/interpreter.py
class GenericPlanInterpreter:
    def __init__(self, *, factsensor: PhaseFactsensor | None = None, ...):
        self._factsensor = factsensor
    
    async def _exit_phase(self, phase_id: str, result: PhaseResult):
        # 1. factsensor 收口
        if self._factsensor is not None:
            open_slots = self._open_slot_registry.snapshot(phase_id=phase_id)
            for evt in await self._factsensor.on_phase_exit(
                phase_id=phase_id,
                outcome=self._current_outcome,
                open_slots=open_slots,
            ):
                record(evt)
        # 2. 触发下一个 phase (与现有逻辑一致)
        ...
```

#### 4. 新事件类型（需 C1 闭集豁免）

| 事件 | 用途 | 事实 vs projection |
|---|---|---|
| `ToolCancelled(tool_call_id, reason, phase_id)` | factsensor 收口:phase 取消时 tool 未关闭 | **事实** —— phase 退出 + tool 终止是可审计的事实 |
| `ToolFailed(tool_call_id, error, phase_id)` | factsensor 收口:phase 失败时 tool 未关闭,或 tool 流后未落地 | **事实** —— phase 退出 + tool 失败是可审计的事实 |

**闭集豁免**：这两个事件**不增加新 phase**，只是 factsensor 的 typed output，符合 ADR-0069 G4。

### 四、`lca_runtime` `execute_with_policy` 集成 factsensor

```python
# lca/harness/declarative/compile/phase_execution_policy.py
async def execute_with_policy(*, node_id, policy, plan_ref, execute_attempt, budget, factsensor=None):
    try:
        return await PhaseExecutionRunner(factsensor=factsensor).execute(...)
    except PhaseExecutionExhaustedError as error:
        # failure_policy 由 phase_factsensor 触发 tool_failed 收口
        if factsensor is not None and error.failure.attempts:
            for evt in await factsensor.on_phase_exit(
                phase_id=node_id,
                outcome=DeclarativeRunOutcome.failed(error.failure),
                open_slots=_collect_open_slots_from_failure(error.failure),
            ):
                record(evt)
        ...
```

### 五、LobeHub 协同 —— 拆 `lcaJournal.ts` 为双通道

`lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts` 拆为：

```ts
// lcaJournalFacts.ts —— 仅 journal event 投影;无 ToolCallStreaming
export function projectJournalFrame(frame: JournalFrame): ProjectedFact { ... }

// lcaProgressStream.ts —— 仅 progress 帧消费
export function projectProgressFrame(frame: ProgressFrame): ProjectedProgress { ... }
```

`LcaRunDriver` SSE 客户端按 `event:` 字段分发到两个 consumer。`ToolCancelled` / `ToolFailed` 走 facts 通道,与既有的 `ToolStarted` / `ToolInvoked` 同一路径。LobeHub `LcaRunDriver.applyProjected('tool-cancelled')` 把对应 placeholder 改成终止态,spinner 收敛。

### 六、ADR-0156-D：**`LlmCall` 必须有 CompletionSentinel —— 流断流仍产 COMPLETED**

#### 1. 现状与宪法 gap

ADR-0038 已规定流式契约：`stream()` 终态 `COMPLETED.response` 与 `complete()` 等价，且 `LlmCallCompleted.stream` 字段标记流式。然而。**LLM provider 的 stream 不是总发 `COMPLETED` 帧**：

- DashScope / Qwen 长输出场景偶发不发 COMPLETED
- 流被客户端/网络中断（`asyncio.CancelledError`、`ConnectionError`）

当前实现 `lca/cognition/brain/llm_turn/executor.py:127-130` 在 `event.type == COMPLETED and event.response is not None: break`，**若不发 COMPLETED 就 fallback 走 retry 循环**，最终可能根本没 `LlmCallCompleted` 事件入 journal。`run_b1294a33e55d` 的 `LlmCallStarted×4 / LlmCallCompleted×2` 失衡即根因。

后果：OTel gen_ai 缺记录、latency/usage 缺统计、无法定位"流在哪个模型/哪个 prompt 断的"。

#### 2. 协议新增 `LlmCallLifecycleGuard`

```python
# lca/contracts/observability/llm_call_lifecycle.py（新文件）
class LlmCallLifecycleGuard(Protocol):
    """LLM 调用的因果收口器。G4 factsensor 范畴：把流断流转化为事实。"""

    async def finalize(
        self,
        *,
        call_id: str,
        started_at: float,
        completed: bool,                         # True if provider sent COMPLETED
        response_text: str | None,
        tool_calls: tuple[Any, ...],
        error: BaseException | None,
    ) -> LlmCallCompleted:
        """无论流是否正常关闭,必产一条 LlmCallCompleted 事实。
        
        不变量:
        - ok = completed and error is None
        - latency_ms = monotonic(started_at, now())
        - stream = True
        - prompt_preview / response_preview 由 caller 截断脱敏后传入
        """
```

#### 3. `stream_then_collect_response` 重构

```python
# lca/cognition/brain/llm_turn/executor.py
async def stream_then_collect_response(
    llm, prompt, tools, step, llm_kwargs, *, lifecycle_guard: LlmCallLifecycleGuard
) -> LLMResponse:
    accumulated = ""
    started_at = time.monotonic()
    call_id = uuid4().hex
    try:
        async for event in llm.stream(prompt, tools=tools, step=step, **llm_kwargs):
            # ... (event handling 同 ADR-0038)
            if event.type == LLMStreamEventType.COMPLETED and event.response is not None:
                response = event.response
                await lifecycle_guard.finalize(
                    call_id=call_id, started_at=started_at, completed=True,
                    response_text=response.text, tool_calls=response.tool_calls,
                    error=None,
                )
                return _merge_stream_response(response, accumulated)
    except (asyncio.CancelledError, ConnectionError, TimeoutError) as err:
        await lifecycle_guard.finalize(
            call_id=call_id, started_at=started_at, completed=False,
            response_text=accumulated or None, tool_calls=(),
            error=err,
        )
        raise
    # 流自然结束但无 COMPLETED —— 仍必须 finalize
    await lifecycle_guard.finalize(
        call_id=call_id, started_at=started_at, completed=False,
        response_text=accumulated or None, tool_calls=(),
        error=RuntimeError("llm_stream_ended_without_completed_event"),
    )
    # ... 空流 fallback (ADR-0038 §三)
```

#### 4. 默认实现

```python
# lca/infrastructure/observability/llm_call_lifecycle_default.py（新文件）
@plugin(id="llm.lifecycle.guard.default", provides=("llm.lifecycle.guard",), ...)
class DefaultLlmCallLifecycleGuard:
    async def finalize(self, *, call_id, started_at, completed, response_text, tool_calls, error):
        ok = completed and error is None
        await record(LlmCallCompleted(
            call_id=call_id,
            ok=ok,
            latency_ms=int((time.monotonic() - started_at) * 1000),
            stream=True,
            error=str(error) if error else "",
            # prompt_preview / response_preview 由 brain layer 截断脱敏
        ))
```

#### 5. ADR-0063 §I2 兑现

「提交先于观察」——LlmCallCompleted 即使在失败路径也是 commit 事实，不允许"流断 → 不发事件"。`try/finally` 或 `try/except` 的 `except` 分支必须 finalize，不允许裸 `raise` 跳过。

### 七、ADR-0156-E：**`PhaseRunCursor` 与 `state.step` 同步 —— 重试期间 step 必须递增**

#### 1. 现状与宪法 gap

ADR-0075 §三 已规定："phase graph 节点退出时 `PhaseRunCursor` 持有下一步信息"。然而。**重试期间 step 视觉冻结**：`run_b1294a33e55d` 中 `LlmCallStarted #1265 → #2666` 间隔 1 分钟以上仍记 `step=3`，原因：

- `state.step` 仅在 `perceive_hub`（perceive phase 入口）递增
- `phase_execution_policy` 重试 think.main 时不进 perceive
- 上层 step-bound（如 max_steps、N+1 trace）以 `state.step` 为基线，重试期间失真

后果：重试与正常 step 视觉不可分、journal 排序误导、UI 步骤计数错位。

#### 2. `StepClock` Protocol

```python
# lca/contracts/observability/step_clock.py（新文件）
class StepClock(Protocol):
    """G3 范畴:state.step 的事实源。perceive 与 phase 重试都调 advance()。"""
    
    def current(self) -> int: ...
    def advance(self) -> int: ...    # 返回新 step;journal 上 emit StepAdvanced 事实
    def reset(self) -> None: ...
```

#### 3. 默认实现与 phase graph 集成

```python
# lca/infrastructure/observability/step_clock_default.py（新文件）
@plugin(id="step.clock.default", provides=("step.clock",), ...)
class DefaultStepClock:
    def __init__(self, hub: BoundObservability):
        self._hub = hub
        self._n = 0
    
    def current(self) -> int:
        return self._n
    
    def advance(self) -> int:
        self._n += 1
        # emit 事实 —— 不依赖 perceive
        record(StepAdvanced(step=self._n, source="phase_retry", at=time.time()))
        return self._n
```

```python
# lca/cognition/perceive_hub.py:73,101,118 —— 改造
# 旧:step=state.step
# 新:step=self._step_clock.current()    # 单一事实源

# lca/harness/declarative/compile/phase_execution_policy.py:60-110 —— 改造
async def execute_with_policy(...):
    for attempt in range(1, policy.max_attempts + 1):
        await self._step_clock.advance()    # 重试算一步;journal 留痕
        try:
            return await self._execute_with_timeout(...)
        except Exception as error:
            ...
```

#### 4. 新事件 `StepAdvanced`

```python
# lca/contracts/models/observability/journal.py 新增
@dataclass(frozen=True)
class StepAdvanced(JournalEvent):
    step: int
    source: str                 # "perceive" | "phase_retry" | "tool_retry" | ...
    at: float
```

**闭集豁免**：StepAdvanced 不是 phase，是 G3 factsensor 的 typed output（每 step 推进是事实）。

#### 5. C7 兑现

控制（step 推进）走 StepClock；观察（journal 留痕）走 StepAdvanced factsensor。两个 seam 强制每一步可追溯、不漏步、不重步。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| ADR-0037 兑现 | journal 仅含事实,无 provider 流中转 | `ToolCallStreaming` 从 journal 删除是 schema breaking,需 ADR-0101 PR-3 同步更新 |
| ADR-0069 G4 落实 | factsensor 是 G4 范畴的实现,phase 退出可观察 | 需要新增 2 个 JournalEvent 类型（ToolCancelled / ToolFailed） |
| ADR-0070 C4 兑现 | `apply_artifact_closure` 退出 reducer 流,reducer 是唯一 state writer | 所有 `state.final_output` 写入点迁移至 `TerminalOutcome.final_output_ref` |
| ADR-0075 MTK 不变量 | "Reducer 唯一 State writer"通过协议 + lint 双重强制 | `state.final_output` 字段从 `AgentState` 删除,所有读取方迁移 |
| ADR-0077 兑现 | TerminalOutcome 是唯一终态,artifact closure 走 projection 不进 state | `Result.from_state(state)` 删除,`Result` 仅从 `TerminalOutcome` 投影 |
| journal 体积 | 31 MB → ~200 KB | ToolCallStreaming 不再落盘;replay 工具依赖 ToolCallStreaming 的需迁移到 ProgressReplayStore(可选) |
| narrative.md | narrative 只描述事实 + 阶段汇总,不再被 stream 淹没 | narrative sidecar 增加"progress 帧"显示开关 |
| 兼容性 | Profile 不变;Boot 不变;Composition root 不变 | contracts/observability/* 新增 5 个文件（progress_stream, phase_factsensor, artifact_closure_projection, llm_call_lifecycle, step_clock）;journal catalog 删除 1 个事件、增加 3 个事件（ToolCancelled/ToolFailed/StepAdvanced）|
| 复杂度 | 五个 seam 清晰、可机械测试、双通道 + 双重 finalize + 单一 step clock | 需新增 5 个 Protocol + 默认实现、测试、SSE 通道测试、step clock hook |
| ADR-0038 兑现 | LlmCallLifecycleGuard 保证流断流仍产 COMPLETED | executor.py 重构；provider stream 自然结束路径必须 finalize |
| ADR-0075 §三 兑现 | StepClock 统一 step 推进,phase 重试也算一步 | perceive_hub 与 phase_execution_policy 都走 StepClock.advance(),新增 StepAdvanced factsensor |
| ADR-0063 §I2 兑现 | 「提交先于观察」——LlmCallCompleted 即使在失败路径也是 commit 事实 | 流断流的异常分支必须 finalize,不允许裸 raise |

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 把 ToolCallStreaming 字段改成 `arguments_delta` | 半补丁;事件仍错位在 journal |
| 给 `apply_artifact_closure` 加 lint 守卫禁止改 status | 半补丁;projection 仍错位在 reducer |
| 在 phase 退出时硬编码 record ToolCancelled | 半补丁;factsensor seam 缺失,下次还得改 |
| 把 factsensor 写在 GenericPlanInterpreter 内部 | 违反 ADR-0069 G10 + ADR-0075 MTK,解释器应只解释计划 |
| LlmCallCompleted 由 executor 在 happy path 记录 | 违反 ADR-0063 §I2 「提交先于观察」——流断流时 COMPLETED 缺失 |
| 把 state.step += 1 散落在 perceive_hub / phase_execution_policy 各处 | 违反 ADR-0069 G3 「Facts/State/Knowledge 由 factsensor 收敛」;step 推进应有单一事实源 |

## 验证约束（机械可执行）

每条都是 `uv run <cmd>` 直接验证:

```bash
# 1. journal 不再含 ToolCallStreaming（重构 A）
uv run pytest tests/observability/test_journal_no_streaming.py -v
# 内容:扫描所有 journal 写入路径,断言 stamped_to_record() 不出现 ToolCallStreaming

# 2. reducer 不再有 projection 写入 state（重构 B）
uv run ruff check --fix . && uv run ruff format .
scripts/check_no_state_outside_reducer.py   # 新 lint script:扫描 reducer 之外的 state.x = ... 模式

# 3. reducer.apply_artifact_closure 已删除（重构 B）
uv run pytest tests/runtime/test_reducer_protocol_surface.py -v
# 内容:断言 Reducer Protocol 不再有 apply_artifact_closure

# 4. phase 退出时必调 factsensor（重构 C）
uv run pytest tests/declarative/test_phase_factsensor_invoked.py -v
# 内容:任意 phase 退出 mock,断言 factsensor.on_phase_exit 被调用

# 5. factsensor 默认实现:tool_call 收口为 ToolCancelled/ToolFailed（重构 C）
uv run pytest tests/observability/test_phase_factsensor_tool_call.py -v
# 内容:任意 open tool_call slot + phase outcome=failed → ToolFailed 事件

# 6. JournalCatalog 不再有 ToolCallStreaming（重构 A）
uv run pytest tests/contracts/test_journal_catalog_closure.py -v
# 内容:遍历 catalog,断言 ToolCallStreaming 不存在

# 7. ProgressStream 协议完整
uv run pytest tests/observability/test_progress_stream_contract.py -v
# 内容:ProgressStream 实现必满足 emit/subscribe/snapshot + 必填字段

# 8. TerminalOutcome 是唯一终态,state.final_output 已移除（重构 B）
uv run pytest tests/declarative/test_terminal_outcome_singleton.py -v
# 内容:AgentState 不再有 final_output;TerminalOutcome.final_output_ref 唯一来源

# 9. LobeHub lcaJournal.ts 已拆为双通道
cd lobehub-ui && bun test src/store/chat/agents/transports/lcaJournalFacts.test.ts
bun test src/store/chat/agents/transports/lcaProgressStream.test.ts

# 10. LlmCallLifecycleGuard 必产 COMPLETED（重构 D）
uv run pytest tests/cognition/brain/llm_turn/test_lifecycle_guard.py -v
# 内容:provider stream 提前 close / asyncio.CancelledError / ConnectionError
#       → LlmCallCompleted(ok=False, error=...) 仍必产

# 11. LlmCallCompleted 数量 == LlmCallStarted 数量（重构 D）
uv run pytest tests/observability/test_llm_call_balance.py -v
# 内容:任意 run 的 journal:count(LlmCallStarted) == count(LlmCallCompleted)

# 12. 流断流异常路径必产 LlmCallCompleted（重构 D）
uv run pytest tests/cognition/brain/llm_turn/test_stream_failure_finalize.py -v
# 内容:mock provider stream raise ConnectionError,断言 LlmCallCompleted(ok=False) 已 record

# 13. StepClock 单一事实源（重构 E）
uv run pytest tests/observability/test_step_clock.py -v
# 内容:state.step 任何写入点必须经 StepClock.advance();直接 state.step += 1 失败

# 14. phase 重试期间 step 必须递增（重构 E）
uv run pytest tests/declarative/test_phase_retry_advances_step.py -v
# 内容:phase max_attempts=3 重试耗尽,journal 含 3 条 StepAdvanced,最终 state.step >= 3

# 15. StepAdvanced 事件 catalog 闭包（重构 E）
uv run pytest tests/contracts/test_journal_catalog_step.py -v
# 内容:catalog 含 StepAdvanced;descriptors 含 step_clock.advanced

# 16. narrative sidecar 记 error（独立小修,与症状 #4 对应）
uv run pytest tests/observability/test_narrative_sidecar_error.py -v
# 内容:narrative markdown 含 error= 字段
```

## 删除清单

| 删除位置 | 删除内容 | 理由 |
|---|---|---|
| `lca/contracts/models/observability/journal.py:393-413` | `ToolCallStreaming` dataclass | journal 不接 progress |
| `lca/contracts/models/observability/journal_catalog.py:71,104` | ToolCallStreaming 登记 | 同上 |
| `lca/runtime/reducer.py:apply_artifact_closure` | 整个方法 | projection 不进 reducer |
| `lca/contracts/protocols/state/reducer.py:apply_artifact_closure` | Protocol 方法 | 同上 |
| `lca/contracts/models/core/state.py:AgentState.final_output` | 字段 | TerminalOutcome 唯一终态 |
| `lca/plugins/transport/webserver/handlers/runs/observability/artifact_closure.py:store.append(StepTextDelta)` | journal 写入 | progress 通道取代 |
| `lca/plugins/transport/webserver/handlers/runs/observability/artifact_closure.py:workspace.artifacts.snapshot()` 直接发 closure | 绕过 session.status | 必须读 session.status,只在 COMPLETED / DEGRADED 发 |
| `lca/plugins/phase_graph/stop_policy.py:_budget_exhausted_decision` 中 `_artifact_closure.synthesize()` 借代 | 借用 projection 字段 | decision.response_text 唯一来源 |
| `lca/contracts/observability/artifact_closure.py` 旧 `ArtifactClosure` Protocol | 旧协议 | 替换为 ArtifactClosureProjection |
| `lca/cognition/brain/llm_turn/executor.py:106-122 record(ToolCallStreaming(...))` | record 调用 | progress.emit |
| `lca/runtime/result_finalizer.py:50-55 apply_artifact_closure(...)` | reducer fold | progress.emit 取代 |
| `lca/harness/declarative/execute/outcome_projection.py:283,335 final_output=None` 字段 | 占位 None | TerminalOutcome.final_output_ref 取代 |
| `lca/cognition/brain/llm_turn/executor.py:127-130` happy path 写 LlmCallCompleted | happy path 直发 | LlmCallLifecycleGuard 统一 finalize,所有路径（含异常）必产事实 |
| `lca/cognition/perceive_hub.py:73,101,118` 散落 step 写入 | 各自 `step=state.step` | StepClock 单一事实源 |
| `lca/harness/declarative/compile/phase_execution_policy.py` 重试循环内无 step 推进 | 重试期间 step 冻结 | StepClock.advance() 在每次 attempt 入口 |

## 新增清单

| 新增位置 | 新增内容 |
|---|---|
| `lca/contracts/observability/progress_stream.py` | `ProgressStream` Protocol + `ProgressFrame` dataclass |
| `lca/contracts/observability/phase_factsensor.py` | `PhaseFactsensor` Protocol + `OpenSlot` Protocol |
| `lca/contracts/observability/artifact_closure_projection.py` | `ArtifactClosureProjection` Protocol + `ClosureProjection` dataclass（替换旧 ArtifactClosure） |
| `lca/contracts/models/observability/journal.py` | `ToolCancelled` / `ToolFailed` 两个 dataclass（factsensor 收口事件） |
| `lca/infrastructure/observability/progress_stream/in_memory.py` | 默认 `ProgressStream` 实现（内存 + 可选落盘） |
| `lca/infrastructure/observability/journal/engine/journal_io.py` | `stamped_to_record` 增加 channel 字段（fact / progress 二选一） |
| `lca/infrastructure/observability/journal/stream/live_tail.py` | `iter_progress_sse` + `iter_journal_sse` 分离 |
| `lca/plugins/observability/phase_factsensor_default.py` | `ToolCallPhaseFactsensor` 默认实现 |
| `lca/plugins/observability/progress_stream_default.py` | 注册默认 ProgressStream |
| `lca/harness/declarative/execute/interpreter.py` | `_exit_phase` 调 factsensor |
| `lca/harness/declarative/compile/phase_execution_policy.py` | `execute_with_policy` 调 factsensor |
| `scripts/check_no_state_outside_reducer.py` | lint:reducer 之外禁写 state |
| `scripts/check_journal_no_progress_signal.py` | lint:journal 不接 progress 流 |
| `lobehub-ui/src/store/chat/agents/transports/lcaJournalFacts.ts` | facts 通道 projector |
| `lobehub-ui/src/store/chat/agents/transports/lcaProgressStream.ts` | progress 通道 consumer |
| `lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts` | SSE 双通道分发 |
| `lca/contracts/observability/llm_call_lifecycle.py` | `LlmCallLifecycleGuard` Protocol |
| `lca/contracts/observability/step_clock.py` | `StepClock` Protocol |
| `lca/infrastructure/observability/llm_call_lifecycle_default.py` | `DefaultLlmCallLifecycleGuard` 默认实现 |
| `lca/infrastructure/observability/step_clock_default.py` | `DefaultStepClock` 默认实现 + StepAdvanced factsensor |
| `lca/contracts/models/observability/journal.py` | `StepAdvanced(step, source, at)` factsensor 事件 |
| `lca/cognition/brain/llm_turn/executor.py` | `stream_then_collect_response` 重构:接 lifecycle_guard |
| `lca/harness/declarative/compile/phase_execution_policy.py` | `execute_with_policy` 重构:接 step_clock |
| `lca/cognition/perceive_hub.py` | 改读 `step_clock.current()` 取代 `state.step` |

## 落地顺序（机械可验证）

1. **重构 A**：写 ADR-0156-A 部分。3 个 commit：
   - commit 1：新增 ProgressStream Protocol + 默认实现；所有 `record(ToolCallStreaming(...))` 改为 `progress.emit(...)`。
   - commit 2：journal catalog 删除 ToolCallStreaming；live_tail.py 拆 iter_journal_sse + iter_progress_sse；SSE 端点双通道。
   - commit 3：LobeHub 拆 lcaJournal.ts 为 facts/progress；测试通过；删除 ToolCallStreaming 单元测试。
   - 每步跑 `pytest tests/observability/test_journal_no_streaming.py tests/contracts/test_journal_catalog_closure.py tests/observability/test_progress_stream_contract.py`。
2. **重构 B**：写 ADR-0156-B 部分。3 个 commit：
   - commit 1：新增 ArtifactClosureProjection Protocol；stop_policy 改为 `final_output=decision.response_text`。
   - commit 2：reducer Protocol 移除 `apply_artifact_closure`；reducer.py 删除方法；finalizer 改为 emit progress。
   - commit 3：AgentState 删除 final_output 字段；TerminalOutcome.final_output_ref 改 TextRef/ArtifactRef/StructuredRef；Result.from_state(state) 删除。
   - 每步跑 `scripts/check_no_state_outside_reducer.py` + `tests/runtime/test_reducer_protocol_surface.py` + `tests/declarative/test_terminal_outcome_singleton.py`。
3. **重构 C**：写 ADR-0156-C 部分。3 个 commit：
   - commit 1：新增 PhaseFactsensor Protocol + ToolCallPhaseFactsensor 默认实现 + journal catalog 增加 ToolCancelled / ToolFailed。
   - commit 2：GenericPlanInterpreter / execute_with_policy 集成 factsensor；ToolCallStream 槽管理加 `has_invoke_event`。
   - commit 3：LobeHub `applyProjected` 加 `tool-cancelled` / `tool-failed` case。
   - 每步跑 `tests/declarative/test_phase_factsensor_invoked.py` + `tests/observability/test_phase_factsensor_tool_call.py`。
4. **重构 D**：写 ADR-0156-D 部分。3 个 commit：
   - commit 1：新增 `LlmCallLifecycleGuard` Protocol + `DefaultLlmCallLifecycleGuard` 默认实现；boot 注册默认实现。
   - commit 2：`executor.py:stream_then_collect_response` 重构接 `lifecycle_guard`；happy path / 流自然结束 / 异常路径都必产 `LlmCallCompleted`；删除 happy path 直发 LlmCallCompleted 旧代码。
   - commit 3：provider stream 提前 close mock 测试，断言 LlmCallCompleted.ok=False 仍 commit；narrative.md 显示 LlmCallCompleted 完整。
   - 每步跑 `tests/cognition/brain/llm_turn/test_lifecycle_guard.py` + `tests/observability/test_llm_call_balance.py` + `tests/cognition/brain/llm_turn/test_stream_failure_finalize.py`。
5. **重构 E**：写 ADR-0156-E 部分。3 个 commit：
   - commit 1：新增 `StepClock` Protocol + `DefaultStepClock` 默认实现 + journal catalog 增加 `StepAdvanced(step, source, at)`。
   - commit 2：`perceive_hub.py` 改读 `step_clock.current()` 取代 `state.step`；`phase_execution_policy.py:execute_with_policy` 每次 attempt 入口调 `step_clock.advance()`；删除 `state.step += 1` 散落写入点。
   - commit 3：`cognitive_agent._run_lifecycle` 与 terminal outcome 投影也读 `step_clock.current()`，不读 state.step；步骤计数 UI 由 StepAdvanced 序列驱动。
   - 每步跑 `tests/observability/test_step_clock.py` + `tests/declarative/test_phase_retry_advances_step.py` + `tests/contracts/test_journal_catalog_step.py`。

## 解释（不是补丁,为什么）

| 现象 | 旧补丁方案 | 本方案 |
|---|---|---|
| journal 31 MB / 3800 ToolCallStreaming | 合并键 + delta 字段 | **ToolCallStreaming 不再是 journal 事件** |
| 折叠 UI 整段 Python | LobeHub 自行截断 / code 改成 delta | **progress 流只发增量,事实层不污染** |
| 标题一开始不渲染 | LobeHub 提前合并 description | **ToolStarted.facts 字段（journal 事实）+ progress 帧（UI 实时）** 双通道 |
| 工具调用全部是 X | phase 退出多发 ToolCancelled | **PhaseFactsensor Protocol 通用收口,任意占位可插拔收口** |
| run failed 仍推 answer 流 | artifact_closure 读 session.status | **artifact closure 是 projection(非 reducer 副作用),失败时不再入 progress 通道** |
| reducer.apply_artifact_closure 偷偷改 status | 删一行 status 副作用 | **整个方法删除;projection 走独立通道** |
| artifact closure final_output 借用 | 改 stop_policy 用 response_text | **TerminalOutcome.final_output_ref 唯一来源;state.final_output 字段删除** |
| LlmCallStarted×4 / LlmCallCompleted×2 失衡 | 流断流补一条 COMPLETED | **LlmCallLifecycleGuard 强制 finalize,所有路径必产事实（happy/异常/自然结束）** |
| think 重试期间 step 不递增 | phase_retry 单独 +1 | **StepClock 单一事实源,phase attempt 入口 advance,StepAdvanced 留痕** |

每一项修复都是**架构 seam 修复**,不是症状补丁;后续类似泄漏点都通过同一 seam 拦截,无需再写补丁。

## 风险与备选

- **风险 1**：journal catalog 删除 ToolCallStreaming 是 schema breaking。需同步审计所有 replay / inspector / 测试工具。
- **风险 2**：LobeHub 拆 lcaJournal.ts 为双通道会破坏既有 SSR/旧端。需同步更新 `lobehub-ui/.agents/acceptance/` 文档与 acceptance test。
- **风险 3**：AgentState 删除 final_output 字段涉及所有 `result.output` 读取方（legacy plugin / external adapter / LobeHub `result.output`）。
- **风险 4**：重构 D 改造 executor.stream_then_collect_response 影响所有 LLM provider 的 stream 实现（openai_compat / anthropic / qwen 等）。需 adapter 层验证 happy path 与异常路径都走 finalize。
- **风险 5**：重构 E 把 step 推进从 state.step 切到 step_clock；任何直接读 state.step 的 UI / projection / inspector 都需迁移到 step_clock.current() 或 StepAdvanced 序列。
- **备选 1**：若 ToolCancelled / ToolFailed 事件被 C1 闭集拒绝,改用单一 `ToolLifecycleEnded(tool_call_id, end_kind, reason)` 事件,通过 descriptor 区分 cancelled / failed / succeeded 三种事实。
- **备选 2**：若 LlmCallLifecycleGuard 与现有 TelemetryLLMAdapter（`TelemetryLLMAdapter.stream`）职责重叠,可让 TelemetryLLMAdapter 持有 LlmCallLifecycleGuard,adapters 层仍单一。