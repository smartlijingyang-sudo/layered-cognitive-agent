# ADR-0191 — Runtime Loop DSH 收敛与 LCA 控制面保留

## 状态

**Implemented — 2026-09-08。** Wave A (model wire + checkpoint) + Wave B (repair + resume) + Wave C (gates → projection + RunCommitter) + Wave D (single stream) 全部关闭。详细验收见 `tests/architecture/test_runtime_convergence_invariants.py` 与 `tests/scenarios/test_adr0191_runtime_convergence.py`。

延伸 ADR-0186（Session SSOT）、0185（model-visible fold）、0189（derive/fork 词表）、0070（Reducer-as-Plugin）、0077（TerminalOutcome）、0078（HIL）。

**实施状态（2026-09-06）**

| Wave | 状态 | 验证 |
|---|---|---|
| A1 ModelContextAssembler | 完成 | `tests/cognition/test_model_context_parity.py` |
| A2 Surface + step boundary | 完成 | `tests/scenarios/test_adr0191_runtime_convergence.py` |
| A3 Checkpoint fail-closed | 完成 | `tests/plugins/session/test_checkpoint_integration.py` |
| B1 Repair | 完成 | `tests/plugins/session/test_repair.py` |
| B2 Restore integration | 完成 | `tests/plugins/session/test_recovery_integration.py` |
| B3 Transport resume | 完成 | `tests/transport/test_resume_session_recovery.py` |
| C TurnControl + RunCommitter | 完成 | `tests/plugins/session/test_turn_control_projection.py` |
| D Single-stream fold | 完成 | `tests/plugins/session/derivers/test_fold_deriver_single_stream.py` |

**对齐参考**：deepseek-harness `packages/core/session`（append / surface / deriveMessages / repair）、`packages/core/agent-loop`（ReactLoopAgent 只 append 不 mutate derived state）、`packages/session/session-checkpoint-policy`（三边界 fail-closed flush）、`packages/session/session-projection`（sessionProjections 纯 fold）。

**本文档配套 Note**：[`docs/notes/implemented/seam/2026-09-06-runtime-dsh-convergence.md`](../notes/implemented/seam/2026-09-06-runtime-dsh-convergence.md)。

## 0. 决策摘要

LCA 观测面（Session / Spine / fold / derive_messages）已按 DSH 方向落地大半；**运行时热路径仍走 imperative 双写**（`AgentState.history` → `build_tool_history`、Transport 内存 resume、checkpoint 有能力未接线、无 crash turn repair）。本 ADR 锁定 **事实层严格对齐 DSH、控制面保留 LCA 优点、Reducer 演进不删除** 的终态架构与分波实施。

```text
Session.append (facts SSOT, 对齐 DSH)
        │
        ├─► derive_messages + foldRequestHeader  →  ModelContextAssembler (LLM wire SSOT)
        │
        ├─► sessionProjections (turnBoundary, token_usage, …)  →  诊断/UI fold
        │
        ├─► repair_interrupted_turn (cold load only)  →  provider-valid transcript
        │
        └─► recover_live_agent  →  durable resume / HIL authority

RunCommitter (Reducer 演进)  →  control-plane state only
        status / budget / terminal / approval / skill_route / activation / memory policy
        ⚠️ 不再承担 model-visible history 构建

Ephemeral runtime  →  stream accumulators, abort controllers, loop phase (不持久化)
```

| 维度 | 对齐 DSH | 保留 LCA |
|---|---|---|
| 事实 SSOT | `Session.append` → spine.jsonl | 同左；鉴权矩阵 + plugin producer 白名单 |
| 模型上下文 | `derive_messages` + `request/header` | `ModelVisibleHook` 审计捕获 |
| Durability | 三边界 checkpoint fail-closed | `SessionCheckpointPolicy` capability |
| Crash repair | `interruptedTurnClosers` 语义 | 新 `session/repair.py` |
| Resume | log 延续 + `request/header { reason: resume }` | `approval.persisted.v1` + TerminalOutcome |
| 状态提交 | projection fold | **RunCommitter**（Reducer 演进）+ RunDelta + C5 envelope |
| 认知闭集 | turn/step 边界事件 | 六步 phase graph + declarative phases |
| 终端语义 | turn/end reason 词表 | `TerminalOutcome` / `ResumeCursor`（ADR-0077） |

**不做什么**：不删除 Reducer；不把 `AgentState` 整体换成 DSH 无命名 projection；不引入平行 messages 存储；不一次性重写 transport/webserver；不实现 DSH 上传水位 / session.vN 代际。

## 1. 第一性原理

### 1.1 四类状态（不可混写）

| 类别 | 问题 | 丢失后 | 拥有者 |
|---|---|---|---|
| **Facts** | 发生了什么？ | 不可丢（durable） | `Session.append` |
| **Model-visible** | 下一轮 LLM 看到什么？ | 必须从 Facts fold | `ModelContextAssembler` |
| **Control** | 能否继续？停在哪？预算？ | 可从 Facts fold；允许 in-process 缓存 | `RunCommitter` / control projections |
| **Ephemeral** | 当前 stream/abort 活着吗？ | 可丢 | loop runtime |

**核心不变量**：Facts 是唯一 durable 写入面；Model-visible 与 Control 均为投影，不得反向写 Facts。

### 1.2 DSH 已验证的模式

1. Loop **只 append**，不直接改 derived state。
2. **Surface 层**显式：`surfaceOp` append/replace；`deriveMessages` 走 surface nodes，非 raw log。
3. **Chunk vs message 分离**：`assistant/chunk*` 为 replay fidelity；`assistant/message` 进 transcript。
4. **语义 checkpoint**：`agent/pre-step` / `llm/stream` / `tools/execute` 三边界 flush；失败 fail-closed。
5. **Cold vs live repair 分离**：进程 crash 合成 closers；live open turn 由 live agent 权威。
6. **Resume = 新 loop 实例 + 旧 log**，非 snapshot 反序列化。

### 1.3 LCA 相对 DSH 的正当扩展

1. **C4/C5**：`CommandEnvelope` + capability 三维检查；commit 前授权。
2. **TerminalOutcome**（ADR-0077）：终端真值独立于 AgentState 字段。
3. **Declarative phase graph**：六步闭集 + ADR 门禁；非 DSH 单一 ReactLoop。
4. **HIL approval 状态机**（ADR-0078）：`waiting_input` ↔ 唯一 unresolved approval。
5. **Reducer-as-Plugin**（ADR-0070）：profile 可替换 fold 策略。
6. **分层 import 边界**：contracts → infrastructure → cognition；DSH 单 repo 布局不照搬。

## 2. 现状差距（2026-09-06 基线）

| 差距 | LCA 现状 | 目标 |
|---|---|---|
| Model wire 双路径 | 运行时 `build_tool_history(state.history)`；观测 `derive_messages(session)` | 运行时仅 `ModelContextAssembler` |
| Resume 双路径 | Transport `RunSession` 内存 snapshot/runnable | `recover_live_agent` + durable facts |
| Checkpoint 未 enforced | `SessionCheckpointPolicy` 存在，executor/body 未 await | 三边界 fail-closed |
| 无 crash turn repair | torn tail 有；无 `interruptedTurnClosers` | `repair_interrupted_turn()` |
| Reducer 职责污染 | `apply_turn` 写入 history 兼服务 LLM + gates | history 收窄为 control Turn 视图 |
| Session∪spine 双源 | `StepTreeFoldDeriver` COMPAT 并集 | 单流 delete-when |
| `recover_live_agent` 孤立 | 零 production call site | cold restore + transport resume |

## 3. 目标架构

### 3.1 数据流（每 step）

```text
┌─ 1. 读 ControlState（RunCommitter fold 或 cache）────────────────┐
│  status, budget, turn_boundary, pending_approval, activated_skills │
└────────────────────────────┬──────────────────────────────────────┘
                             ▼
┌─ 2. Perceive → append perception facts（如已有 journal 事件）──────┐
│  RunCommitter.apply_perception → control cache 更新                │
└────────────────────────────┬──────────────────────────────────────┘
                             ▼
┌─ 3. ModelContextAssembler.assemble(session) ──────────────────────┐
│  foldRequestHeader + derive_messages + system/tools injection      │
│  ⚠️ 禁止读 AgentState.history 构建 wire                             │
└────────────────────────────┬──────────────────────────────────────┘
                             ▼
┌─ 4. checkpoint(boundary=llm/stream) ──fail──► CheckpointFailure     │
│  Session.append(request/header)  [ModelVisibleHook]                 │
└────────────────────────────┬──────────────────────────────────────┘
                             ▼
┌─ 5. LLM stream → append assistant/chunk* (live)                     │
│  settle → append assistant/message (surface append)                 │
│  cancel → assistant/message { interrupted: true } 或 attempt 事件   │
└────────────────────────────┬──────────────────────────────────────┘
                             ▼
┌─ 6. tool/call → checkpoint(tools/execute) → body → tool/result      │
│  surface append (spine.body.tool.execute.end)                       │
└────────────────────────────┬──────────────────────────────────────┘
                             ▼
┌─ 7. remember → RunCommitter.commit_turn (control facts + fold)      │
│  append turn/control facts to Session；不 duplicate model surface    │
└────────────────────────────┬──────────────────────────────────────┘
                             ▼
┌─ 8. stop → apply_stop + apply_terminal_outcome（ADR-0077 顺序）     │
└────────────────────────────────────────────────────────────────────┘
```

### 3.2 Protocol 缝（contracts 层新增/明确）

```python
# lca/contracts/protocols/session/model_context.py

class ModelContextAssembler(Protocol):
    """从 Session 事实 fold 本轮 LLM 请求可见部分（DSH deriveMessages + header）。"""

    def assemble(self, session: SessionReader, *, step: int) -> ModelVisibleRequest: ...


# lca/contracts/protocols/session/control_state.py

class ControlStateFolder(Protocol):
    """从 Session 事实 fold 控制面状态（非 model wire）。"""

    def fold(self, session: SessionReader) -> ControlState: ...


# lca/contracts/protocols/state/run_committer.py

class RunCommitter(Protocol):
    """Reducer 演进名：commit 控制面变化；默认实现委托现有 Reducer.apply_*。

    中期：每个 commit 先 append control/turn facts，再 fold ControlState。
    长期：Session subscriber 纯 fold（ADR-0181 PR-9 方向）。
    """

    def commit_turn(self, state: AgentState, turn: Turn, session: SessionWriter) -> AgentState: ...
    # … 其余 apply_* 签名保持 Reducer 兼容，RunCommitter 为 Reducer 别名扩展
```

**命名收敛**（实施期逐步重命名，非 breaking 一次性）：

| 旧名 | 新语义 | 备注 |
|---|---|---|
| `AgentState.history` | `control_turns` 或 fold 视图 | 不是 model SSOT |
| `build_tool_history` | `@deprecated` → `ModelContextAssembler` | delete-when Wave A |
| `Reducer` | `RunCommitter`（别名） | Protocol 保留 `Reducer` 至 Wave C |

### 3.3 Surface 与 LCA 词表映射（SSOT）

沿用 ADR-0185 / `lca_kernel/events/fold.py` 闭集：

| DSH | LCA spine category | 进 derive_messages |
|---|---|---|
| `user/message` | `spine.llm.request.header`（messages 段） | 是（via header fold + surface） |
| `assistant/message` | `spine.llm.request.header.assistant` | 是 |
| `tool/result` | `spine.body.tool.execute.end` | 是 |
| `assistant/chunk` | `thinking.delta.v1` / stream live | 否 |
| `llm/retry` | `model.failed.v1` / retry 对位（待补） | 否 |

Session 层 `.v1` 事件（`message.accepted.v1`、`assistant.responded.v1`）为 **compat fallback**；新生产路径必须写 surface 事件，delete-when：`derive_messages` 测试不依赖 fallback。

## 4. Reducer 演进（保留，收窄）

### 4.1 三阶段

| 阶段 | Reducer 角色 | 验收 |
|---|---|---|
| **R0（现在）** | imperative `apply_*` + `runtime.reducer.apply` marker | 基线 |
| **R1（Wave A–B）** | 停止用 `history` 构建 model wire；gates 仍读 control turns | `build_tool_history` 生产路径 = 0 |
| **R2（Wave C）** | `commit_turn` append facts + `TurnControlProjection` fold | gates 读 projection |
| **R3（Wave D+）** | subscriber 纯 fold（可选，ADR-0181 PR-9） | Reducer imperative 仅测试 fixture |

### 4.2 Reducer 保留职责（LCA 控制面）

- `apply_step_advanced` / budget
- `apply_perception` → manifest_digest（idempotency token）
- `apply_skill_route` / `apply_activation`
- `apply_memory`（policy fold，非 memory 层直写）
- `apply_stop` → **先于** `apply_terminal_outcome`（C12）
- `apply_error` / `apply_paused` / `apply_resume`
- `apply_terminal_outcome` → `TerminalOutcome` SSOT（ADR-0077）

### 4.3 从 Reducer 移除的职责

- 作为 **唯一** model tool-call wire 来源（移交 `ModelContextAssembler`）
- 任何仅为了让「模型看到」而写的 state 字段

## 5. Model-visible 运行时收敛（Wave A）

### 5.1 规则 **I-MV-RUNTIME-1**

> 每轮 LLM 请求的 messages 集合，必须等于同 run 同 step 的 `spine.llm.request.header` payload 中记录的 messages；且 `session.derive_messages()` 与 runtime assembler 在 surface 闭集内等价（mod 显式 compaction policy）。

### 5.2 实施要点

1. `lca/cognition/brain/llm_turn/executor.py`：`llm_kwargs["history"]` 改从 bound `Session.derive_messages()` 或注入的 `ModelContextAssembler` 获取。
2. remember/act 路径：tool result 必须以 surface 事件 durable 化（已有 `emit_body_tool_execute_end`；需保证进 Session 单流）。
3. `ModelVisibleHook.capture_pre_llm` 保持：header 捕获为审计 SSOT。
4. Parity 测试：`tests/cognition/test_model_context_parity.py`（新建）对比 assembler 与 fold 重建。

### 5.3 COMPAT

```text
# COMPAT(owner: ADR-0191, from: build_tool_history(state.history),
#   to: ModelContextAssembler.assemble(session),
#   delete_when: rg 'build_tool_history' lca/cognition/ = 0 && parity tests green,
#   forbidden_new_usage: cognition 新代码不得 import build_tool_history)
```

## 6. Durability 与网络中断（Wave A）

### 6.1 三边界 checkpoint（对齐 DSH session-checkpoint-policy）

| 边界 | DSH | LCA 接线点 | 失败语义 |
|---|---|---|---|
| 步开始前 | `agent/pre-step` | loop driver / phase executor pre-step | `CheckpointFailure`，不开下一步 |
| 模型请求前 | `llm/stream` | `execute_llm_turn` 调 adapter 前 | 不 dispatch LLM |
| 工具副作用前 | `tools/execute` | `SafeExecutor` body 执行前 | 不 dispatch tool body |

`SessionCheckpointPolicy.enabled=False` 仅用于测试替换；production profile 默认 `True`。

### 6.2 网络中断状态机

```text
stream 中网络错误
  → adapter 层 retry（瞬时错误，指数退避）
  → 记录 model.failed.v1 / llm.retry 对位（audit，不进 surface）
  → 若最终失败：assistant/message interrupted 或 turn/end error
  → 不通过 state.history.append 修复 transcript
```

**原则**：checkpoint 失败 = fail-closed；log 可能已 append 但未 durable → 依赖 flush；进程 loss → torn tail + repair。

## 7. Resume 与 Recovery 统一（Wave B）

### 7.1 三种场景，一种事实模型

| 场景 | 事实事件 | 恢复入口 |
|---|---|---|
| HIL 等待输入 | `session.checkpoint.v1 { waiting_input }` + 唯一 `approval.persisted.v1` | `recover_live_agent` |
| 进程 crash | open turn in log | `repair_interrupted_turn` + restore |
| 正常 resume | balanced log | `agents.resume` 等价：新 loop + `request/header { reason: resume }` |

### 7.2 `repair_interrupted_turn`（新模块）

路径：`lca/plugins/session/runtime/repair.py`

对齐 DSH `interruptedTurnClosers`：

1. 扫描 open turn（有 `turn/start` 无 `turn/end`）。
2. 对 unmatched tool calls 合成 `tool/result`：
   - `TOOL_NOT_STARTED` — assistant message 有 call 无 `tool/call`
   - `TOOL_OUTCOME_UNKNOWN` — 有 `tool/call` 无 `tool/result`
3. 合成 `step/end`、`turn/end { kind: interrupted }`（仅 cold load append）。
4. **Live session 有 open turn 时拒绝 cold repair**（双写者防护）。

接线：`SessionStore.restore_from_log` 在 fail-closed read 后、construct Session 前调用 repair。

### 7.3 Transport resume 收敛

目标：Transport `resume_run` 读 `recover_live_agent(session.events)`，内存 `RunSession.snapshot` 降为 cache。

不变量（延续 AGENTS.md + ADR-0078）：

- `waiting_input` checkpoint ↔ 恰好一个 unresolved `approval.persisted.v1`
- checkpoint **禁止** `working`
- resume idempotent（已有 transport 测试扩展）

### 7.4 COMPAT

```text
# COMPAT(owner: ADR-0191, from: RunSession in-memory snapshot primary,
#   to: recover_live_agent + Session restore,
#   delete_when: transport resume e2e 不依赖 snapshot 主路径 && rg 'waiting_input' snapshot 主路径 = 0,
#   forbidden_new_usage: 新 resume 逻辑不得只写内存不 append facts)
```

## 8. Session Projections 注册（Wave C）

对齐 DSH `ctx.sessionProjections`：

| Projection key | 输入事件 | 用途 |
|---|---|---|
| `turn_boundary` | turn/step start/end | loop 读 lastTurn；doctor |
| `turn_control` | turn/decision/observation facts | gates / stop / critic |
| `token_usage` | surface + header + usage | 已有 Wave 4 |
| `session_stats` / `session_turn_outline` | 已有 | 保留 |

`AgentStateProjection`（harness）保留为 **窄 recovery 视图**（checkpoint/step），不 expand 为完整 Reducer 语义；完整 control fold 走 `ControlStateFolder`。

## 9. 单流收敛（Wave D）

完成 ADR-0186 PR-3g/3h delete-when：

- `StepTreeFoldDeriver._iter_events` 去掉 Session∪spine 并集
- 所有 durable 事件经 `Session.append` → PersistenceObserver → spine.jsonl
- `EventSpine.append` shim 调用方清零

## 10. 不变量

| ID | 内容 | 测试位置 | 落地 Wave |
|---|---|---|---|
| **I-MV-RUNTIME-1** | 运行时 LLM messages ≡ header fold ≡ derive_messages（surface 闭集） | `tests/cognition/test_model_context_parity.py` | A |
| **I-MV-RUNTIME-2** | cognition 生产路径禁止 `build_tool_history` | `tests/architecture/test_runtime_convergence_invariants.py` | A |
| **I-CHK-1** | executor 调 LLM 前 await `before_model_request` | 同上 + integration | A |
| **I-CHK-2** | SafeExecutor 工具 body 前 await `before_tool_side_effect` | 同上 | A |
| **I-RESUME-1** | cold restore  open turn → repair closers | `tests/plugins/session/test_repair.py` | B |
| **I-RESUME-2** | live open turn 拒绝 cold repair | 同上 | B |
| **I-RESUME-3** | `recover_live_agent` 为 transport/cold restore 权威 | `tests/plugins/session/test_recovery_integration.py` | B |
| **I-RESUME-4** | waiting_input ↔ 唯一 approval（已有，加强 call site） | 已有 + 扩展 | B |
| **I-CONTROL-1** | gates 不读 model assembler 输出作控制输入 | architecture test | C |
| **I-SESSION-1..5** | ADR-0186 不变量 | 已有 | D |

不破坏：C4 Reducer 单写（control）、C11 事件闭集、C12 stop/terminal 顺序、I-FW-SSOT-1、I-MV-1..5。

## 11. PR 切分（Wave A–D）

依赖图：

```text
Wave A (model wire + checkpoint)
  ├─► Wave B (repair + resume 单路径)  [可部分并行]
  ├─► Wave C (projections + Reducer R2)
  └─► Wave D (单流 + ADR-0186 Accepted)
```

| Wave | PR | 目标 | 主要触点 | delete-when |
|---|---|---|---|---|
| **A1** | model context assembler | `ModelContextAssembler` 默认实现；executor 切换 | `llm_turn/executor.py`, `contracts/protocols/session/` | `build_tool_history` cognition 生产 = 0 |
| **A2** | surface production 补齐 | remember/act append surface 一致性 | phase executors, body reflector | parity test green |
| **A3** | checkpoint 接线 | executor + SafeExecutor await policy | `checkpoint_policy`, executor, safe_executor | integration test 证明 fail-closed |
| **B1** | session repair | `repair.py` + tests | `session/runtime/repair.py` | DSH repair 用例对齐 |
| **B2** | restore 集成 | `restore_from_log` 调 repair | `session/runtime/store.py` | cold load e2e |
| **B3** | transport resume | `recover_live_agent` 接线 | `loop_drivers`, registry | snapshot 非主路径 |
| **C1** | TurnControlProjection | gates 迁 fold | `session/projections/` | gates 不读 history 直写 |
| **C2** | RunCommitter 别名 + fact append | remember append turn facts | `reducer.py`, remember phase | — |
| **D1** | 单流 | 删 StepTree 并集 COMPAT | `fold_deriver.py` | COMPAT 块删除 |
| **D2** | 文档 Accepted | 0186 + 0191 状态更新 | docs | — |

## 12. Alternatives considered

### 12.1 删除 Reducer，全面 DSH 化

**否决**。DSH 用 sessionProjections 隐式承担 commit；LCA 的 `CommandEnvelope`、capability C5、declarative TerminalOutcome、HIL 状态机需要显式 commit seam。删除 Reducer 会迫使控制面逻辑散落进 loop 或投影，破坏 C4 与 ADR-0070。

### 12.2 保留 `build_tool_history`，仅加强测试

**否决**。双路径必然 drift；doctor/replay 与 live 不一致违背 ADR-0185「Model-visible ⟺ logged」精神。

### 12.3 用 AgentState 快照做 resume 主路径

**否决**。快照不可审计、不可 fork、与 Session SSOT 冲突；DSH 与 ADR-0186 均选择 log 延续。

### 12.4 在 live session 上 synthetic repair

**否决**。DSH 明确拒绝；双写者 race。Live 由 live agent 关 turn；cold 才 repair。

### 12.5 一次性 big-bang 重写 agent loop

**否决**。ADR-0186/0185 已证明分波 + COMPAT + delete-when 可维护；本 ADR 延续该策略。

## 13. 与现有 ADR 关系

| ADR | 关系 |
|---|---|
| **0186** | **延伸并完成**：Session SSOT 运行时消费方收敛 |
| **0185** | **互补**：runtime assembler 与 fold parity |
| **0189** | **依赖**：derive_messages / fork / surface_op 已 Proposed |
| **0070** | **保留**：Reducer → RunCommitter 演进 |
| **0077** | **保留**：terminal 顺序与 ResumeCursor |
| **0078** | **保留**：approval 与 recover_live_agent |
| **0183** | **不修改**：durable 链仍为 spine.jsonl |
| **0181 PR-9** | **可选远期**：Reducer as subscriber |

## 14. 风险与缓解

| 风险 | 缓解 |
|---|---|
| derive_messages 性能（全 log 扫描） | Session 增量 surface 缓存（0189）；Wave D 优化 |
| ASK_HUMAN resume 答案不在 surface | Wave A2 显式 append user/message with source |
| checkpoint 增加 latency | 仅三边界；async flush 批处理（已有） |
| repair 合成事件与 provider 不兼容 | 对齐 DSH TOOL_* 码；parity 测试 |
| 并行 subagent 撞文件 | worktree / Wave 分目录 |

## 15. 验证协议

```sh
# 本 ADR 骨架（0191 PR-0）
uv run pytest tests/architecture/test_runtime_convergence_invariants.py -q
uv run pytest tests/test_refactor_guards.py::TestAdrIndexMatchesFilesystem -q
./scripts/lca-ops notes-check

# Wave A 完成
uv run pytest tests/cognition/test_model_context_parity.py tests/plugins/session/test_checkpoint_integration.py -q
rg 'build_tool_history' lca/cognition/  # 期望 0（tests 除外）

# Wave B 完成
uv run pytest tests/plugins/session/test_repair.py tests/plugins/session/test_recovery_integration.py -q

# 终态
uv run pytest tests/architecture/test_session_ssot_invariants.py tests/architecture/test_runtime_convergence_invariants.py -q
./scripts/lca-ops e2e timeline  # 冒烟
```

## 16. 实施顺序（subagent 派发）

1. **0191-PR-0**（本提交）：ADR + Note + 架构不变量骨架 + README 索引。
2. **0191-Wave-A**：A1→A2→A3（model context + checkpoint）；可一 agent 顺序执行。
3. **0191-Wave-B**：B1→B2→B3（repair + resume）；可与 Wave A 并行，避免改同一文件。
4. **0191-Wave-C/D**：待 A/B 绿后启动。
