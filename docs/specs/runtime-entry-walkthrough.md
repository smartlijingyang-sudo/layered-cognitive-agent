# 运行时入口走读：从 HTTP 到 PhaseGraph

> **状态：** Living note
> **维护者：** @lca-maintainers
> **适用：** 需要回答"一条 `POST /runs` 究竟是怎么一步步把请求送进 `CognitiveRuntime`，又怎么把 `CompiledRunPlan` 真正跑起来"的所有读者。
> **不在此：** Plan 怎么被编出来由 [plan-compile-and-execute-walkthrough.md](plan-compile-and-execute-walkthrough.md) 负责；阶段闭集、节点边权、控制条目由 [declarative-phase-graph-spec.md](declarative-phase-graph-spec.md) 负责；术语见 [glossary.md](glossary.md)；架构决策见 [ADR-0103](../adr/0103-locked-surface-and-port-policy.md)、[ADR-0110](../adr/0110-plugin-contract-unification-and-naming-convergence.md)、[ADR-0112](../adr/0112-gateway-routes-as-plugins.md)、[ADR-0115](../adr/0115-kernel-transport-boundary.md)、[ADR-0119](../adr/0119-webserver-as-plugin.md)、[ADR-0119-followup-gateway-name-map](../adr/0119-followup-gateway-name-map.md)。

本文用 7 个问题逐段走读 LCA 的运行时入口链：HTTP 进来 → agent.run / runtime.run → 计划被 binding 装订并执行。同时把每一段背后的"约束为什么是这样"标注在脚注里。

配套阅读：

- [plan-compile-and-execute-walkthrough.md](plan-compile-and-execute-walkthrough.md) —— **计划本身**怎么被编出来、怎么被 hash、怎么跨进程交接。
- [declarative-phase-graph-spec.md](declarative-phase-graph-spec.md) —— 节点、边、loop guard 的语义。
- [harness-spine-spec.md](harness-spine-spec.md) —— Profile/Boot/Plugin 的启动顺序。

---

## 0. 一句话总结

**`POST /runs` 不是 cognitive agent 的入口，它只是 carrier 的"投递请求"。真正驱动 `CompiledRunPlan` 的入口是 `CognitiveRuntime.run` —— 它做且只做 4 件事：new_state、require_executable_plan、STARTED 生命周期事件、把状态丢给 `DeclarativeRuntimeBindings.new_driver()`。图计划是被 binding 通过"装订 + 解释"两步拉到运行里的。**

理解入口链路的核心是把 6 个层次的角色分清楚：

| 层 | 模块 | 角色 | 它知不知道阶段语义 |
|---|---|---|---|
| 0. Wire | HTTP + Route catalog | 字节流进出 | 不知道 |
| 1. Carrier | webserver handler (`command_endpoints.create_run`) | body → `RunRequest` 投递 | 不知道 |
| 2. Port | `RunPort`（`terminal/port.py`）Protocol | transport 与 application 的唯一运行词汇表 | 不知道 |
| 3. Coordinator | `RunLifecycleCoordinator.execute`（`lifecycle/lifecycle.py`） | 解析 intent → 选 driver → dispatch | 不知道 |
| 4. Driver | `CognitiveRunDriver.execute`（`execute/loop_drivers.py`） | 造 Agent / Team 实例并 `.run()` | **不依赖任何"loop topology"** |
| 5. Application facade | `Agent.run`（`application/api.py:152`） | 把 facade 调用直接转发给 `CognitiveRuntime` | 不知道 |
| 6. Runtime | `CognitiveRuntime.run` / `resume`（`runtime/runtime_loop.py:135/179`） | 唯一的认知平面入口 | **也是不知道**——它把责任丢给 binding |
| 7. Binding + Executor | `DeclarativeRuntimeBindings` + `DeclarativeExecution`（`runtime/runtime_bindings.py`, `runtime/declarative_runtime.py`） | **唯一持有 `CompiledRunPlan` 解释权的层** | 知道 |

只有第 7 层真的"懂图"，其余 6 层都把图当成不透明对象在传递。[^no-knowledge-leak]

---

## 1. 第 0 层：路由 catalog 是 webserver 的唯一真理

`POST /runs` 不在 `server.py` 里 hard-code。`lca-web-server` plugin 启动后从一个 routes plugin registry 把所有 `Route` 条目安装到 Starlette `app.router.routes`。

入口目录在 `lca/plugins/transport/webserver/routes_runs_sessions.py:53`：

```python
ROUTES: tuple[Route, ...] = (
    Route("/runs", create_run, methods=["POST", "OPTIONS"]),
    Route("/runs/{run_id}", get_run, methods=["GET"]),
    Route("/runs/{run_id}/live", stream_run_live, methods=["GET", "OPTIONS"]),
    Route("/runs/{run_id}/doctor", get_run_doctor, methods=["GET"]),
    Route("/runs/{run_id}/profile", get_run_profile, methods=["GET"]),
    Route("/runs/{run_id}/evidence/{ref:path}", get_run_evidence, methods=["GET"]),
    Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
    Route("/runs/{run_id}/answer", answer_run, methods=["POST", "OPTIONS"]),
    Route("/v1/sessions", create_session, methods=["POST", "OPTIONS"]),
    Route("/v1/sessions/{session_id}/messages", send_message, methods=["POST", "OPTIONS"]),
)
```

`lca-webserver-router` plugin 在 lifespan 期间调 `route_registry.install(app)`，一次性 append 上面所有条目（[ADR-0112](../adr/0112-gateway-routes-as-plugins.md) §决定 4；[ADR-0115](../adr/0115-kernel-transport-boundary.md) §决定 6）。

**新增 HTTP 路径就是新增一个 routes plugin，而不是改 `server.py` 或 `gateway/app.py`。**[^routes-as-plugins]

## 2. 第 1 层：handler 把 HTTP 翻译成 `RunRequest`

`POST /runs` 命中 `create_run`，看 `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py:53-127`：

```python
async def create_run(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())

    ctx = _ctx_of(request)                                  # 拿 cordis.Context（由 lifespan 装到 app.state）
    ...
    body = await request.json()
    run_input = RunInputPayload.model_validate(body)        # pydantic 解析（wire 校验）

    adapter = _run_port_of(request)                         # 拿 RunPort（profile boot 时注入 app.state.run_port）
    receipt = await adapter.create_and_dispatch(
        RunRequest(
            profile=str(body.get("profile") or "web-standard"),
            question=run_input.question,
            user_text=run_input.user_text,
            ...
        )
    )
    return JSONResponse(
        {"run_id": receipt.run_id, "live_url": f"/runs/{receipt.run_id}/live", ...},
        status_code=202,                                    # 异步收据；真正结果从 SSE 流出去
        headers=cors_headers(),
    )
```

三件事：

1. **wire 解析**——`RunInputPayload` 在 webserver 层做最低限度字段校验；任何 pydantic 错误就此返回 4xx，不会污染应用层。
2. **wire 类型**——`RunRequest`（`terminal/port.py:23`）是 transport 与 application 之间唯一的 wire 类型，handler 收到 dict 就要转成它。
3. **202 Accepted**——返回的不是 `Result`，而是收据加 `live_url`。`POST /runs/{run_id}/live`（SSE）才是真正结果的载体；这就是 [ADR-0092 durable command ledger](../adr/0092-durable-session-command-ledger.md) 的"submit returns receipt，observe via stream"语义。

handler 调用的是 `RunPort.create_and_dispatch(request)`，**handler 不知道也不需要知道运行态在哪儿发生**——这就是 carrier 与 application 的边界。[^carrier-vs-app]

## 3. 第 2 层：`RunPort` Protocol

`lca/plugins/transport/webserver/handlers/runs/terminal/port.py:60`：

```python
@runtime_checkable
class RunPort(Protocol):
    """HTTP carrier 可依赖的完整运行词汇表和健康投影。"""

    async def create_and_dispatch(self, request: RunRequest) -> RunReceipt: ...
    async def cancel(self, run_id: str) -> RunCommandReceipt: ...
    async def resume_approval(
        self, run_id: str, approval_id: str, payload: str, ...
    ) -> RunCommandReceipt: ...
```

`RunPort` 是 **transport 在 boot 期从 `app.state` 注入的 capability**。webserver 拿到这个能力对象就可以走整条运行词汇表，但**它完全不知道 `CognitiveRuntime`、`Agent`、`Body`、`Brain`**——这些都不在 wire 协议面上。[^transport-port-policy]

`RunPort` 的实现是 `RunLifecycleCoordinator`，它在 lifespan 启动阶段由 `install_bootstrap_state` 钩到 `app.state.run_port`（[ADR-0119](../adr/0119-webserver-as-plugin.md) §决定 1）。

## 4. 第 3 层：`RunLifecycleCoordinator.execute`

这个 coordinator 是"carrier 与 application 的真正接缝点"。`lca/plugins/transport/webserver/handlers/runs/lifecycle/lifecycle.py:55`：

```python
async def execute(self, *, run_id, question, ...):
    # 1) 用 session + profile 选 runtime plane / 出 RunContext
    intent = resolve_run_intent(...)

    # 2) 从 run_loop_driver_registry 选 driver（profile 决定，不是 hard-code）
    drivers = require_capability(ctx, "run_loop_drivers")
    driver = drivers.select(intent.mode, session=session)

    # 3) 真正调用这个 driver 的 execute
    outcome: DriverOutcome = await driver.execute(
        session=session,
        question=question,
        mode=intent.mode,
        hub=hub,
        bindings=intent.bindings,
        run_context=intent.run_context,
        ctx=ctx,
    )
    ...
```

关键点：**driver 是 profile 注入的，不是 carrier 写死的**。`RunLoopDriverRegistry`（`lca/plugins/loop_drivers/registry.py`）是一个 registry seam：

| 内置 driver | 用途 | 在 |
|---|---|---|
| `CognitiveRunDriver` | 默认：用 plugin 树 / Cordis Context 拼 Agent / Team | `execute/loop_drivers.py:89` |
| `Streaming*Driver`（可选） | 直接对外暴露流（OpenAI SSE 与 LCA SSE 同源） | `execute/scheduling.py` |

profile enable/disable `loop.*` plugin 即可切换 driver，不用动 webserver。[^driver-via-plugin]

## 5. 第 4 层：`CognitiveRunDriver.execute` —— 造 Agent 并 `.run()`

`lca/plugins/transport/webserver/handlers/runs/execute/loop_drivers.py:104-172` 的核心：

```python
async def execute(self, session, *, question, mode, hub, bindings, run_context,
                  ctx=None, llm_resolver=None, machine_resolver=None):
    del machine_resolver
    # 1) 选 LLM
    if llm_resolver is None:
        if ctx is None:
            raise TypeError("CognitiveRunDriver.execute requires ctx or llm_resolver")
        llm = require_capability(ctx, "llm_resolver").resolve()
        scope: Context | None = ctx
    else:
        llm = llm_resolver.resolve()
        scope = None

    # 2) 从 booted tools seam 物化工具集
    tools = _tools_from_ctx(scope, bindings)

    # 3) 按 mode 选 Agent 或 Team —— 这是 profile 的决策
    if mode == SOLO_MODE_KEY:
        runnable: Agent | Team = _build_solo_agent(
            llm, observability=hub, role=session.agent.name,
            scope=scope, tools=tools,
        )
    else:
        runnable = await _build_team(
            question, llm, observability=hub,
            trace_id=session.trace_id, run_id=session.run_id,
            scope=scope, tools=tools,
        )

    # 4) ★ 真正调用 Agent/Team.run —— application 层 facade 入口
    result = (
        await runnable.run(question, run_context)
        if isinstance(runnable, Agent)
        else await runnable.run(question)
    )

    # 5) 把 Result 折叠成 DriverOutcome（HITL / approval / 终态投影在更上一层做）
    if result.status == TaskStatus.INPUT_REQUIRED:
        return DriverOutcome(
            success=False, result=result,
            waiting_input=True,
            snapshot=result.extra.get("state_snapshot"),
            approval_request=result.extra.get("approval_request"),
            resumable=runnable,                       # ← 同一 Agent 实例被回填
        )
    return DriverOutcome(
        success=result.status == TaskStatus.COMPLETED,
        result=result, error=result.error or "",
    )
```

四点要记：

1. **`mode` 来自 session/profile，driver 不允许自己决定运行时模式**——这与 [ADR-0082](../adr/0082-architecture-review-2026-08-24.md) §结论 "六步闭集由 Profile/PhaseGraph 组合，不能新增平行 runtime" 一致。
2. **driver 只造 `Agent`/`Team`，不解释阶段**。它连 `CognitiveRuntime` 的影子都没碰——它只接收"已冻结的 binding 包装出的 Agent"。
3. **`runnable.run(...)` 才是真正的认知平面入口**。
4. **`resumable=runnable`** 把同一个 `Agent`（背后同一份 binding）回填进 `DriverOutcome`——下一次 `POST /runs/{run_id}/answer` 命中同一个 `runnable.run` 路径，**通常走 `Runtime.resume` 分支**，cursor 由 checkpoint 决定（见 §7）。

`runnable.run()` 落进 `lca/application/api.py:152` 的 `Agent.run`，它做**一件事**：

```python
async def run(self, task: str | AgentMessage, ctx: RunContext | None = None) -> Result:
    return await self._agent.run(task, ctx)
```

`self._agent` 就是构造期注入的 `CognitiveRuntime` 实例——这一层是 application facade，**完全没有自己的逻辑**。

## 6. 第 6 层：`CognitiveRuntime.run` —— 唯一的认知平面入口

`lca/runtime/runtime_loop.py:135-171` 是整套入口的核心：

```python
async def run(
    self,
    task: str,
    ctx: RunContext | None = None,
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_wall_clock_seconds: int | None = None,
    agent_role: str = "",
) -> Result:
    # 1) trace 协商（三处来源回退）
    trace_id = (
        (ctx.trace_id if ctx and ctx.trace_id else None)
        or scope_trace_id
        or span_ctx.trace_id
        or new_id("trace")
    )

    # 2) 用 binding 造一份全新 AgentState（预算、来源、team 感知）
    state = self._bindings.new_state(
        trace_id=trace_id, task=task, budget=create_budget(...),
        agent_role=agent_role,
        from_role=(ctx.from_role if ctx else ""),
        team_awareness=(ctx.team_awareness if ctx else None),
    )

    # 3) 把上一轮 WM 回灌
    if ctx and ctx.extra.get(PRIOR_CONVERSATION_WM_KEY):
        state.extra[PRIOR_CONVERSATION_WM_KEY] = ctx.extra[PRIOR_CONVERSATION_WM_KEY]

    # 4) 强校验：plan + 所有 phase executor 已就位，否则 fail-closed
    self._bindings.require_executable_plan()

    # 5) 发生命周期事件 + ON_START hook
    await self._lifecycle.publish(RuntimeLifecycleEventType.STARTED, state)
    await self.hooks.trigger(HookEvent.ON_START.value, state)

    # 6) ★ 把状态交给 binding.new_driver() —— 图计划真正的入口
    return await self._run_driver(
        state,
        runner=lambda: self._bindings.new_driver().run(state),
    )
```

6 步里没有任何"思考→决策→行动"的逻辑：

- (1)-(3) 是**上下文协商**——给状态盖 trace、给预算、灌 WM。
- (4) 是**入口闸**——这一步是 binding 的 `require_executable_plan()` 抛错的唯一窗口。
- (5) 是**生命周期**——publish STARTED、trigger ON_START hook；任何 hook 都无权改写 State（[v3 宪法](../design/2026-08-19-cognitive-primitive-constitution-v3.md)）。
- (6) 是**真正驱动的边缘**——把所有事都丢给 `binding.new_driver()`。

`resume()`（`runtime_loop.py:179-213`）是镜像入口：

```python
async def resume(self, snapshot, input=None, ...):
    state = await self.state_store.load(snapshot.state_ref)              # 物化状态
    resume_input = self.resume_input_adapter.normalize(input)            # 适配输入
    state = self.reducer.apply_resume(state, ..., resume_input.turn)     # 应用 resume reducer

    phase_cursor = snapshot.phase_cursor or getattr(state, "phase_cursor", None)
    self._bindings.require_executable_plan()
    if phase_cursor is None:
        raise ValueError(
            "CognitiveRuntime.resume requires a declarative phase_cursor. "
            "Legacy runtime loop has been removed (ADR-0074/0075 declarative cutover)."
        )

    checkpoint = DeclarativeCheckpoint(
        state_snapshot=snapshot, cursor=phase_cursor,
        plan_ref=phase_cursor.plan_ref, resume_state=state,
    )
    await self._lifecycle.publish(...RESUMED..., phase_cursor=phase_cursor.node_id)
    return await self._run_driver(
        state,
        runner=lambda: self._bindings.new_driver().resume(checkpoint),
        phase_cursor=phase_cursor.node_id,
    )
```

关键不变量（**fresh 和 resume 走同一个 binding、同一个 driver 工厂**：区别只是有/无 cursor）。这也是为什么 `DriverOutcome.resumable=runnable` 安全——同一个 `Agent`（= 同一份 binding）的 `run` / `resume` 都能落到这里。[^same-binding-both-paths]

`CognitiveRuntime.__init__`（`runtime_loop.py:62`）就更简单了：

```python
def __init__(self, bindings: DeclarativeRuntimeBindings) -> None:
    self._bindings = bindings
    self._lifecycle = RuntimeLifecycleEmitter(bindings)
```

构造期不接受任何可替换依赖——`Brain`/`Body`/`Memory`/具体 `CompiledRunPlan` **全部已经在 binding 里冻结了**。

## 7. 第 7 层：binding 才是计划的解释者

这一层才是 `CompiledRunPlan` 真正被"装订"成可执行代码的地方。

### 7.1 binding 本身

`lca/runtime/runtime_bindings.py:111-189`（节选）：

```python
@dataclass(frozen=True, slots=True)
class DeclarativeRuntimeBindings:
    plan: CompiledRunPlan | None                  # 编译好的图
    phase_executors: Mapping[str, PhaseExecutor]  # 每个阶段对应的执行器
    capabilities: RuntimePhaseCapabilities        # Brain / Body / Memory / PerceiveHub
    reducer: Reducer
    hooks: HookRegistry
    effect_handler_registry: EffectHandlerRegistry
    delta_handler_registry: DeltaHandlerRegistry
    artifact_closure: ArtifactClosure
    idempotency_store: IdempotencyStore
    resume_input_adapter: ResumeInputAdapter
    state_store: StateStore
    effect_dispatcher_factory: EffectDispatcherFactory
    delta_reducer_factory: DeltaReducerFactory
    journal_factory: RuntimeJournalFactory
    interpreter_factory: DeclarativeInterpreterFactory     # ★ 解释器工厂
    checkpoint_state_resolver_factory: CheckpointStateResolverFactory
    result_finalizer_factory: ResultFinalizerFactory
    phase_observer: PhaseObserver
    lifecycle_publisher: RuntimeLifecyclePublisher | None
```

`assemble(...)` 工厂把 `phase_executors` 用 `MappingProxyType(dict(...))` 冻结（`runtime_bindings.py:170`）——**runtime 启动期没有任何路径能改写 phase 映射**。这正是 [ADR-0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md) "trust the kernel, freeze the plan" 的实现机制。[^frozen-mapping]

### 7.2 计划可用性校验（binding 的入口闸）

`runtime_bindings.py:194-205`：

```python
def require_executable_plan(self) -> CompiledRunPlan:
    if self.plan is None or not self.phase_executors:
        raise ValueError(
            "DeclarativeRuntimeBindings requires a compiled_plan and phase_executors."
        )
    required = {binding.executor_capability for binding in self.plan.phase_bindings}
    missing = sorted(required.difference(self.phase_executors))
    if missing:
        raise ValueError(
            "DeclarativeRuntimeBindings is missing phase executors: " + ", ".join(missing)
        )
    return self.plan
```

行为：**拿计划声明的每一个 `executor_capability` 与已注册的 `phase_executors` 求差集**。缺任何一个就 fail-closed。这是 `CognitiveRuntime.run` 第 (4) 步实际抛错的源头。

### 7.3 `new_driver()` —— 把 binding 变成 carrier adapter

`lca/runtime/declarative_runtime.py:75-107`：

```python
class DeclarativeRuntimeDriver:
    """由不可变运行 binding 构造的 carrier adapter。"""

    def __init__(self, bindings: DeclarativeRuntimeBindings, *, journal: RuntimeJournal) -> None:
        self._bindings = bindings
        self._checkpoint_state_resolver = bindings.new_checkpoint_state_resolver()
        result_finalizer = bindings.new_result_finalizer()
        self._execution = DeclarativeExecution(
            bindings, journal=journal, result_finalizer=result_finalizer,
        )

    async def run(self, state: AgentState) -> Result:
        return await self._execution.execute(state)

    async def resume(self, checkpoint: DeclarativeCheckpoint) -> Result:
        loaded_state = await self._checkpoint_state_resolver.resolve(
            checkpoint, expected_plan_ref=self._execution.plan_ref,
        )
        return await self._execution.execute(loaded_state, cursor=checkpoint.cursor)
```

`driver` 自己**不理解阶段**，它只是 carrier adapter。真正的执行落在 `DeclarativeExecution.execute`。

### 7.4 `DeclarativeExecution.execute` —— 图计划被装订并解释

`lca/runtime/declarative_runtime.py:32-67`：

```python
class DeclarativeExecution:
    def __init__(self, bindings, *, journal, result_finalizer):
        self._bindings = bindings
        self._journal = journal
        self._result_finalizer = result_finalizer

    async def execute(self, state, *, cursor=None):
        # (1) 反向校验：plan + phase_executors 闭集完整
        plan = self._bindings.require_executable_plan()

        # (2) 装订：把 plan + 只读 phase_scope 变成可被解释器消费的 executable
        executable = GraphAssembler().assemble(
            plan,
            self._bindings.phase_scope(),                # MappingRestrictedScope(self.phase_executors)
        )

        # (3) 解释器工厂（profile 选定的）→ 真正的 DeclarativeInterpreter
        interpreter = self._bindings.new_interpreter(journal=self._journal)

        if cursor is None:
            interpretation = await interpreter.run(
                executable, state=state,
                budget=state.budget,
                capabilities=self._bindings.capabilities,
                artifacts={"task": state.task},
            )
        else:
            interpretation = await interpreter.resume(
                executable, state=state, cursor=cursor,
                budget=state.budget,
                capabilities=self._bindings.capabilities,
            )

        # (4) 终态投影：合成最终 Result（不决定下一条图边）
        return await self._result_finalizer.finalize(
            interpretation=interpretation,
            plan_ref=self._bindings.plan_ref(),
            journal_sequence=self._journal.sequence,
        )
```

这就是"图计划怎么被 binding 驱动起来"的精确 4 步：

| 步 | 在哪里 | 在做什么 |
|---|---|---|
| (1) 校验 | `require_executable_plan` | 用 binding 冻结的 plan 反向校验 phase_executors 集合 |
| (2) 装订 | `GraphAssembler().assemble(plan, phase_scope)` | 把"声明式图"+"只读 phase 映射"打包成解释器可消费的 `executable` |
| (3) 解释 | `bindings.new_interpreter(...)` → `interpreter.run/resume(executable, state, ...)` | 解释器按 cursor 推进、产出 delta、reduce 到 state、写 journal |
| (4) 终态 | `result_finalizer.finalize(...)` | 仅做"成功/失败/HITL/取消/审批暂停"的 `Result` 合成，不决定下一条图边 |

`plan_ref()` 是 binding 暴露的稳定身份，对应 `compiled_run_plan_ref(plan)`——它是审批交接、checkpoint resume、跨进程幂等的同一把锁（见 [plan-compile-and-execute-walkthrough.md](plan-compile-and-execute-walkthrough.md) §4）。

---

## 8. 把 7 层压成一张图

```
HTTP POST /runs
  │
  ▼
[0] routes plugin         ── routes_runs_sessions.ROUTES  (Starlette Route)
  │ POST /runs → create_run
  ▼
[1] handler (carrier)     ── command_endpoints.create_run     (wire parse → RunRequest, 202 + live_url)
  │
  ▼
[2] RunPort Protocol      ── terminal/port.py RunPort           (transport ↔ application 唯一词汇表)
  │ create_and_dispatch()
  ▼
[3] Coordinator           ── lifecycle/lifecycle.execute        (resolve intent → select driver)
  │ drivers.select(mode)
  ▼
[4] RunLoopDriver         ── execute/loop_drivers.CognitiveRunDriver
  │                          (build Agent/Team → runnable.run)
  ▼
[5] Application facade    ── application/api.Agent.run          (forward to self._agent.run)
  │
  ▼
[6] Runtime               ── runtime/runtime_loop.CognitiveRuntime.run
  │                          new_state + require_executable_plan + STARTED + new_driver()
  ▼
[7] Binding + Executor    ── DeclarativeRuntimeBindings
  │                          + DeclarativeRuntimeDriver
  │                          + DeclarativeExecution.execute
  │                          + GraphAssembler.assemble
  │                          + interpreter.run / .resume        ★ 图计划真正被装订并解释
  ▼
  Result → DriverOutcome → JSONResponse / SSE
```

每一层只看见下一层；只有第 7 层知道图计划长什么样。

## 9. 不变量速查

| 不变量 | 由哪一层强制 | 怎么强制 |
|---|---|---|
| Transport 不绑定 Brain/Body/Loop | [0]–[4] | `RunPort` Protocol；`CognitiveRuntime`/`Agent` 从不在 transport import 链中出现 |
| Route 全部 plugin 化 | [0] | routes plugin + `route_registry.install(app)`；`build_routes` 已退役 |
| `mode` 来自 profile，不来自 driver | [4] | `intent.mode` 由 `resolve_run_intent` 出，`drivers.select(mode, ...)` 只选不决定 |
| 同一 binding 同时支持 fresh + resume | [5]–[7] | `Agent.run` 把 facade 调用直接转发给 `CognitiveRuntime.run/resume`；driver 工厂在 binding 闭包里 |
| binding 是 `frozen=True` + phase_executors 是 `MappingProxyType` | [7] | dataclass(..., frozen=True, slots=True) + `MappingProxyType(dict(...))` 双重冻结 |
| plan 与 phase_executors 闭集一致 | [7] | `require_executable_plan()` 反向校验 `executor_capability` 集合 |
| 图遍历写 delta，失败投影写不到下一条边 | [7] | reducer + effect_gateway 写入；finalizer 只投影 |
| checkpoint 跨进程用 `plan_ref` 防串号 | [7] | `interpreter.resume()` 比较 `cursor.plan_ref == expected_plan_ref`，不等就抛 `DeclarativeValidationError("PG-008")` |
| Hook 不能改 State / Decision / 执行路径 | 全局 | `HookEvent` 是闭集枚举；v3 宪法硬约束 |
| 入口都是 202 + `live_url` | [1] | `POST /runs` 返回收据而非 `Result`；结果从 SSE 流出去（[ADR-0092](../adr/0092-durable-session-command-ledger.md)） |

## 10. 改动影响表

| 想改的东西 | 改这一层 | 关键文件 |
|---|---|---|
| 新增 HTTP 路径 | [0] | 新增 routes plugin，或在 `routes_runs_sessions.py:ROUTES` 加 `Route(...)` |
| 改 wire 类型 / 解析规则 | [1] | `command_endpoints.py:create_run` + `terminal/port.py:RunRequest` |
| 把 `RunPort` 换成另一个实现 | [2] | `lifecycle/lifecycle.py:RunLifecycleCoordinator`，它就是 `RunPort` 的默认实现 |
| 切换 driver（profile 决策） | [3]–[4] | 注册新 driver 到 `RunLoopDriverRegistry`；profile enable 对应 plugin |
| 把 facade `Agent` 换成另一个 runtime | [5] | `application/api.py:Agent.__init__` 注入的 `self._agent` |
| `CognitiveRuntime.run` 行为 | [6] | `runtime/runtime_loop.py:135` —— 应警惕扩展；任何"加阶段语义"的改动先有 ADR |
| 改变 binding 冻结策略 | [7] | `runtime/runtime_bindings.py` + `declarative_runtime.py` |
| 改计划本身的装订逻辑 | [7] | `GraphAssembler.assemble` + `binding.new_interpreter`（详见 plan-compile-and-execute-walkthrough §6） |

## 11. 关键文件清单

| 文件 | 职责 |
|---|---|
| `lca/plugins/transport/webserver/routes_runs_sessions.py:53` | 路由 catalog（routes plugin ROUTES） |
| `lca/plugins/transport/webserver/server.py` | webserver plugin 自身：构造 app、lifespan、`route_registry.install` |
| `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py:53` | `create_run` handler |
| `lca/plugins/transport/webserver/handlers/runs/terminal/port.py:60` | `RunPort` Protocol + `RunRequest` / `RunReceipt` wire 类型 |
| `lca/plugins/transport/webserver/handlers/runs/lifecycle/lifecycle.py:55` | `RunLifecycleCoordinator.execute` |
| `lca/plugins/transport/webserver/handlers/runs/execute/loop_drivers.py:104` | `CognitiveRunDriver.execute` |
| `lca/application/api.py:152` | `Agent.run` facade（直接转发到 `CognitiveRuntime.run`） |
| `lca/runtime/runtime_loop.py:62` | `CognitiveRuntime.__init__`（注入 binding） |
| `lca/runtime/runtime_loop.py:135` | `CognitiveRuntime.run`（入口核心） |
| `lca/runtime/runtime_loop.py:179` | `CognitiveRuntime.resume`（镜像入口） |
| `lca/runtime/runtime_bindings.py:111` | `DeclarativeRuntimeBindings` dataclass |
| `lca/runtime/runtime_bindings.py:170` | `assemble(...)` 用 `MappingProxyType` 冻结 phase_executors |
| `lca/runtime/runtime_bindings.py:194` | `require_executable_plan()` 反向校验 |
| `lca/runtime/declarative_runtime.py:75` | `DeclarativeRuntimeDriver`（carrier adapter） |
| `lca/runtime/declarative_runtime.py:32` | `DeclarativeExecution.execute`（4 步装订 + 解释） |

## 12. 同义术语表（与 [plan-compile-and-execute-walkthrough.md](plan-compile-and-execute-walkthrough.md) §14 一致）

- **MTK**（minimal Trusted Core / 最小可信内核）—— 编译器 + 校验器 + 解释器 + Reducer + Effect Gateway 这套稳定机制。
- **phase** —— 7 个语义阶段之一（perceive / think / act / reflect / remember / stop + 可选 observe 类横切）。
- **node** —— phase graph 里一个具体节点（带 id 与 binding）。
- **executor_capability** —— `phase_bindings` 里出现的 ability key，运行时 binding 用它去 `phase_executors` 字典里查实现。
- **`require_executable_plan()`** —— binding 暴露的"plan 是否可执行"反向校验。`CognitiveRuntime.run/resume` 的入口闸。
- **`DeclarativeRuntimeBindings`**（公共 alias: `RuntimeBindings`，[ADR-0110 D5](../adr/0110-plugin-contract-unification-and-naming-convergence.md)） —— 不可变运行闭包；唯一持有 `CompiledRunPlan` 的运行时对象。
- **`plan_ref`** —— `CompiledRunPlan` 的 SHA-256 短摘要，跨进程身份证。
- **seam / provider / adapter / registry / plugin / profile / bundle** —— 见 [glossary.md](glossary.md)。
- **driver / loop driver** —— `RunLoopDriver`；profile 注册的"运行时类型"，决定把请求派给哪个 `Agent`/`Team` 模板。
- **routes plugin** —— ADR-0112 后所有 `Route` 条目都封装为 plugin，由 `route_registry.install(app)` 集中加入 Starlette。

---

[^no-knowledge-leak]: 为什么不把阶段语义塞进 `runtime.run` 或更外层？参见 [ADR-0082](../adr/0082-architecture-review-2026-08-24.md) §Q2 与 [ADR-0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md)。简言之：让 Plan 失去唯一事实源的话，六阶段闭集就会因为 hook/Hook/Topology 平行扩张而失守。

[^routes-as-plugins]: 把 routes 从 `gateway/app.py` 抽到 plugin 是 [ADR-0112](../adr/0112-gateway-routes-as-plugins.md) + [ADR-0119](../adr/0119-webserver-as-plugin.md) 的核心结果。`build_routes` 已退役，plugin 是 route catalog 唯一 SSOT（[ADR-0115](../adr/0115-kernel-transport-boundary.md) §决定 6）。

[^carrier-vs-app]: transport 与 application 的边界由 [ADR-0103](../adr/0103-locked-surface-and-port-policy.md) 与 [ADR-0119-followup-gateway-name-map](../adr/0119-followup-gateway-name-map.md) 落地：`RunPort` 是 wire vocabulary，`RunRequest`/`RunReceipt` 是 wire 数据，二者共同定义 carrier 唯一可调用面。

[^transport-port-policy]: "Gateway 绑定具体认知实现" 明确被 [ADR-0082](../adr/0082-architecture-review-2026-08-24.md) §结论 + AGENTS.md §3 禁止。`RunPort` Protocol 是物理边界——它没有 `Brain`/`Body`/`Agent` 等字段。

[^driver-via-plugin]: "loop.*" seam 是 Profile 选择的运行时类型。`RunLoopDriverRegistry` 是 ADR-0091 / ADR-0110 之后的标准 seam，不在 webserver 自身里 hard-code。

[^same-binding-both-paths]: `CognitiveRuntime.resume` 显式要求 `phase_cursor != None`（`runtime_loop.py:198-203`），错误消息原话引用 ADR-0074/0075 declarative cutover——legacy runtime loop 已被拆除，所以 fresh 与 resume 必须经过同一条 binding 通道。

[^frozen-mapping]: `MappingProxyType(dict(phase_executors))`（`runtime_bindings.py:170`）让任何 mutating 操作直接抛 `TypeError`。这一点也是为什么 `assert_set`/`update` 之类的 monkey-patch 在 runtime 启动后会立刻失败——保护闭集不被绕开。
