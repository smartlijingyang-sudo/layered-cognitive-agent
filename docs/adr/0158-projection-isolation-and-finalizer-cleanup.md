# ADR-0158：删 reducer 私改 status + 删 final_output 字段 + 删 Result.from_state

## 状态

**Revised — 2026-09-01**(subagent 评审后重做。原 ArtifactClosureProjection Protocol 方案作废)

Supersedes: ADR-0156 §「决策 二」 / 原 ADR-0158 v1

Refines: ADR-0063 §I4 (投影永不回写)、ADR-0070 C4 (Reducer 不私改 status)、ADR-0077 (TerminalOutcome as Sole Terminal Truth)

## 背景

`run_b1294a33e55d` RCA 暴露的真实违反点(subagent 评审逐行核对 `lca/runtime/reducer.py` / `lca/runtime/result_finalizer.py` / `lca/harness/projection/agent_state.py` / `lca/contracts/models/core/result.py`):

| 真实违反 | 文件:行 | 违反的宪法 |
|---|---|---|
| `apply_artifact_closure` 末尾 `state.status = COMPLETED` | `lca/runtime/reducer.py:285` | ADR-0070 C4、ADR-0077 |
| `apply_artifact_closure` 把 closure 文本塞 `state.final_output` | `lca/runtime/reducer.py:280-283` | ADR-0063 §I4 |
| finalizer 调用顺序错(closure 在 error/paused 之前) | `lca/runtime/result_finalizer.py:48-55` | ADR-0070 C4 |
| `projection/agent_state.py` 直接写 `state.final_output` | `lca/harness/projection/agent_state.py:114` | ADR-0063 §I4、ADR-0070 C4 |
| `Result.from_state(state)` 把 `state.final_output` 塞 Result.output | `lca/contracts/models/core/result.py:98` | ADR-0077 §三 |
| transport 层 `artifact_closure` 不读 `session.status` | `lca/plugins/transport/webserver/handlers/runs/observability/artifact_closure.py:18-50` | C7 控制/观察分离 |

## 第一性原理:已有 seam 已经闭合

subagent 评审验证:

1. **Reducer Protocol 已含正确 seam**:
   - `apply_terminal_outcome(state, stop, *, plan_ref, journal_seq_end, resume_cursor=None)`(`lca/contracts/protocols/state/reducer.py:69-82`)已构造 TerminalOutcome
   - ADR-0077 已规定"Reducer 仍是唯一实体构造终态"
   - **不需要新建 ArtifactClosureProjection Protocol** —— 旧 `ArtifactClosure` Protocol 已是"读 workspace → 输出 closure 文本"的纯 projection,语义正确

2. **`OutcomeProjection._terminal_output` 已读 `TerminalOutcome.final_output_ref`**(`lca/runtime/result_projection.py:168-172`):
   - Result.output 来源已经是 TerminalOutcome,不是 state.final_output
   - ADR-0158 §VI 提议"改读 final_output_ref"是**已存在的事实**

3. **`TerminalOutcome.final_output_ref` 已是 typed ref**(`lca/contracts/models/core/terminal_outcome.py:152-154`):
   - TextRef / ArtifactRef / StructuredRef 三类 resolver 已实现
   - 真实需要修的是 reducer 在 `apply_terminal_outcome` 里 handoff 占位 `"handoff completed"` 这处污染(`reducer.py:147-158`)

## 原方案错在哪里

ADR-0158 v1 错误地:

- 新建 `ArtifactClosureProjection` Protocol + `ClosureProjection` dataclass(与旧 `ArtifactClosure` 同语义,只是改名换汤)
- 提议"旧 Protocol deprecated 保留"——同时存在两个 seam 是 runtime 双债
- 引用 `StopDecision.response_text` 字段——**该字段根本不存在**(`stop.py:29-44` 真实字段是 `final_output` 或 `failure.message`)
- 引用 `interpretation.workspace` 字段——**该字段不存在**(`outcome_projection.py:32-46` 真实字段是 `state` / `artifact` / `visits`)
- 把"`state.final_output` 字段保留但语义收窄"作为方案——空壳字段就是垃圾
- 把不存在的 `scripts/check_no_state_outline_reducer.py` 当作已有工具

总计 5 个不存在的引用,3 个新文件,0 个真实修复。

## 决策(纯减法,零新 Protocol)

### 一、删 reducer 私改 status 的那 1 行

`lca/runtime/reducer.py:285`:

```diff
 def apply_artifact_closure(self, state: AgentState, closure: str) -> AgentState:
     if not closure:
         return state
     if state.final_output:
         if closure.strip() not in state.final_output:
             state.final_output = state.final_output.rstrip() + "\n\n" + closure
     else:
         state.final_output = closure
-    if state.status == TaskStatus.WORKING:
-        state.status = TaskStatus.COMPLETED
     return state
```

### 二、删 finalizer 的 closure → final_output 折叠

`lca/runtime/result_finalizer.py:48-55`:

```diff
 async def finalize(self, *, interpretation, plan_ref, journal_sequence):
     final_state = interpretation.state
     outcome = interpretation.outcome
     await self._hooks.trigger("on_complete", final_state)

+    # status 收敛先于 closure 派生
     if outcome.kind == "failed":
         final_state = self._reducer.apply_error(final_state, outcome.as_exception())
     elif outcome.kind == "paused":
         final_state = self._reducer.apply_paused(final_state, outcome.cursor)

-    # closure 折叠移出 reducer 流
-    closure_text = self._artifact_closure.synthesize(fallback=...)
-    if closure_text:
-        final_state = self._reducer.apply_artifact_closure(final_state, closure_text)

     # terminal 折叠:Reducer 仍是唯一终态写者
     terminal_outcome = self._reducer.apply_terminal_outcome(...)
     return await self._result_projection.project(final_state, terminal_outcome=terminal_outcome, ...)
```

closure 改为由 `ArtifactClosure` (旧 Protocol) emit 到 progress 通道(走 ADR-0157 ProgressStream,若落地)或仅留作 transport 层 projection。

### 三、删 `projection/agent_state.py` 直接写 state

`lca/harness/projection/agent_state.py:114`:

```diff
- state.final_output = data["answer"]
```

改为:

```diff
+ # final_output 不再属于 AgentState;terminal 答案走 TerminalOutcome.final_output_ref
```

### 四、删 `AgentState.final_output` 字段

`lca/contracts/models/core/state.py:110`:

```diff
- final_output: Any | None = None
```

所有读取方迁到 `TerminalOutcome.final_output_ref` 或 `Result.output`(由 `_terminal_output` 解析)。

### 五、删 `Result.from_state(state)`

`lca/contracts/models/core/result.py:98` —— ADR-0077 §三「Result 只读 TerminalOutcome 与 projection」兑现。

### 六、删 `DefaultReducer.apply_artifact_closure` 方法

`lca/runtime/reducer.py:272-285` 整段删除;`lca/contracts/protocols/state/reducer.py:100-103` Protocol 同步删除。

### 八、`DefaultStopPolicy._budget_exhausted_decision` 改用 `decision.final_output` 而非借 `artifact_closure`

`lca/plugins/phase_graph/stop_policy.py` 不再借用 `self._artifact_closure.synthesize()`,改为 `decision = StopDecision(reason="budget_exhausted", final_output=f"任务在 {policy.max_attempts} 次尝试后仍未完成,最后一轮错误:{last_error}", ...)`。

### 九、`artifact_closure.py` transport 层读 `session.status`

`lca/plugins/transport/webserver/handlers/runs/observability/artifact_closure.py:18-50` 在 `emit_artifact_closure_if_needed` 入口先读 `session.status.value`,仅在 `COMPLETED` / `DEGRADED` 时发 answer channel。**建议把判断提前到 `terminalizer.py:51` 的 caller**而非 transport 内部。

### 十、删 reducer handoff 占位污染

`lca/runtime/reducer.py:147-158` `apply_terminal_outcome` 在 `kind == COMPLETED and output_text == ""` 时写 `"handoff completed"` 占位 —— 这也是 projection 污染。改为 `final_output_ref = None`,由 result_projection 投影时输出空。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| ADR-0063 §I4 兑现 | 投影不再回写 state;`state.final_output` 字段删除 | 所有读 `state.final_output` 的代码需迁移 |
| ADR-0070 C4 兑现 | Reducer 不私改 status 终态;reducer.py:285 删一行 | `ArtifactClosureDeltaHandler` 注册项同步删除 |
| ADR-0077 兑现 | TerminalOutcome 是唯一终态;Result.from_state 删除 | legacy 读取方全部迁移 |
| run 状态一致性 | failed / paused / canceled 不再推 answer channel | transport 层加 session.status 判断 |
| **新增代码量** | **0** | — |
| **删除代码量** | ~80 行(reducer 方法 + finalizer 折叠 + Result.from_state + state 字段) | — |
| **新增 Protocol** | **0** | — |
| **新增 Plugin** | **0** | — |
| **lint 脚本** | **0**(无需新增;现有 delta_handler_registry 已覆盖) | — |

## 替代方案(已否决)

| 方案 | 否决理由 |
|---|---|
| 新建 ArtifactClosureProjection Protocol + ClosureProjection dataclass | 与旧 ArtifactClosure 同语义,只是改名换汤;运行时双债 |
| `state.final_output` 字段保留"语义收窄" | 空壳字段就是垃圾,选 A 删 |
| `scripts/check_no_state_outside_reducer.py` 新 lint | 现有 delta_handler_registry 已覆盖 reducer 一致性;加新 lint 是双保险但非必要 |

## 验证约束(机械可执行)

```bash
# 1. Reducer Protocol 不再有 apply_artifact_closure
uv run pytest tests/runtime/test_reducer_protocol_surface.py -v

# 2. Reducer.apply_artifact_closure 已删除
uv run pytest tests/runtime/test_reducer.py -v

# 3. AgentState 不再有 final_output 字段
uv run pytest tests/contracts/test_agent_state_shape.py -v

# 4. Result 不再有 from_state(state) 工厂
uv run pytest tests/contracts/test_result_no_from_state.py -v

# 5. failed 路径不发 answer closure
uv run pytest tests/runtime/test_finalizer_failed_no_answer.py -v

# 6. artifact_closure transport 读 session.status
uv run pytest tests/transport/webserver/handlers/runs/test_artifact_closure_status_gate.py -v

# 7. delta_handler_registry 不再有 artifact_closure 注册项
uv run pytest tests/plugins/providers/act/test_delta_handler_registry.py -v
```

## 删除清单

| 删除位置 | 删除内容 |
|---|---|
| `lca/contracts/protocols/state/reducer.py:100-103` | `apply_artifact_closure` Protocol 方法 |
| `lca/runtime/reducer.py:272-285` | `apply_artifact_closure` 实现 |
| `lca/runtime/reducer.py:285` | `state.status = TaskStatus.COMPLETED` 副作用 |
| `lca/runtime/reducer.py:147-158` | `apply_terminal_outcome` handoff 占位写入 |
| `lca/runtime/result_finalizer.py:50-55` | `apply_artifact_closure` 调用 |
| `lca/contracts/models/core/state.py:110` | `AgentState.final_output` 字段 |
| `lca/contracts/models/core/result.py:98` | `Result.from_state(state)` 工厂 |
| `lca/harness/projection/agent_state.py:114` | `state.final_output = data["answer"]` 直接写 |
| `lca/plugins/providers/act/delta_handlers.py:194-203` | `ArtifactClosureDeltaHandler` 整段 |
| `lca/plugins/providers/act/delta_handler_registry.py:58` | `artifact_closure` 注册项 |
| `lca/plugins/phase_graph/stop_policy.py` | `_artifact_closure.synthesize()` 借用 |

## 修改清单

| 修改位置 | 修改内容 |
|---|---|
| `lca/plugins/phase_graph/stop_policy.py:_budget_exhausted_decision` | `decision.final_output = f"任务在 {policy.max_attempts} 次尝试后..."`(真实字段名) |
| `lca/plugins/transport/webserver/handlers/runs/observability/artifact_closure.py:18-50` | 入口读 `session.status.value`,仅在 COMPLETED/DEGRADED 时发 answer |
| 所有 `state.final_output` 读取点 | 迁移至 `terminal_outcome.final_output_ref` 解析或 `result.output` |

## 新增清单

无新增 Protocol / Plugin / 字段 / 工厂 / lint 脚本。

## 落地顺序

3 个 commit:

1. commit 1:删 reducer.py:285 status 副作用;删 finalizer 中 `apply_artifact_closure` 调用;artifact_closure transport 读 session.status;`delta_handler_registry` 移除 `artifact_closure` 注册项。
2. commit 2:删 `AgentState.final_output` 字段;删 `Result.from_state`;删 reducer.handoff 占位写入;所有读取方迁移。
3. commit 3:`stop_policy._budget_exhausted_decision` 改用 `decision.final_output`(真实字段名)。

每步跑 `tests/runtime/test_reducer_protocol_surface.py tests/runtime/test_reducer.py tests/contracts/test_agent_state_shape.py tests/contracts/test_result_no_from_state.py`。

## 风险

- **风险 1**:`AgentState.final_output` 字段删除涉及所有外部 plugin / LobeHub `result.output` 读取方,需全局 grep + 迁移。**缓解**:加 `tests/contracts/test_agent_state_shape.py` 守门;CI 上线。
- **风险 2**:`Result.from_state` 删除影响所有 `result = Result.from_state(s)` 调用方。**缓解**:`tests/contracts/test_result_no_from_state.py` 守门;`grep -rn Result.from_state lca/` 全量迁移。
- **风险 3**:`ArtifactClosureDeltaHandler` 整段删除需要 `delta_handler_registry` 同步移除注册项,否则 `test_delta_handler_registry_completeness` 会爆。**缓解**:commit 1 同步处理。