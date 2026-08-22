# ADR 74/75 声明式运行切换 Implementation Plan (Refined)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Refinement note:** 本版本基于代码实地审计，修正了初步 plan 中与实际接口不符的契约。主要修正点见末尾 §审计修正清单。

**Goal:** 让所有生产 Agent run、暂停/恢复、控制投稿和效果执行都由 ADR-0074 的 `CompiledRunPlan` 与 ADR-0075 的 `PhaseGraph` 驱动，并删除可达的旧 `_loop`、v1 composer fallback 和 legacy-authoritative shadow path。

**Architecture:** 保留六个认知语义契约及 MTK 不变量，但把 checkpoint、pause/resume、失败收口和控制贡献纳入 `GenericPlanInterpreter` 的标准执行状态。`CognitiveRuntime` 仅创建初始 state 并委托声明式 driver；driver 从 plan、Journal、Reducer、Effect Gateway 和 checkpoint store 恢复或推进同一份图。任何不含可验证声明式绑定的生产 Profile 在启动前失败，不能回落到旧循环。

**Tech Stack:** Python 3.11、dataclasses、Pydantic、Cordis、pytest、ruff、mypy、import-linter、vulture。

**Spec:** `docs/adr/0074-plugin-everything-trimmed-implementation.md`、`docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md`、`docs/specs/declarative-phase-graph-spec.md`、`docs/adr/0075-implementation-audit.md`、`docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`。

## Global Constraints

- 不增删 `perceive`、`think`、`act`、`reflect`、`remember`、`stop` 六个语义 phase；仅把其实现、贡献、连边和恢复语义纳入已验证的 `PhaseGraph`。
- `Reducer` 是唯一 `AgentState` writer；插件只返回 `RunDelta`、`RunFact`、`PhaseResult` 或其他协议化输出。
- 所有模型可见事实、控制 verdict、暂停/失败决定和 effect receipt 经 Journal 提交；不得引入第二事实源。
- 所有外部副作用均经 `CommandEnvelope → EffectGateway → receipt → Journal`；effect handler 必须落实幂等键去重，不仅检查 key 是否存在。
- 子 scope/agent/artifact grant 必须是父 grant 的子集；计划、插件或恢复逻辑不得扩大权限。
- Runtime、Assembler、Gateway、Composer 和 Driver 不得按 plugin ID、类名、工具名、`simple` 或 `default` 做业务分派。
- 默认生产 Profile 缺少完整、有效、声明式 `CompiledRunPlan` 时必须 fail-closed；不得回落到 `CognitiveRuntime._loop` 或 v1 composer key。
- 删除的范围仅限**生产认知运行与装配路径**。历史 Journal reader、外部 OpenAI 兼容协议、磁盘数据读取兼容和测试 fixture 不在本计划的删除范围内。
- 每个生产代码变更遵循 RED → GREEN → REFACTOR；先观察到对应测试因缺少行为而失败，再写最小实现。
- 提交前必须执行 `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest && uv run vulture lca --min-confidence 80`，不得用 `--no-verify` 绕过门禁。

---

## 0. 事实基线与切换定义

ADR-0074 的 tracker 已记录 17/17 交付项完成，包括 `CompiledRunPlan`、plan-bound assembly、`plan_ref × Journal`、`CommandEnvelope` 与控制数据面；ADR-0075 默认 `run()` 已通过 `DeclarativeRuntimeDriver → GraphAssembler → GenericPlanInterpreter` 运行。[1] [2] 然而 `CognitiveRuntime.resume()` 仍固定调用 `_loop()`，而 `_loop()` 仍拥有 hard-coded 六阶段、`DefaultControlPolicyEngine`、checkpoint、approval pause 和 error path。`plan_binding.py` 仍对 `not plan.is_declarative` 选择 v1 `composer.*` candidates；这些是本次真正要切除的生产双轨。[3] [4]

| 生产能力 | 当前主路径 | 旧路径残留 | 本计划完成定义 |
|---|---|---|---|
| 初始 run | 具备 plan 和 phase executors 时走声明式 driver | 缺 plan/executors 时回退 `_loop()` | 无有效 declarative plan 即启动失败；`_loop` 不再存在 |
| Pause / resume | legacy `_loop` 可写 snapshot 并 resume | `resume()` 永远回到 `_loop()` | snapshot 记录 plan/node/visits/artifacts；resume 重入同一图 |
| 控制 | plan 可编译 control entries | 旧循环仍调用 `DefaultControlPolicyEngine` | govern contribution 在解释器中产生标准终端/改写/暂停结果 |
| Composer | declarative plan 从 capability bindings 找 composer | 非 declarative plan 可尝试 v1 composer keys | 仅已声明 binding 可组装；缺 binding fail-closed |
| Effects | declarative Act/Remember 已经 mint envelope | 旧 Body 直接执行仍在 `_loop()` | Gateway 是唯一 body/memory effect caller；handler 落实持久幂等 |
| Shadow / dual write | diagnostics 组件仍可执行 legacy-authoritative 比较 | legacy result 仍为 authoritative | 删除生产 shadow executor；保留离线 trace 比较工具（不执行 production run） |

## 1. 目标文件结构

| 文件 | 任务后的唯一职责 |
|---|---|
| `lca/contracts/protocols/declarative_phase_graph.py` | 声明不可变的 phase-run cursor、checkpoint payload、标准暂停/失败 outcome；保持为纯数据和 Protocol 定义。 |
| `lca/harness/declarative/interpreter.py` | 推进、持久化并恢复一份已验证 `ExecutablePlan`；统一贡献 verdict、效果 receipt、错误和安全边界。 |
| `lca/layer2_runtime/declarative_runtime.py` | 提供 runtime-backed Journal、EffectGateway、checkpoint store 与 `DeclarativeRuntimeDriver.run/resume`；不认识具体业务 phase。 |
| `lca/layer2_runtime/runtime_loop.py` | 保留 `CognitiveRuntime` 作为 thin public façade：创建 state、要求 compiled plan、转发 run/resume；删除 `_loop`、`evaluate_control`、checkpoint 私有实现及 `DefaultControlPolicyEngine` 依赖。 |
| `lca/plugins/composer/plan_binding.py` | 仅从 `CompiledRunPlan.capability_bindings` 解析 composer；删除 v1 `not plan.is_declarative` 分支。 |
| `lca/plugins/loop_drivers/cognitive.py` 与 `gateway/runs/loop_drivers.py` | 只启动 plan-bound runnable；删除 legacy agent-loop factory 和 shadow-authoritative 执行选择。 |
| `lca/layer2_runtime/control_policies.py`、`lca/harness/command/dual_write.py` | 在所有调用迁移后删除；其行为改由 PluginSpec contribution、effect handler 和离线 trace comparator 覆盖。 |
| `tests/declarative/`、`tests/architecture/`、`tests/layer2_runtime/`、`tests/gateway/` | 以 e2e、resume、failure、AST/路径守卫证明没有可达旧流程。 |
| `docs/adr/0075-implementation-audit.md`、`docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md`、`docs/adr/README.md` | 基于验收证据更新 ADR-0075 状态、审计结论和迁移说明；不回写已归档 ADR 的历史事实。 |

## 2. 可执行任务

### Task 1: 锁定"无旧流程"目标与现有行为的 characterization 基线

**Files:**
- Create: `tests/declarative/test_cutover_characterization.py`
- Modify: `tests/declarative/test_default_profile_architecture.py`
- Modify: `tests/architecture/test_new_architecture_closure.py`
- Modify: `lca/layer2_runtime/runtime_loop.py`（仅在后续 GREEN 阶段）

**Interfaces:**
- Consumes: `CognitiveRuntime.run(task, ctx, *, max_steps, max_wall_clock_seconds, agent_role) -> Result` 与 `CognitiveRuntime.resume(snapshot, input, max_steps) -> Result`。
- Produces: 对默认 Profile 的初始 run、approval resume、错误恢复和缺 binding 四类行为的可执行切换合同。

**当前代码事实（审计确认）：**
- `runtime_loop.py:109-154` — `run()` 在 `compiled_plan is not None and phase_executors` 存在时委托 `DeclarativeRuntimeDriver.run()`，否则回落 `self._loop()`。
- `runtime_loop.py:156-183` — `resume()` 永远调用 `self._loop()`，无视 `compiled_plan`。
- `runtime_loop.py:217-331` — `_loop()` 仍包含完整硬编码六阶段、`DefaultControlPolicyEngine` 调用、`_checkpoint` 和 `ApprovalPendingError` 处理。

- [ ] **Step 1: 写失败的默认 run 与 resume 同路由测试。**

```python
@pytest.mark.asyncio
async def test_default_profile_run_and_resume_never_invoke_legacy_loop(monkeypatch):
    runtime, snapshot = await build_paused_default_runtime()

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy CognitiveRuntime._loop is reachable")

    monkeypatch.setattr(runtime, "_loop", forbidden, raising=False)
    assert (await runtime.run("complete task")).status is not None
    assert (await runtime.resume(snapshot, input="approved")).status is not None
```

> **注意：** `build_paused_default_runtime()` 必须在 `tests/declarative/conftest.py` 中实现，使用已存在的 `lca/harness/profile/boot.py:boot_profile()` 启动默认 `web-standard.yaml`，并通过 `lca/layer4_app/spawn.py:spawn_agent()` 获得带 `compiled_plan` 的 `CognitiveRuntime`。

- [ ] **Step 2: 运行测试，确认当前 `resume()` 因固定调用 `_loop()` 而失败。**

Run: `uv run pytest --no-cov tests/declarative/test_cutover_characterization.py::test_default_profile_run_and_resume_never_invoke_legacy_loop -q`

Expected: FAIL，异常包含 `legacy CognitiveRuntime._loop is reachable`。

- [ ] **Step 3: 写失败的 fail-closed 与源代码闭包测试。**

```python
def test_runtime_requires_a_valid_declarative_plan():
    runtime = CognitiveRuntime(..., compiled_plan=None, phase_executors={})
    with pytest.raises(DeclarativeValidationError, match="declarative"):
        asyncio.run(runtime.run("task"))


def test_runtime_module_has_no_legacy_loop_or_policy_engine_reference():
    source = Path("lca/layer2_runtime/runtime_loop.py").read_text()
    assert "def _loop(" not in source
    assert "DefaultControlPolicyEngine" not in source
    assert "return await self._loop" not in source
```

- [ ] **Step 4: 运行测试，确认它们在删除前失败。**

Run: `uv run pytest --no-cov tests/declarative/test_cutover_characterization.py -q`

Expected: FAIL，原因分别是 fallback 仍返回结果、`_loop` 与 `DefaultControlPolicyEngine` 仍存在。

- [ ] **Step 5: 不修改生产代码，只提交 red-test 基线。**

```bash
git add tests/declarative/test_cutover_characterization.py tests/declarative/test_default_profile_architecture.py tests/architecture/test_new_architecture_closure.py
git commit -m "test(adr-075): characterize declarative cutover boundaries"
```

### Task 2: 为解释器引入可持久、可恢复的 phase-run cursor

**Files:**
- Modify: `lca/contracts/protocols/declarative_phase_graph.py`
- Modify: `lca/harness/declarative/interpreter.py`
- Create: `tests/declarative/test_interpreter_checkpoint_resume.py`
- Modify: `tests/declarative/test_phase_graph.py`

**Interfaces:**
- Consumes: 已验证的 `ExecutablePlan`、当前 State、`PhaseInput`、`PhaseRunCursor | None`。
- Produces: `PhaseRunCursor`，包含 `plan_ref`、`node_id`、`visit_counts`、`edge_counts`、`artifacts`、`causation_refs`、`budget_snapshot`；所有字段可序列化且无 live Context。

**当前代码事实（审计确认）：**
- `interpreter.py:102-211` — `GenericPlanInterpreter.run()` 在局部维护 `visit_counts`、`edge_counts` 和 `artifact_map`，但没有 `PhaseRunCursor` 暴露。
- `interpreter.py:79-85` — `InterpretationResult` 没有 `cursor` 字段。
- `interpreter.py:88-111` — 构造器只接收 `journal`、`effect_gateway`、`reducer`；没有 `checkpoint_store` 注入。

- [ ] **Step 1: 写失败的 cursor round-trip 和续跑测试。**

```python
@pytest.mark.asyncio
async def test_interpreter_resumes_from_saved_cursor_without_reexecuting_completed_effect():
    executable, state, gateway = executable_with_effectful_act()
    interpreter = GenericPlanInterpreter(effect_gateway=gateway, ...)
    first = await interpreter.run(executable, state=state)
    cursor = first.cursor
    assert cursor is not None
    assert cursor.node_id == "reflect.main"  # 完成 act.main 后停在 reflect.main 之前

    resumed = await interpreter.resume(executable, state=first.state, cursor=cursor)

    assert gateway.body_act_calls == 1  # resume 不重放已确认的 act effect
    assert resumed.terminal_node == "stop.main"
```

- [ ] **Step 2: 运行测试，确认 `cursor` 和 `resume` 尚不存在。**

Run: `uv run pytest --no-cov tests/declarative/test_interpreter_checkpoint_resume.py::test_interpreter_resumes_from_saved_cursor_without_reexecuting_completed_effect -q`

Expected: FAIL，`AttributeError: 'InterpretationResult' object has no attribute 'cursor'`。

- [ ] **Step 3: 以纯数据实现 cursor 和解释器恢复入口。**

```python
@dataclass(frozen=True, slots=True)
class PhaseRunCursor:
    plan_ref: str
    node_id: str
    visit_counts: tuple[tuple[str, int], ...]
    edge_counts: tuple[tuple[str, str, int], ...]
    artifacts: Mapping[str, Any]
    causation_refs: tuple[str, ...]
    budget_snapshot: Mapping[str, Any]
```

**实现要点（对齐现有 `interpreter.py` 结构）：**

1. 在 `declarative_phase_graph.py` 新增 `PhaseRunCursor` dataclass（frozen、slots、JSON 可序列化）。
2. 在 `InterpretationResult` 新增 `cursor: PhaseRunCursor | None` 字段。
3. 把 `run()` 方法拆为 `_drive()` 内部循环，`run()` 构造初始 cursor 后调用 `_drive()`。
4. 新增 `resume(executable, *, state, cursor, ...)` 方法，验证 `cursor.plan_ref == compiled_run_plan_ref(executable.plan)` 后从 `cursor.node_id` 开始 `_drive()`。
5. 在每步循环中：commit fact → apply delta → effect receipt → 才推进 cursor。effect receipt 未确认时不得推进。
6. 每次进入节点或选择边后，生成新的 `PhaseRunCursor` 放入 `InterpretationResult.cursor`。

- [ ] **Step 4: 运行 cursor、phase graph 和 plan hash 测试。**

Run: `uv run pytest --no-cov tests/declarative/test_interpreter_checkpoint_resume.py tests/declarative/test_phase_graph.py tests/plan/test_plan_hash_determinism.py -q`

Expected: PASS。

- [ ] **Step 5: 格式化、静态检查并提交。**

```bash
uv run ruff check --fix lca/contracts/protocols/declarative_phase_graph.py lca/harness/declarative/interpreter.py tests/declarative/
uv run ruff format lca/contracts/protocols/declarative_phase_graph.py lca/harness/declarative/interpreter.py tests/declarative/
uv run mypy lca/contracts/protocols lca/harness/declarative
git add lca/contracts/protocols/declarative_phase_graph.py lca/harness/declarative/interpreter.py tests/declarative/
git commit -m "feat(adr-075): persist declarative phase cursors"
```

### Task 3: 将 pause、错误和效果不确定性收敛为可恢复的声明式 outcome

**Files:**
- Modify: `lca/contracts/protocols/declarative_phase_graph.py`
- Modify: `lca/harness/declarative/interpreter.py`
- Modify: `lca/layer2_runtime/declarative_runtime.py`
- Create: `tests/declarative/test_runtime_outcomes.py`

**Interfaces:**
- Consumes: `PhaseResult`、contribution verdict、`ApprovalPendingError`、effect handler exception、`CommandEnvelope`。
- Produces: `DeclarativeRunOutcome(kind: Literal["completed", "paused", "failed", "effect_uncertain"], cursor: PhaseRunCursor | None, stop: StopDecision, error_fact: RunFact | None)`。

**当前代码事实（审计确认）：**
- `interpreter.py:247-250` — `_apply_post_contributions` 的 govern 分支调用 `_verdict_allows()`（布尔判定），deny 时抛 `DeclarativeValidationError("RT-002")`。没有 `pause`/`rewrite`/`defer` 语义。
- `interpreter.py:176-184` — effect gateway 执行后直接 commit observation，没有 receipt 不匹配处理。
- `declarative_runtime.py:172-193` — `DeclarativeRuntimeDriver.run()` 直接返回 `Result.from_state()`，没有 outcome 映射。

- [ ] **Step 1: 写失败的 pause 和 effect-uncertain 测试。**

```python
@pytest.mark.asyncio
async def test_govern_pause_returns_resumable_outcome_and_journal_fact():
    outcome = await run_with_govern_verdict({"verdict": "pause", "reason": "approval"})
    assert outcome.kind == "paused"
    assert outcome.cursor is not None
    assert outcome.stop.should_stop is True
    assert any(f.kind == "run.paused" for f in outcome.facts)

@pytest.mark.asyncio
async def test_receipt_mismatch_stops_without_reissuing_the_effect():
    outcome = await run_with_mismatched_receipt()
    assert outcome.kind == "effect_uncertain"
    assert outcome.cursor is not None
    assert outcome.stop.should_stop is True
```

- [ ] **Step 2: 运行测试，确认当前 interpreter 把非 allow govern 统一抛为 `RT-002`，且未产生恢复 outcome。**

Run: `uv run pytest --no-cov tests/declarative/test_runtime_outcomes.py -q`

Expected: FAIL，pause 不存在或报 `RT-002`；receipt mismatch 仅抛异常。

- [ ] **Step 3: 实现标准 outcome 与错误映射。**

**实现要点（对齐现有 interpreter 结构）：**

1. 在 `declarative_phase_graph.py` 新增 `DeclarativeRunOutcome` dataclass。
2. 在 `interpreter.py` 中：
   - 将 `_verdict_allows()` 替换为 `_classify_verdict()` → 返回 `Literal["allow", "deny", "rewrite", "pause", "stop", "defer"]`。
   - `govern` 的 `deny` → 生成 `run.denied` fact 并返回 failed outcome（不抛 `RT-002`）。
   - `govern` 的 `pause` → 生成 `run.paused` fact、保存 cursor、返回 paused outcome。
   - `govern` 的 `rewrite` → 替换 `PhaseResult.payload` 中的 decision_ref，继续执行。
   - Effect gateway 抛 `DeclarativeValidationError("RT-003")` → 返回 `effect_uncertain` outcome，保存 cursor。
   - `ApprovalPendingError` → 返回 paused outcome。
   - 其他 `BaseException` → 生成 `run.failed` fact，返回 failed outcome。
3. 在 `declarative_runtime.py` 的 `DeclarativeRuntimeDriver.run()` 中把 outcome 映射为 `Result`：

```python
result = Result.from_state(outcome.state)
result.extra.update({
    "phase_cursor": outcome.cursor,
    "stop": outcome.stop,
    "outcome": outcome.kind,
})
return result
```

- [ ] **Step 4: 运行测试并提交。**

```bash
uv run pytest --no-cov tests/declarative/test_runtime_outcomes.py tests/declarative/test_interpreter_checkpoint_resume.py tests/declarative/test_runtime_driver.py -q
git add lca/contracts/protocols/declarative_phase_graph.py lca/harness/declarative/interpreter.py lca/layer2_runtime/declarative_runtime.py tests/declarative/
git commit -m "feat(adr-075): model declarative pause and failure outcomes"
```

### Task 4: 让声明式 driver 成为 checkpoint/resume 的唯一入口

**Files:**
- Modify: `lca/layer2_runtime/declarative_runtime.py`
- Modify: `lca/layer2_runtime/runtime_loop.py`
- Modify: `lca/layer3_agent/cognitive_agent.py`
- Modify: `lca/layer4_app/harness_live.py`
- Create: `tests/declarative/test_driver_resume.py`
- Modify: `tests/declarative/test_default_profile_architecture.py`

**Interfaces:**
- Consumes: `StateSnapshot.state_ref`、持久化 `PhaseRunCursor`、同一 `CompiledRunPlan.plan_ref`。
- Produces: `DeclarativeRuntimeDriver.resume(snapshot, input) -> Result`，以及 `CognitiveRuntime.resume()` 的纯委托实现。

**当前代码事实（审计确认）：**
- `declarative_runtime.py:154-193` — `DeclarativeRuntimeDriver` 只有 `run(state)`，没有 `resume()`。
- `runtime_loop.py:156-183` — `CognitiveRuntime.resume()` 构造 answer turn 后直接调 `self._loop()`。
- `cognitive_agent.py:156` — `CognitiveAgent.resume()` 委托 `self._runtime.resume()`。
- `harness_live.py` — `LiveAgentHandle.resume()` 调用 `runtime.resume()`。

- [ ] **Step 1: 写失败的 paused-default-profile resume 测试。**

```python
@pytest.mark.asyncio
async def test_runtime_resume_uses_the_snapshot_plan_and_declarative_driver(monkeypatch):
    runtime, paused = await build_default_profile_paused_run()
    monkeypatch.setattr(runtime, "_loop", AsyncMock(side_effect=AssertionError("old loop")), raising=False)

    result = await runtime.resume(paused.extra["state_snapshot"], input="approved")

    assert result.extra["outcome"] in {"completed", "paused"}
    assert result.extra["plan_ref"] == runtime.compiled_plan.plan_hash
```

- [ ] **Step 2: 运行测试，确认现有 `CognitiveRuntime.resume()` 固定回到 `_loop()`。**

Run: `uv run pytest --no-cov tests/declarative/test_driver_resume.py::test_runtime_resume_uses_the_snapshot_plan_and_declarative_driver -q`

Expected: FAIL，断言触发 `old loop`。

- [ ] **Step 3: 实现 runtime-owned checkpoint store 与 driver resume。**

```python
@dataclass(frozen=True, slots=True)
class DeclarativeCheckpoint:
    state_snapshot: StateSnapshot
    cursor: PhaseRunCursor
    plan_ref: str

# In DeclarativeRuntimeDriver:
async def resume(self, checkpoint: DeclarativeCheckpoint, *, input: object | None = None) -> Result:
    from lca.contracts.protocols.plan import compiled_run_plan_ref
    if checkpoint.plan_ref != compiled_run_plan_ref(self._plan):
        raise DeclarativeValidationError("RT-004", "checkpoint plan_ref differs from bound plan")
    state = await self._state_store.load(checkpoint.state_snapshot.state_ref)
    if input is not None:
        state = self._apply_human_input(state, input)
    executable = GraphAssembler().assemble(self._plan, MappingRestrictedScope(self._phase_executors))
    interpretation = await GenericPlanInterpreter(
        journal=RuntimeJournalCommitter(),
        effect_gateway=RuntimeEffectGateway(self._capabilities),
        reducer=ReducerDeltaAdapter(self._reducer),
    ).resume(executable, state=state, cursor=checkpoint.cursor, ...)
    return self._materialize_result(interpretation)
```

**在 `runtime_loop.py` 中：**
- `run()` — 删除 `if self.compiled_plan is not None and self.phase_executors:` 的条件回落。改为：若 `compiled_plan is None or not phase_executors`，抛 `DeclarativeValidationError("RT-005", ...)`。否则委托 `DeclarativeRuntimeDriver.run()`。
- `resume()` — 保留 answer turn 构造逻辑，但把 `self._loop()` 替换为 `DeclarativeRuntimeDriver(...).resume(checkpoint, input=input)`。从 `state.extra` 中提取 `phase_cursor` 和 `plan_ref`，构造 `DeclarativeCheckpoint`。

- [ ] **Step 4: 运行 driver、gateway 和 e2e resume 测试。**

Run: `uv run pytest --no-cov tests/declarative/test_driver_resume.py tests/declarative/test_runtime_driver.py tests/declarative/test_default_profile_architecture.py tests/e2e/test_full_run_replay.py tests/test_run_*.py -q`

Expected: PASS。

- [ ] **Step 5: 提交。**

```bash
git add lca/layer2_runtime/declarative_runtime.py lca/layer2_runtime/runtime_loop.py lca/layer3_agent/cognitive_agent.py lca/layer4_app/harness_live.py tests/declarative/ tests/e2e/
git commit -m "feat(adr-075): route checkpoint resume through declarative driver"
```

### Task 5: 把 ADR-0074 控制面从旧 policy engine 迁入 phase contribution 图

**Files:**
- Modify: `lca/harness/declarative/interpreter.py`
- Modify: `lca/harness/declarative/compiler.py`
- Modify: `lca/plugins/phase_executors/`
- Create: `lca/plugins/control_contributions/`
- Delete: `lca/layer2_runtime/control_policies.py`
- Modify: `lca/layer2_runtime/runtime_loop.py`
- Create: `tests/declarative/test_control_contributions.py`
- Delete: `tests/layer2_runtime/test_control_policies.py`

**Interfaces:**
- Consumes: `PhaseContribution(role=GOVERN, executor, aggregation, predicate)` 与 `ControlVerdict`。
- Produces: 每个 phase 的确定性 contribution order、聚合 verdict、evidence fact 和标准 outcome；无 `DefaultControlPolicyEngine` 或 ControlSlot-to-method map。

**当前代码事实（审计确认）：**
- `control_policies.py:52` — `DefaultControlPolicyEngine` 类，被 `runtime_loop.py:50,89,106` 导入和使用。
- `runtime_loop.py:191-215` — `evaluate_control()` 方法调用 `self.control_policies.evaluate()` 和 `aggregate_control_verdicts()`。
- `interpreter.py:312-320` — `_verdict_allows()` 是简单的布尔映射，不理解标准 verdict 结构。
- `tests/layer2_runtime/test_control_policies.py` — 270 行测试直接测试 `DefaultControlPolicyEngine`。

- [ ] **Step 1: 写失败的 contribution 聚合测试。**

```python
@pytest.mark.asyncio
async def test_deny_on_any_deny_blocks_act_before_the_effect_gateway():
    result, gateway = await run_plan_with_govern_verdicts("allow", "deny")
    assert result.outcome.kind == "failed"
    assert gateway.executed_envelopes == []
    assert any(f.kind == "control.verdict" for f in result.outcome.facts)

@pytest.mark.asyncio
async def test_ordered_rewrite_replaces_decision_before_act():
    result = await run_plan_with_rewrite("original", "rewritten")
    assert result.observation.decision_ref == "rewritten"
```

- [ ] **Step 2: 运行测试，确认当前实现只用 `_verdict_allows` 判布尔值，不能保存/聚合标准 verdict。**

Run: `uv run pytest --no-cov tests/declarative/test_control_contributions.py -q`

Expected: FAIL，缺少 `control.verdict` 事实或 rewrite 不生效。

- [ ] **Step 3: 以 PluginSpec contribution 实现 control executors。**

**实现要点：**
1. 创建 `lca/plugins/control_contributions/` 包，包含：
   - `perceive_context.py` — `control.executor.perceive-context` capability
   - `think_guard.py` — `control.executor.think-guard` capability
   - `act_authorize.py` / `act_budget.py` / `act_constrain.py` / `act_execute.py` / `act_safe_boundary.py`
   - `remember_admit.py` — `control.executor.remember-admit` capability
   - `stop_decide.py` — `control.executor.stop-decide` capability
   - `observe_checkpoint.py` / `observe_wildcard.py`
2. 每个 contribution 实现 `PhaseContributionExecutor` Protocol，返回标准 `PhaseResult(payload=ControlVerdict(...))`。
3. 在 `interpreter.py` 的 `_apply_post_contributions()` 中：
   - 替换 `_verdict_allows()` 为 `_aggregate_govern_verdicts(contributions, aggregation)`。
   - 支持 `deny-on-any-deny`、`first-terminal`、`ordered-rewrite` 聚合模式。
   - 每个 verdict 生成 `control.verdict` fact 并 commit 到 journal。
4. 在 `compiler.py` 中，把 `ControlEntry` 的 executor 字段解析为 `control.executor.*` capability binding。
5. 为每个 control contribution 生成 PluginSpec manifest YAML。

- [ ] **Step 4: 删除旧 engine 与调用点。**

1. 从 `runtime_loop.py` 中删除：
   - `from lca.layer2_runtime.control_policies import ControlPolicyContext, DefaultControlPolicyEngine` (L48-51)
   - `from lca.layer2_runtime.control_runtime import ControlEvaluation, ...` (L52-58)
   - `control_policies: DefaultControlPolicyEngine | None = None` 构造参数 (L89)
   - `self.control_policies = ...` 赋值 (L105-107)
   - `select_control()` 方法 (L185-189)
   - `evaluate_control()` 方法 (L191-215)
   - `_finish_control_stop()` 方法 (L357-367)
   - `_loop()` 中对上述方法的所有调用 (L228-320)
2. 删除 `control_policies.py` 文件和对应测试。
3. 更新 `lca/layer2_runtime/__init__.py` 的 re-export。

- [ ] **Step 5: 运行测试与提交。**

```bash
uv run pytest --no-cov tests/declarative/test_control_contributions.py tests/declarative/test_runtime_outcomes.py tests/architecture/test_new_architecture_closure.py -q
uv run lint-imports
git add lca/harness/declarative/ lca/plugins/control_contributions/ lca/plugins/phase_executors/ lca/layer2_runtime/runtime_loop.py tests/declarative/ tests/architecture/
git rm lca/layer2_runtime/control_policies.py tests/layer2_runtime/test_control_policies.py
git commit -m "refactor(adr-074): execute controls as phase contributions"
```

### Task 6: 删除 legacy runtime、v1 composer fallback 与 legacy-authoritative dual write

**Files:**
- Modify: `lca/layer2_runtime/runtime_loop.py`
- Modify: `lca/plugins/composer/plan_binding.py`
- Modify: `lca/plugins/loop_drivers/cognitive.py`
- Modify: `gateway/runs/loop_drivers.py`
- Delete: `lca/harness/command/dual_write.py`
- Delete: `tests/harness/test_dual_write.py`
- Modify: `tests/architecture/test_new_architecture_closure.py`
- Create: `tests/architecture/test_declarative_production_closure.py`
- Modify: `tests/layer4_app/test_spawn_bind_plan.py`

**Interfaces:**
- Consumes: `CompiledRunPlan.is_declarative`、`capability_bindings`、`phase_bindings`、`validation_report`。
- Produces: 生产 agent only accepts `plan.is_declarative is True` and valid; composition only injects capability bindings declared by plan.

**当前代码事实（审计确认）：**
- `plan_binding.py:158-164` — `_composer_bindings()` 的 `else` 分支对 `not plan.is_declarative` 使用 v1 fallback candidates `("composer.brain", "composer.body", "composer.perceive")` 或 `("composer.team",)`。
- `plan_binding.py:170-171` — 在 v1 fallback 下，inject 失败时抛 `BindPlanError`。
- `plan_binding.py:84` — `metadata` 中在 `not plan.is_declarative` 时 `removeprefix("composer.")`。
- `dual_write.py` — 存在，需查找所有调用点并确认删除安全性。

- [ ] **Step 1: 写失败的 source/behavior closure tests。**

```python
def test_production_runtime_and_composer_contain_no_legacy_execution_fallbacks():
    paths = [
        "lca/layer2_runtime/runtime_loop.py",
        "lca/plugins/composer/plan_binding.py",
        "lca/plugins/loop_drivers/cognitive.py",
        "gateway/runs/loop_drivers.py",
    ]
    forbidden = ("def _loop(", "return await self._loop", "not plan.is_declarative", "legacy_fn", "DualWriteExecutor")
    for path in paths:
        source = Path(path).read_text()
        assert all(token not in source for token in forbidden), path


def test_non_declarative_compiled_plan_is_rejected_before_assembly():
    with pytest.raises(BindPlanError, match="declarative"):
        bind_plan(request, non_declarative_plan, scope=scope)
```

- [ ] **Step 2: 运行测试，确认当前 source 包含 `_loop`、v1 composer candidates 和 dual-write 实现。**

Run: `uv run pytest --no-cov tests/architecture/test_declarative_production_closure.py -q`

Expected: FAIL，报告上述 legacy token 或 non-declarative plan 可组装。

- [ ] **Step 3: 进行删除式迁移。**

**`runtime_loop.py` 删除清单（审计确认的行号）：**
- 删除 `_loop()` 方法 (L217-331)
- 删除 `_checkpoint()` 方法 (L333-355)
- 删除 `_finish_control_stop()` 方法 (L357-367)
- 删除模块级辅助函数 `_is_blocking`、`_must_stop`、`_control_stop_decision`、`_control_denied_observation` (L370-416)
- 删除 `_drain_newly_activated` (L419-430) — 迁移到 perceive phase executor 或 observe contribution
- 删除所有 `control_policies` 和 `control_runtime` 导入 (L20-21, L42-43, L48-58)
- 从构造器删除 `control_plan`、`control_policies` 参数 (L88-89)
- 保留 `run()` 和 `resume()` 作为纯委托方法

**`plan_binding.py` 删除清单：**
- 删除 `_composer_bindings()` 中 `else` 分支 (L158-164)：改为 `if not plan.is_declarative: raise BindPlanError("...")`
- 删除 L84 和 L129 的 `if not plan.is_declarative` 条件表达式

**`dual_write.py` 删除：**
- 先搜索所有 `from lca.harness.command.dual_write import` 或 `DualWriteExecutor` 引用，确认不在生产路径
- 删除 `dual_write.py` 和 `test_dual_write.py`

- [ ] **Step 4: 运行聚焦回归和 vulture。**

Run: `uv run pytest --no-cov tests/architecture/test_declarative_production_closure.py tests/architecture/test_new_architecture_closure.py tests/declarative/ tests/layer4_app/test_spawn_bind_plan.py tests/test_run_*.py -q && uv run vulture lca --min-confidence 80`

Expected: PASS，vulture 不报告删除后新产生的未使用 production symbol。

- [ ] **Step 5: 提交。**

```bash
git add lca/layer2_runtime/runtime_loop.py lca/plugins/composer/plan_binding.py lca/plugins/loop_drivers/cognitive.py gateway/runs/loop_drivers.py tests/architecture/ tests/layer4_app/test_spawn_bind_plan.py
git rm lca/harness/command/dual_write.py tests/harness/test_dual_write.py
git commit -m "refactor(adr-074-075): remove legacy runtime and composer fallbacks"
```

### Task 7: 完成 effect 幂等、恢复图与计划 revision 的长程验收

**Files:**
- Modify: `lca/layer2_runtime/declarative_runtime.py`
- Modify: `lca/harness/declarative/interpreter.py`
- Modify: `lca/contracts/protocols/command_envelope.py`
- Modify: `profiles/web-standard.yaml`
- Create: `profiles/web-standard-recovery.yaml`
- Create: `tests/e2e/test_declarative_long_horizon_recovery.py`
- Modify: `tests/e2e/test_full_run_replay.py`

**Interfaces:**
- Consumes: `CommandEnvelope.idempotency_key`、effect receipt、checkpoint cursor、`PhaseEdge.loop` 和 profile-bound recovery contributions。
- Produces: 失败 observation → journal-backed reflection → bounded `reflect → think` re-entry；同一 idempotency key 至多执行一次；新 plan revision 只在 safe boundary 采用。

**当前代码事实（审计确认）：**
- `declarative_runtime.py:94-122` — `RuntimeEffectGateway.execute()` 只检查 `envelope.idempotency_key` 存在性（L100），没有 claim store。
- `interpreter.py:176-184` — effect receipt 后直接 commit，没有幂等去重。
- 默认 `web-standard.yaml` 的 phase graph 没有 `reflect → think` recovery edge。

- [ ] **Step 1: 写失败的持久幂等与 bounded recovery e2e 测试。**

```python
@pytest.mark.asyncio
async def test_resume_after_crash_does_not_reissue_a_confirmed_effect(tmp_path):
    harness = durable_effect_harness(tmp_path)
    first = await harness.run_until_crash_after_receipt()
    resumed = await harness.resume(first.checkpoint)
    assert harness.effect_handler.calls_for(first.envelope.idempotency_key) == 1
    assert resumed.status is TaskStatus.COMPLETED

@pytest.mark.asyncio
async def test_recovery_profile_replans_once_then_stops_at_declared_budget():
    result = await run_profile("profiles/web-standard-recovery.yaml", failing_tool_once=True)
    assert result.trace.edge_visits("reflect.main", "think.main") == 1
    assert result.trace.node_visits("think.main") <= 2
```

- [ ] **Step 2: 运行测试，确认默认 effect handler 仅检查 key 存在、默认图也没有 recovery edge。**

Run: `uv run pytest --no-cov tests/e2e/test_declarative_long_horizon_recovery.py -q`

Expected: FAIL，重复调用可发生或找不到 `reflect → think` recovery edge。

- [ ] **Step 3: 实现持久 idempotency receipt store 与声明式恢复 Profile。**

**实现要点：**

1. 在 `declarative_runtime.py` 中新增 `RuntimeIdempotencyStore`：
   - `claim(plan_ref, idempotency_key) → ClaimResult(receipt | None, status: Literal["new", "completed", "in_progress"])`
   - `completed` 返回同一 receipt；`in_progress` 返回 `effect_uncertain`；`new` 写入 claim 并继续 handler。
   - 使用 `StateStore` 或独立持久 backend。

2. 在 `RuntimeEffectGateway.execute()` 中：
   - handler 执行前调用 `store.claim()`。
   - `completed` → 直接返回已有 receipt，不执行 handler。
   - `in_progress` → 抛 `DeclarativeValidationError("RT-003", ...)`，由 interpreter 映射为 `effect_uncertain` outcome。

3. 创建 `profiles/web-standard-recovery.yaml`：
   - 在 phase graph 中声明 `reflect.main → think.main` edge，`when: "result.admit_recovery"`。
   - edge.loop: `{ maxIterations: 1, budget: run.steps }`。
   - `reflect` phase executor 增加 recovery contribution，检查 observation 失败并设置 `admit_recovery`。

- [ ] **Step 4: 写失败的 plan-revision safe-boundary 测试并实现最小采用规则。**

```python
@pytest.mark.asyncio
async def test_new_plan_revision_is_adopted_only_after_safe_boundary():
    result = await run_with_revision_requested_during_act()
    assert result.plan_refs == ("v1", "v1", "v2")
    assert result.phase_at_revision_adoption == "stop.main"
```

在 `interpreter.py` 中：新 revision 作为已验证计划放入下一轮 entry cursor；运行中的 node 永远使用原 `plan_ref`。

- [ ] **Step 5: 运行 e2e 和提交。**

```bash
uv run pytest --no-cov tests/e2e/test_declarative_long_horizon_recovery.py tests/e2e/test_full_run_replay.py tests/declarative/test_driver_resume.py -q
git add lca/layer2_runtime/declarative_runtime.py lca/harness/declarative/interpreter.py lca/contracts/protocols/command_envelope.py profiles/ tests/e2e/
git commit -m "feat(adr-075): add bounded declarative recovery and effect idempotency"
```

### Task 8: 更新 ADR 状态、运行审计和不可回退门禁

**Files:**
- Modify: `docs/adr/0075-implementation-audit.md`
- Modify: `docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md`
- Modify: `docs/adr/README.md`
- Modify: `docs/plans/adr-0074-plugin-everything-tracker.md`
- Modify: `docs/specs/declarative-phase-graph-spec.md`
- Modify: `tests/architecture/test_new_architecture_closure.py`
- Modify: `scripts/check_adr_supervision.py`（仅当 tracker 状态语法需要新增有效状态）

**Interfaces:**
- Consumes: 任务 1–7 的测试和 command output。
- Produces: ADR-0075 的可验证实施状态、ADR-0074 的"已被默认路径实际消费"证据、`audit declarative-boundaries` 零生产 fallback 结论。

- [ ] **Step 1: 写失败的不存在旧路径 guard。**

```python
def test_production_sources_do_not_reference_removed_runtime_modules():
    production = production_python_sources(excluding=("tests",))
    forbidden = {"lca.layer2_runtime.control_policies", "lca.harness.command.dual_write"}
    assert not {module for module in imports_of(production) if module in forbidden}
```

- [ ] **Step 2: 运行测试，确认在模块删除前 guard 捕获现有 import 或文件。**

Run: `uv run pytest --no-cov tests/architecture/test_new_architecture_closure.py -q`

Expected: FAIL，直到 Tasks 5–6 完成删除与 import 收口。

- [ ] **Step 3: 更新文档事实。**

在 ADR-0075 中将状态从 `Proposed` 改为 `Accepted` 的前提是本任务全量门禁通过；若任一 Task 7 的恢复/幂等 e2e 尚未通过，保留 `Proposed` 并在 `实施后果` 中引用未完成任务。实施审计必须删去已经补齐事项，新增"旧 `_loop`、v1 composer fallback、legacy-authoritative dual write 已删除"的测试命令与 commit。ADR-0074 tracker 仅追加"ADR-0075 consumption cutover"监督条目，不伪造或重写 2026-08-21 的历史 PR 状态。

- [ ] **Step 4: 执行 ADR 和文档一致性检查。**

Run: `uv run python scripts/check_adr_supervision.py && uv run python scripts/route_legacy_patterns.py && uv run pytest --no-cov tests/architecture/test_new_architecture_closure.py tests/test_check_adr_supervision.py -q && uv run python scripts/verify_md_links.py docs/adr docs/specs docs/plans`

Expected: PASS；route report 中不再有指向 production cognitive runtime/composer 的旧流程 owner。

- [ ] **Step 5: 单独提交文档与架构门禁。**

```bash
git add docs/adr/ docs/specs/declarative-phase-graph-spec.md docs/plans/adr-0074-plugin-everything-tracker.md tests/architecture/ scripts/check_adr_supervision.py
git commit -m "docs(adr-074-075): record declarative runtime cutover"
```

## 3. 最终验收矩阵

| 验收项 | 必须成立的证据 | 命令 |
|---|---|---|
| 默认 run 只走声明式图 | monkeypatch `_loop` 为失败函数后 default Profile run 仍成功 | `uv run pytest --no-cov tests/declarative/test_default_profile_architecture.py -q` |
| resume 不可回落旧循环 | pause → snapshot → resume 用 driver cursor 完成 | `uv run pytest --no-cov tests/declarative/test_driver_resume.py -q` |
| 图循环有界 | node/edge 超出 `max_visits` / `max_iterations` 返回 Journal-backed stop outcome | `uv run pytest --no-cov tests/declarative/test_interpreter_checkpoint_resume.py tests/declarative/test_runtime_outcomes.py -q` |
| 控制完全由贡献图执行 | deny/rewrite/pause 具有 evidence、不能执行被拒绝效果 | `uv run pytest --no-cov tests/declarative/test_control_contributions.py -q` |
| 效果不可重复 | crash after receipt 后 resume 不重发同一 idempotency key | `uv run pytest --no-cov tests/e2e/test_declarative_long_horizon_recovery.py -q` |
| 非声明式计划 fail-closed | 无 `phase_graph` / binding 的 plan 在 assembly 前拒绝 | `uv run pytest --no-cov tests/architecture/test_declarative_production_closure.py -q` |
| 旧生产流程删除 | Runtime/Composer/Driver 无 `_loop`、policy engine、v1 fallback、dual-write import | `uv run pytest --no-cov tests/architecture/test_new_architecture_closure.py tests/architecture/test_declarative_production_closure.py -q` |
| 分层与类型正确 | contracts 无实现依赖，公开 Protocol 有完整类型 | `uv run lint-imports && uv run mypy lca` |
| 无死代码且全仓回归 | vulture/pytest/ruff 全绿 | `uv run ruff check --fix . && uv run ruff format . && uv run pytest && uv run vulture lca --min-confidence 80` |

## 4. 风险与拒绝条件

| 风险 | 检测点 | 拒绝/缓解动作 |
|---|---|---|
| 删除 `_loop` 破坏未覆盖的直接构造测试 | Task 1 characterization 与仓库全量 pytest | 不恢复 fallback；将测试迁移为 booted declarative profile 或专用 fake `ExecutablePlan`。 |
| 审批恢复丢失任务或重复 effect | Task 4 resume test + Task 7 idempotency e2e | checkpoint 不含 cursor/plan_ref 或 receipt 状态时拒绝 resume，返回 `effect_uncertain`/人工升级。 |
| 控制迁移改变 deny 优先级 | Task 5 deny/rewrite tests | 将实际 aggregation 写入 PluginSpec 和 plan；不保留 engine 作为 second opinion。 |
| 计划热更新在 action 中途改变语义 | Task 7 safe-boundary test | 仅在 Stop safe boundary 从新 plan cursor 进入下一轮；任何中途 revision 请求被 Journal 记录但不采用。 |
| "删除旧流程"误伤存量数据 reader/API 协议 | Global Constraints + architecture source allowlist | 仅删除可执行 production cognitive flow；保留带迁移注释且无运行选择权的 data-reader compatibility。 |

## 5. 计划自检

| 自检项 | 结论 |
|---|---|
| ADR-0074 consumption | Tasks 4–6 让 plan、control entries、capability bindings、CommandEnvelope 成为唯一生产输入和执行边界。 |
| ADR-0075 consumption | Tasks 2–4、7 将 PhaseGraph、PhaseExecutor、GenericPlanInterpreter、Journal/Reducer/Gateway、pause/resume 和 recovery edge 统一为同一运行模型。 |
| 旧流程删除 | Task 6 删除 `_loop`、DefaultControlPolicyEngine、v1 composer fallback、legacy-authoritative dual write；Task 8 用源代码守卫阻止回归。 |
| 长程与自愈 | Task 2/3/4/7 依次实现 cursor、typed outcome、durable resume、idempotent effect 和 bounded recovery graph。 |
| 无占位任务 | 每个任务给出具体文件、API、RED 命令、GREEN 实现目标、验证命令和提交边界。 |
| 范围约束 | 明确不删除历史数据读取与外部协议兼容；不改变六 phase 闭集或 MTK 不变量。 |

## 6. 审计修正清单（相对初步 plan 的差异）

| # | 初步 plan 描述 | 实际代码事实 | 修正 |
|---|---|---|---|
| 1 | `interpreter.py` 的 `run()` 可直接拆为 `_drive()` + `resume()` | 确认：`run()` 在 L102-211，`visit_counts`/`edge_counts`/`artifact_map` 是局部变量，需提升为参数 | Task 2 Step 3 增加实现要点 |
| 2 | `InterpretationResult` 可直接加 `cursor` 字段 | 确认：`InterpretationResult` 在 L79-85，需新增 `cursor: PhaseRunCursor \| None` | Task 2 Step 3 明确 |
| 3 | `_verdict_allows()` 替换为 `_classify_verdict()` | 确认：`_verdict_allows()` 在 L312-320，只理解 `allowed`/`verdict` 布尔映射 | Task 3 Step 3 给出具体替换策略 |
| 4 | `DeclarativeRuntimeDriver` 可直接加 `resume()` | 确认：class 在 L154-193，只有 `run(state)`，需注入 `_state_store` | Task 4 Step 3 给出完整签名 |
| 5 | `CognitiveRuntime.resume()` 改为委托 | 确认：L156-183，含 answer turn 构造逻辑（需保留）和 `_loop()` 调用（需替换） | Task 4 Step 3 明确保留 turn 构造 |
| 6 | `runtime_loop.py` 的 `control_policies` 导入在 L48-58 | 确认：L48-51 (`control_policies`) 和 L52-58 (`control_runtime`) | Task 5 Step 4 给出精确行号 |
| 7 | `plan_binding.py` 的 v1 fallback 在 L158-164 | 确认：`else` 分支在 L158-164，candidates 是 `("composer.brain", "composer.body", "composer.perceive")` | Task 6 Step 3 给出精确替换 |
| 8 | `DeclarativeRuntimeDriver.run()` 的 effect gateway 检查幂等键存在性 | 确认：`declarative_runtime.py:100` 只检查 `not envelope.idempotency_key`，无 claim store | Task 7 Step 3 新增 `RuntimeIdempotencyStore` |
| 9 | `harness_live.py` 引用 | 确认文件存在（`lca/layer4_app/harness_live.py`） | 无需修正 |

## 8. 风险评估

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 控制聚合语义改变导致行为回归 | 高 | Task 5 使用与旧 engine 完全相同的聚合逻辑（deny-on-any-deny、first-terminal、ordered-rewrite）；删除前先用双轨模式验证新路径输出与旧 engine 一致 |
| 删除 `_loop()` 后发现未覆盖的边界情况 | 高 | Task 1 已建立 characterization 基线；Task 6 删除前必须确保 characterization 测试全部 GREEN |
| 生产 Profile 缺少 `CompiledRunPlan` | 中 | Task 6 fail-closed 实施前确认所有生产 profile YAML 已包含声明式 plan；提供 profile 验证脚本 |
| 幂等 claim store 持久化层引入性能问题 | 低 | Task 7 使用现有 `StateStore` 接口；可回退到内存实现 + 重启去重（不保证跨重启幂等，但保证单次运行内幂等） |
| ADR-0075 状态更新与实施事实不一致 | 低 | Task 8 明确：只有所有验收矩阵项全绿才能改 Accepted；否则保留 Proposed 并记录未完成项 |

## 9. 文档更新

完成所有任务后需更新：

| 文档 | 更新内容 |
|---|---|
| `docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md` | 状态从 `Proposed` → `Accepted`（仅当验收矩阵全绿）；更新"后果"章节引用 Task 1-7 的测试命令和 commit hash |
| `docs/adr/README.md` | ADR-0075 状态标记为 `Accepted` |
| `docs/plans/adr-0074-plugin-everything-tracker.md` | 追加"ADR-0075 消费切换"监督条目，引用 Task 5-6 的 commit |
| `docs/specs/declarative-phase-graph-spec.md` | 删除"迁移计划"章节；更新"实施状态"为"已完成" |

**注意**：不伪造历史 PR 状态。若 Task 7 的恢复 e2e 未通过，ADR-0075 保留 `Proposed` 状态。

## 10. 开放问题

**Q1: Task 7 的 `RuntimeIdempotencyStore` 应使用什么持久化后端？**
- **选项 A**：使用现有 `StateStore` 接口（与 `AgentState` 共用 backend）
- **选项 B**：使用独立 `EffectReceiptStore` 接口（更隔离但增加复杂度）
- **建议**：选项 A，减少新增原语；若性能测试发现问题再拆分为选项 B

**Q2: 删除 `dual_write.py` 是否影响外部集成测试？**
- **答案**：`dual_write.py` 仅在生产路径执行"双轨写入"（legacy + declarative），外部集成测试不依赖它；删除前用 `grep -r "dual_write" tests/` 确认无引用

**Q3: 是否需要提供 `CompiledRunPlan` 生成工具？**
- **答案**：不需要。现有 `profiles/web-standard.yaml` 已包含声明式 plan；用户通过修改 YAML 调整行为，不需要程序化生成工具

---

## 执行策略

**方法**：使用 `superpowers:subagent-driven-development` 逐任务实施。每个任务由独立 subagent 完成，主 agent 负责：
1. 分配任务给 subagent
2. 审查 subagent 提交的代码（spec 合规性、测试覆盖、commit 质量）
3. 拒绝不合格的实现，要求重新执行
4. 任务间执行全量门禁（ruff + mypy + pytest + lint-imports + vulture）

**提交边界**：每个任务独立 commit，commit message 引用任务编号和 ADR。

**并行性**：Task 5 和 Task 6 可部分并行（Task 5 创建新模块，Task 6 删除旧模块），但 Task 6 必须在 Task 5 验证 GREEN 后执行删除。

---

**计划完成时间估计**：8 个任务 × 平均 2-3 小时/任务 = 16-24 小时（含测试和门禁验证）。
