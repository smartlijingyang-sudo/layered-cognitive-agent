# ADR-0077: TerminalOutcome Protocol as Sole Terminal Truth

## 状态

**Proposed — 2026-08-24**

Refines: [ADR-0068](0068-compiled-plugin-kernel-and-unified-run-plan.md)、[ADR-0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md)、[ADR-0076](0076-six-plane-capability-layout-and-substitution-test.md)。

## 背景

当前 turn 结束路径上同时存在四个候选事实源：phase executor 返回的 `PhaseResult`、stop phase 产出的 `StopDecision`、`state.final_output` 字段、`Result.output` 属性。`_terminal_stop_decision()` 固定生成 `final_output=None`；`DeclarativeRuntimeDriver` 再用 `Result.from_state(final_state)` 反推终态。这造成：

- 同一 Profile 在不同入口下可能得到不同最终字段
- text / artifact / stream / structured output 没有分型契约
- artifact closure 通过 `synthesize_artifact_closure()` 自由函数拼接，未进入 reducer 流
- 错误终态（crash、approval timeout、cancel）无法与正常终态在协议层区分

ADR-0075 已规定六阶段闭集与 Reducer 单写，但未规定**终态唯一契约**。ADR-0076 已要求 boot 期硬失败，但未规定终端类型规范。

## 决策

### 一、引入 `TerminalOutcome` 协议

Stop phase 与 reducer 折叠后必须产出唯一的 `TerminalOutcome` 实例：

```python
class TerminalOutcomeKind(Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    WAITING_INPUT = "waiting_input"
    DEGRADED = "degraded"

@dataclass(frozen=True, slots=True)
class TerminalOutcome:
    kind: TerminalOutcomeKind
    stop_reason: str
    final_output_ref: ArtifactRef | TextRef | StructuredRef | None
    artifact_refs: tuple[ArtifactRef, ...]
    error_ref: ErrorRef | None
    resume_cursor: ResumeCursor | None
    plan_ref: str
    journal_seq_end: int
```

每个 `TerminalOutcome` 必须有：

- 唯一的 `kind`，覆盖所有非「继续循环」的退出路径
- 至少一个 `*_ref`（成功时 `final_output_ref`、失败时 `error_ref`、暂停时 `resume_cursor`）
- `plan_ref` 与最后一次 reducer fold 的 `journal_seq_end` 配对，保证外部观察者可从 journal 重放

### 二、PhaseResult / StopDecision / ArtifactClosure 各自归位

| 来源 | 职责 | 不得做 |
|---|---|---|
| `PhaseResult` | 单阶段 typed result（payload / deltas） | 不读 State，不写终态，不假装是终态 |
| `StopDecision` | stop phase 内部裁决 | 不直接写到用户可见字段 |
| Reducer | 唯一把 stop decision / artifact closure 折叠为 `TerminalOutcome` | 不构造 final_output 字符串，只折叠 ref |
| `ArtifactClosure` seam | 把 artifact ledger 折叠为 `tuple[ArtifactRef, ...]` | 不持有用户可见 output 文本 |
| `TerminalOutcome` | 唯一终态事实 | 不被任何 phase 直接构造，只由 reducer 产出 |

### 三、Result 只读 TerminalOutcome 与 projection

`Result.from_state(state)` 移除。所有用户可见 result 字段从 `TerminalOutcome` 与对应 projection 派生：

- `result.output` ← `terminal.final_output_ref.resolve(state)`
- `result.artifacts` ← `terminal.artifact_refs`
- `result.error` ← `terminal.error_ref.resolve(state)`
- `result.can_resume` ← `terminal.kind is WAITING_INPUT and terminal.resume_cursor is not None`

### 四、四类 output 的契约测试

每类 final_output 必须有 typed resolver：

| 类型 | resolver 协议 | 必填字段 |
|---|---|---|
| `TextRef` | 文本片段 + journal ref | text、seq、cursor |
| `ArtifactRef` | artifact_id + plan_ref | artifact_id、plan_ref、kind |
| `StructuredRef` | JSON schema + value ref | schema_id、value_ref |
| `StreamRef` | 流式增量起点 | first_seq、last_seq、model |

没有 typed resolver 的 final_output 类型拒绝进入 production schema。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| 单一事实源 | `TerminalOutcome` 是唯一终态 | 所有 `Result.from_state` 调用方需迁移 |
| 错误区分 | crash / cancel / approval-timeout 各自有 kind | error_ref 必须有 schema |
| 可重放 | plan_ref + journal_seq_end 保证 replay | journal 写入路径需要带 plan_ref 与 seq |
| 类型完整 | text / artifact / structured / stream 各自 typed resolver | resolver 实现成本 |

**验证约束：**

- `tests/declarative/test_terminal_outcome_contract.py`：每种 `TerminalOutcomeKind` 必填字段完整
- `tests/declarative/test_phase_result_does_not_pretend_terminal.py`：`PhaseResult` 不得有 `kind == COMPLETED` 等终态值
- `tests/declarative/test_artifact_closure_in_reducer.py`：artifact closure 经 reducer 折叠，不直接拼接
- `tests/declarative/test_text_structured_stream_resolvers.py`：每类 resolver 实现且契约测试通过

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 继续 `Result.from_state(state)` 反推 | 四源并存；`final_output=None` 固定 bug 无法定位 |
| 让每个 phase executor 自己写终态字段 | 违反 ADR-0070 Reducer 单写 |
| 不引入 typed resolver，`final_output` 永远是字符串 | text/artifact/stream/structured 无法区分 |
| 删 stop phase，把 stop logic 放 reducer | 违反 ADR-0075 六阶段闭集 |