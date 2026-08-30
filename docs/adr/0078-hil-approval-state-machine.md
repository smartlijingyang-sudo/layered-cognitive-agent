# ADR-0078: HIL/Approval as First-Class State Machine

## 状态

**Proposed — 2026-08-24**

Refines: [ADR-0067](0067-spacetime-runtime-and-governed-creation.md)、[ADR-0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md)、[ADR-0076](0076-six-plane-capability-layout-and-substitution-test.md)、[ADR-0077](0077-terminal-outcome-protocol.md)。

## 背景

当前 HIL 路径散落在多类组件之间：

- `ToolStarted` 事件由 tool runtime 发出，但 `ToolInvoked` / `ToolDenied` / `EffectCompleted` / `EffectDenied` 不一定有终态
- `ApprovalRequested` → `WAITING_INPUT` → `ApprovalResolved` 流程在测试中实际产出 `FAILED`，run doctor 报告 `tool started without invoked/denied`
- `StandardPhaseExecutor` 直接 mint `CommandEnvelope`，`RuntimeEffectGateway` 执行幂等，`GenericPlanInterpreter` 捕获 `ApprovalPendingError`——暂停点、cursor、snapshot、approval request 与 resume 输入契约零散
- resume 路径仍可能引用 live `asyncio.Task`、`snapshot`、旧 `runnable` 对象，违反 ADR-0073 的 session path 收敛

ADR-0067 8 状态机被 ADR-0074 裁剪到 4 状态机，但 HIL 的具体状态与转移仍未形式化。

## 决策

### 一、HIL 五状态 + 六事实

把 HIL 当作一等状态机而非异常分支：

```
REQUESTED → WAITING → APPROVED → EXECUTING → COMPLETED
                ↓
              DENIED
                ↓
              EXPIRED (timeout)
```

每个状态对应一组必须在 journal 中存在的 facts：

| 状态 | 必填 facts | 不得出现的 facts |
|---|---|---|
| REQUESTED | `ApprovalRequested`、tool/effect metadata、idempotency_key | `EffectCompleted` |
| WAITING | `ApprovalPersisted`、resume cursor、`session_seq` | `EffectStarted`、`ToolInvoked` |
| APPROVED | `ApprovalResolved(approved=True)`、resume command、批准者 | `ToolDenied` |
| EXECUTING | `EffectStarted`、tool/effect metadata | `ApprovalRequested`（重复请求） |
| COMPLETED | `EffectCompleted`、receipt、artifact_ref（如有） | 任何 approval-* fact |
| DENIED | `ToolDenied`、`ApprovalResolved(approved=False)` | `EffectStarted` |
| EXPIRED | `ApprovalExpired`、timeout 阈值 | `EffectStarted` |

**任何 `ToolStarted` 之后必须有 `EffectCompleted` / `ToolDenied` / `EffectUncertain` 之一；缺失则 reducer 抛出 `IncompleteToolEvent` 并在 journal 留下 `EffectUncertain`。**

### 二、Resume 只能提交 command，不接触旧 live object

- `resume_run(input)` 不再调用 `session.runnable.resume(snapshot)`，改为投递 typed `ResumeCommand` 给 `CommandGateway`
- `ResumeCommand` 必填：`session_id`、`approval_token`（来自 `ApprovalPersisted`）、`payload`、`idempotency_key`
- `CommandGateway` 从 journal 重建 session state，重新解释 plan，禁止 resume 到一个没有完整 journal seq 的 session
- `live_state` 与 `asyncio.Task` 不得在 checkpoint 中保存；只保存 `session_id`、`plan_ref`、`journal_seq`、`approval_token`、`resume_cursor`

### 三、Approval / Cancel / Crash-after-effect / Duplicate-answer 各自有 property test

| 场景 | 必须验证的不变量 |
|---|---|
| 批准后执行中崩溃 | 重启 session 时看到 `EffectUncertain`，effect gateway 不得重复执行（基于 idempotency_key + journal seq） |
| 取消已批准未执行 | `CANCEL` 命令必须把 `APPROVED` 折叠为 `CANCELED`，不进入 `EXECUTING` |
| 重复回答同一审批 | 第二次回答必须按 idempotency_key 去重，不产生第二个 `EffectStarted` |
| Approval 超时 | `EXPIRED` 状态下任何后续 resume 命令拒绝 |
| 工具启动后无终态（网络断） | reducer 写 `EffectUncertain`，journal 中存在 fact，session 不得标 COMPLETED |

### 四、HIL 状态机由 reducer 折叠，不在 executor 中分支

- `StandardPhaseExecutor` 的 act / think 路径不再写 HIL 状态；HIL 状态仅由 reducer 在收到 `ApprovalRequested` / `ApprovalResolved` / `EffectStarted` / `EffectCompleted` / `ToolDenied` facts 后折叠
- reducer 暴露 `apply_approval_*` / `apply_effect_*` 一组纯函数；`PhaseResult.deltas` 触发 reducer，不直接改 state
- HIL 状态机以 typed enum 表达；测试只验证 reducer 输入输出，不读 executor 内部分支

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| 协议完整 | 6 facts + 7 状态全覆盖 | 每个 effect 路径都要补齐终态事件 |
| 可重放 | HIL 状态可从 journal 重放 | journal 写入路径必须带 approval_token |
| 拒绝 resume 副作用 | resume 只通过 CommandGateway | 旧 `runnable.resume(snapshot)` 调用方需迁移 |
| 故障安全 | crash-after-effect 不重复执行 | effect gateway 需 idempotency_key 校验 |

**验证约束：**

- `tests/hil/test_state_machine_transitions.py`：每条状态转移对应 reducer 折叠路径
- `tests/hil/test_required_facts_invariant.py`：每状态必填 facts 验证
- `tests/hil/test_resume_via_command_only.py`：resume 不接触 live object
- `tests/hil/test_crash_after_effect_property.py`：崩溃重放不重复执行
- `tests/hil/test_idempotent_approval_answer.py`：重复 answer 去重

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 继续以 `ApprovalPendingError` 异常分支表达 HIL | 异常分支无法重放，无法在 journal 中查找 |
| Resume 保留 `session.runnable.resume(snapshot)` | 违反 ADR-0073 session path 收敛；进程重启即丢 |
| 把 HIL 状态机放在 executor 而非 reducer | 违反 ADR-0070 Reducer 单写；状态散落不可重放 |
| 不要求 `EffectUncertain` 终态 | crash-after-effect 会导致重复执行 |