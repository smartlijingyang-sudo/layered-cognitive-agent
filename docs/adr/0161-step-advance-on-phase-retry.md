# ADR-0161：撤销 —— phase_retry 不该推进 step,UI 实时驱动走 ProgressStream

## 状态

**Withdrawn — 2026-09-01**(已由 [ADR-0162](0162-fact-vs-progress-judgment-criterion.md) 收口真方案)

subagent 深度评审发现:本 ADR 的核心修复点("phase_retry 期间 step 不递增 → 在 attempt 入口调 reducer")是**修错位置**;重试是同一回合,不应推进 step;真正"step 视觉冻结"是 UI 实时驱动问题,应走 ADR-0157 ProgressStream 通道,而非 journal 留痕。

## 评审发现的事实

### 1. phase_retry 不该推进 step

declarative runtime 的 phase 推进语义本就区分两个层面:

- **perceive-step**(主循环回合):每次 perceive → think → reflect 完成,step +1。已由 `plugins/phase_graph/perceive.py:60-65` 提 RunDelta → `delta_handlers.py:71-72 StepDeltaHandler.apply` → `reducer.apply_step_advanced` 闭环。
- **think-retry**(同一回合内重试):think.main 失败重试,**不应**推进 step,它在同一回合内。

### 2. ADR-0161 自身引入的双发与命名错位

| 问题 | 严重度 | 触发条件 |
|---|---|---|
| 双发 step | P0 | perceive 推 N→N+1,think.main attempt=1 又推 N→N+1,attempt=2 又 N→N+2;每次 think 第一次进入都重复推进 |
| record_step_advanced 命名位置错 | P1 | `journal_io.record_*` 现有族都是序列化/反序列化(`stamped_to_record` / `record_to_journal_record` 等),没有"向 journal 写入一条"的 helper;真正对应位置是 `facade.record(event)` |
| best_effort 误用 | P0 | `durability="best_effort"` 不等于"不进 fact 流",只是元数据描述;现有 backend 不基于此过滤。record_step_advanced 一旦写就真进 JSONL,污染 ADR-0037 事实流 |
| ProgressStream 通道冲突 | P0 | ADR-0157 拒绝"把 progress 也用 JournalEvent 投递+best_effort 标记"(理由:违反 §I6);本 ADR 用 best_effort 把 step 留痕塞回 journal,等于把否决的方案以新名字做回来 |
| perceive_hub 行号引用错 | P2 | ADR 写"lca/cognition/perceive_hub.py:73,101,118",但这三行不写 step;真实写入点是 `plugins/phase_graph/perceive.py:60-65` |
| PhaseExecutionRunner 模块边界违反 | P1 | `phase_execution_policy.py` docstring 自承"never selects plugins, reads live composition scope, or routes a graph";塞 reducer 调用违反模块边界 |

### 3. ADR-0161 与 ADR-0157 自相矛盾

- ADR-0157 §三否决 "把 progress 也用 JournalEvent 投递,但加 durability=best_effort 标记",理由:违反 ADR-0063 §I6 动态扩展不扩张核心原语
- ADR-0161 反手用 best_effort + record_step_advanced helper 把 step 留痕塞回 journal
- **同一通道,ToolCallStreaming 必须迁出,StepAdvanced 却可以留下——双标**

### 4. C4 reducer 是 state 唯一 writer 已守住

subagent grep `state.step` 全部写入点:

```
runtime/reducer.py:43:        state.step = step          # apply_step_advanced 内
runtime/reducer.py:273:        state.step += 1          # apply_resume 内
harness/projection/agent_state.py:76: state.step = data["step"] + 1  # session 反序列化
```

- 全部都在 reducer 协议内部或反序列化 helper 里
- **没有真实绕过**
- ADR-0161 的"reducer 是 state 唯一 writer"是真命题,无需新 seam 加固

### 5. 真实问题:UI 实时步骤计数

journal 时间序列的隐含契约是"必存、可重放、source of truth"(ADR-0157 §三 二表)。把"step 推进 UI 实时"塞进 journal = 倒退。

真方案:**UI 步骤实时计数走 ProgressStream channel="step" 或 channel="retry"**:

- 每次 perceive 入口 reducer 推 step 推进后,emit 一条 progress frame
- 每次 phase_retry 入口 emit `ProgressFrame(channel="retry", kind="PhaseRetry", payload={"attempt": N, "of": max_attempts})`
- LobeHub UI 从 ProgressStream 订阅,实时显示"正在重试 attempt 2/3"
- journal 不动,事实流保持纯净

## 评审结论

| 提案 | 评审结果 |
|---|---|
| §一 phase_execution_policy attempt 入口调 reducer.apply_step_advanced | **撤销** —— phase_retry 不该推进 step(同一回合内重试) |
| §二 journal_io.record_step_advanced helper + EventDescriptor | **撤销** —— best_effort 不进 fact 流是空头支票;命名位置错;ProgressStream 通道直接冲突 |
| §三 perceive_hub 改读 step_clock.current() | **撤销** —— perceive_hub 本就不读 step_clock;真实 step 写入在 plugins/phase_graph/perceive.py:60-65 |
| §四 UI 步骤计数从 journal record_step_advanced 序列驱动 | **撤销** —— journal 隐含契约是"必存、可重放",与"可丢进度信号"冲突;UI 实时驱动应走 ProgressStream |

## 真正需要做的 1 件事

**已由 [ADR-0162](0162-fact-vs-progress-judgment-criterion.md) 决策 二 收口**:不依赖 ProgressStream(已撤),复用 ADR-0157 的 `_delta_key` 合并键 + LiveTail 机制,新增 `ToolRetryProgress` best_effort JournalEvent:

`lca/harness/declarative/compile/phase_execution_policy.py` PhaseExecutionRunner 每次 attempt 入口 emit 一条 best_effort 增量:

```python
# phase_execution_policy.py:PhaseExecutionRunner.execute 循环顶部
async def execute(self, ...):
    for attempt in range(1, policy.max_attempts + 1):
        # 仅 emit best_effort 增量,不动 state.step
        from lca.infrastructure.observability.facade.facade import record
        record(ToolRetryProgress(
            tool_call_id=last_active_tool_call_id or "",
            phase_id=node_id,
            attempt=attempt,
            of=policy.max_attempts,
        ))
        try:
            return await self._execute_with_timeout(execute_attempt, timeout_seconds)
        except Exception as error:
            ...
```

LobeHub UI 订阅 LiveTail best_effort 流,在 phase 重试时显示"正在重试 attempt 2/3",spinner 不冻结但有状态提示;`state.step` 末值由 perceive 入口控制,正确且无双发。

## 替代方案(已采纳)

| 方案 | 理由 |
|---|---|
| 撤销本 ADR + 走 ADR-0162 `ToolRetryProgress` best_effort 流 | journal 不接 progress 信号是 ADR-0157 第一性原理;phase_retry 不该推 step 是 G3/G12 语义;不依赖 ProgressStream Protocol(已撤),复用 ADR-0157 通道 |
| phase_retry 不动 state.step,只 emit best_effort 增量 | 修对位置 + 复用已有 seam |

## 不落地清单

以下提案全部撤回,不实现:

- §一 phase_execution_policy.py attempt 入口调 `reducer.apply_step_advanced`
- §二 `journal_io.record_step_advanced` helper 函数
- §二 EventDescriptor 注册 `record_step_advanced`(durability=best_effort)
- §四 LobeHub 步骤计数从 journal record_step_advanced 序列驱动
- §「验证约束」#4 LobeHub stepSequence.test.ts

## 风险

- **风险 1** ~~ADR-0157 ProgressStream 通道若不先落地,phase_retry UI 状态无可订阅源~~ **已由 ADR-0162 收口**:真方案是 `ToolRetryProgress` best_effort JournalEvent(走 ADR-0157 `_delta_key` 合并通道),不再依赖已撤的 ProgressStream Protocol。
- **风险 2**:若未来真的需要 step 实时驱动(例如 N+1 trace),journal 留痕 + best_effort 方案会被重新提起。**缓解**:本 ADR 显式记录"该方案与 ADR-0157 冲突";ADR-0162 §I6 三准则 + ToolRetryProgress 命名通道已固定语义,future proposal 必须先引用本 ADR 与 ADR-0157 + ADR-0162 一并修订。