# 2026-09-01 — Spine 强制埋点 · 执行点白名单 + 织入 + 编译期校验设计

> **Status**: Draft, pending user review
> **Parent ADR**: [ADR-0165 — Event Spine 统一事件真相](../../adr/0165-event-spine-unified-log.md)
> **Sub ADR planned**: [ADR-0165.1 — Execution Point 强制织入与编译期校验](../../adr/0165.1-execution-point-enforcement.md)
> **Incident refrence**: `docs/incidents/2026-09-01-run-c9fd294e5371-blank-spine.md`
> **Date**: 2026-09-01
> **Scope**: webserver → kernel → cognition → runtime → agent → body → llm → phase graph 全执行链路的框架强制埋点;从 EventSpine 单一入口、EXECUTION_POINTS 白名单、织入机制、build-time 5 层校验,到失效语义、SpanTree 派生视图,直至 Graphite stack 6 PR 实施。

---

## 0. 背景

ADR-0165 把"日志"从**业务方主动调用的对象**改成**框架在每个执行点自动触发的横切关注点**,并确立了 EventSpine 单一入口 + 统一 append-only 真值 `events.jsonl`。

ADR-0165 留下三个未充分解答的硬缺口:

1. **白名单缺失**:哪些执行点必须埋?目前散落在 ADR 行文里,没有一份**可校验、可拒绝**的清单。
2. **织入策略模糊**:§ 三路径 A/B 是两条并列路径,未指定主路径;业务方可能选错或偷懒不选。
3. **build-time 校验缺位**:即使 § 不变量列表了 C-new1/C-new2,没有可执行的 hard-fail 校验,只能事后 grep。

用户原话:**"我害怕业务方会忘记;是不是每个函数、模块应该自动有这个插件注入埋点日志?不希望业务方自己加,可能忘记,太多了。"**

这条诉求的核心是 **dedicated-by-construction(框架强制)** 而不是 **manual-by-convention(约定俗成)**。当前现状下 `lca/plugins/tools/cordis_control/creator_promotion.py:87` 仍**手写** `PluginMounted(...)` + `RunStore.append`——这是埋点责任放在业务方的反例。

本 spec 解决:把"业务方记得调"变成"框架织入挡不住"。

---

## 1. 设计决策(高层)

**D1.** **EXECUTION_POINTS 是 close set 白名单,所有执行点必须登记**。新增/删除执行点必须更新 `spine/manifest.py` + 五层校验全过 + 对应测试。Registry 是真值,不是代码扫描结果。

**D2.** **主路径 = cordis `ctx.effect` + `ctx.intercept`**。cognition/runtime/agent 内部方法靠 intercept 包;plugin lifecycle 靠 effect 钩。**不允许业务方手写 `@instrument` 装饰器代替**。这是对 ADR-0165 § 三的偏离,需要在 ADR-0165.1 明确。

**D3.** **assembler compile-time wrap** 是 phase graph 节点的织入机制。`ExecutableNode.runnable` 在 `compile_phase_graph` 时强制包成 instrumented 版本,**业务方写裸函数**。

**D4.** **build-time 五层 hard fail 校验**:
  - Layer-1: `registry.keys() ⊇ EXECUTION_POINTS`(compile_profile 时)
  - Layer-2: 每个 wrap_fn + target_module 必须绑定
  - Layer-3: phase graph 每个 node.runnable 已 instrumented 且有 wrap_provenance
  - Layer-4: importlinter `business-event-isolation` 业务代码禁 import 旧 backend
  - Layer-5: 每个 EXECUTION_POINTS 项必须有一个单元测试断言"事件入 spine"

**D5.** **失效语义**:
  - FD-1 FileSink 抛 → 业务一起抛(hard 终止)
  - FD-2 Deriver 抛 → 不传播业务,spine 记 `spine.deriver_failed` 事件
  - FD-3 Catalog/schema 校验 → fail-fast(`UnknownExecutionPoint` / `UnknownEventType`)
  - FD-4 织入失败 → compile_profile 抛,Kernel 不 boot

**D6.** **承认无法 100% 覆盖**:第三方代码、IO callbacks、stdlib 内部调用不在框架可见之列。框架外层包入是其效果能被埋点的条件,但框架不能进入 stdlib 内部。该边界显式写在 manifest 注释。

**D7.** **保持 LCA 分层不破坏**:不把 cognition/runtime/agent 重写为 plugin(会颠覆分层依赖)。"插件化"是有效实施手段,但不是覆盖一切的解决方案。

**D8.** **SpanTree = 派生视图,不持久化**。每个 event 加 `span_id` + `parent_span_id` 字段,跨层通过 `SpineContext`(ContextVar)传递。`lca-ops journal trace <run_id>` 重建。

---

## 2. 不变量(Invariants)

| ID | 不变量 | 验证手段 | 引入 PR |
|---|---|---|---|
| I1 | 业务代码不直接 import 旧 backend(`engine`/`backends`/`step`/`stream`/`derivers` 子包) | importlinter `business-event-isolation` hard fail | PR-5 |
| I2 | 每个 EXECUTION_POINTS 项有 wrap_fn + target_module 绑定 | Layer-2 校验 | PR-3 |
| I3 | 每个 `ExecutableNode.runnable` 已被 assembler 包(`__lca_instrumented__=True`,`wrap_provenance="assembler"`) | Layer-3 校验 | PR-4 |
| I4 | 业务代码不直接调 `RunStore.append` / `LiveTail.on_event` / `StepGroupedBackend.write` | Layer-4(已存在 ADR-0165)+ 单元测试断言 spine 唯一入口 | PR-1,硬化 PR-5 |
| I5 | spine.append 抛 → 业务一起抛(fail-fast) | 单元 + 注入 FileSink 故障测试 | PR-1 |
| I6 | deriver.on_event 抛 → 不传播业务 | 单元 + 注入 deriver 故障测试 | PR-2 |
| I7 | 孤儿事件显式化 `phase="orphan"` + `reason` ∈ close enum | e2e cancel pre-boot | PR-6 |
| I8 | 执行点新增必须登记到 `EXECUTION_POINTS` + 加测试 + 修订本 spec | `verify_doc_budgets.py` 新增 `execution_points_diff` | PR-3 后 |
| I9 | EventSpine 是公开面,业务只能 `import EventSpine` 和 `emit_event()` helper,不进 deriver | 同 I4 | 持续 |
| I10 | 单事件序列化 ≤ 4KB(O_APPEND PIPE_BUF);> 4KB 走 `<event_hash>.json` 旁路 | FileSink 单元 | PR-1 |
| I11 | deriver recursion depth ≤ 8 | 单元 + FD-2 自检 | PR-2 |

---

## 3. 架构与数据链路

### 3.1 织入生命周期

```text
compile_profile time (Kernel 启动,一次性):
────────────────────────────────────────────
  compile_profile(profiles/web-standard.yaml)
    ├─ registry = SpineInstrumentationRegistry()
    │   for ep in EXECUTION_POINTS:
    │     spec = build_wrap_spec(ep)
    │     registry.register(ep, spec)
    │
    ├─ Layer-1 校验: registry.keys() ⊇ EXECUTION_POINTS
    │   ↑ fail → SpineMissingExecutionPoint
    │
    ├─ for ep, spec in registry.items():
    │   if spec.kind == "ctx_effect":
    │     ctx.effect(spec.wrap_fn)
    │   elif spec.kind == "ctx_intercept":
    │     ctx.intercept(target_module, method_name, wrap_fn)
    │   elif spec.kind == "assembler_wrap":
    │     pass   # 在 compile_phase_graph 阶段处理
    │
    ├─ Layer-2 校验: 每个 spec.wrap_fn + target_module 绑定
    │   ↑ fail → SpineUnboundExecutionPoint
    │
    ├─ spine.append(KernelBootStarted, channel="control",
    │             execution_point="kernel.boot.start")
    └─ return spine

compile_phase_graph time (每个 run 启动):
────────────────────────────────────────────
  compile_phase_graph(plan)
    ├─ for node in plan.nodes:
    │   if not node.runnable.__lca_instrumented__:
    │     node.runnable = wrap_instrument(node.runnable, node_id)
    │     node.runnable.__lca_instrumented__ = True
    │     node.wrap_provenance = "assembler"
    │
    ├─ Layer-3 校验
    │   ↑ fail → SpineUninstrumentedNode(node_id)
    │
    └─ return InstrumentedPlan

runtime(实际执行):
────────────────────────────────────────────
  spine.append(BrainThinkingStarted, channel="fact",
               execution_point="brain.think.start")
    ├─ span_id = SpineContext.current_span_id
    ├─ parent_span_id = SpineContext.span_stack[-1]
    ├─ file_sink.append(serialized)            # FD-1 失败 → 抛
    ├─ for deriver in subscribers:
    │   try: deriver.on_event(serialized)
    │   except Exception: _log_deriver_failure(...)  # FD-2 不传播
    └─ return EventRecord
```

### 3.2 单一真相数据流

```text
business code
  → spine.append(ep=...)                        ★ 唯一入口
    → file_sink   (events.jsonl)               ★ 唯一 append-only 真值
    → derivers    (StepTree | Narrative | GraphDot | LiveTail | Metrics)
      ← 所有下游文件都是派生
```

任何"我直接写 journal.json"的代码不存在(Layer-4 importlinter 强制)。

### 3.3 边界(框架可见 vs 不可见)

| 可见 | 不可见 |
|---|---|
| `transport.route.enter` 等 4 routes plugin mount/unmount | stdlib 内部(`requests.get` 内部调用) |
| `kernel.boot.*`, `kernel.run.*` lifecycle | third-party lib 内部(除非我们 wrap) |
| `agent_loop.iteration.start/end` | IO callback 中间(`uvloop` 内部 epoll) |
| `brain.*.start/end` (intercept on Cognition methods) | process-level signal handlers(除非显式包) |
| `body.tool.execute.start/end` | threads/进程级多进程 fork |
| `llm.call.start/end`, `llm.stream.token` | os.fork 后的子进程(独立 spine 实例) |
| `runtime.reducer.apply`, `runtime.event_publisher.publish` | pytest fixture 内调用(Layer-5 测试 mock spine) |
| `phase_graph.node.start/end` (assembler wrap) | |
| `exception.caught`, `finally` 走 middleware | |

**承认**:做不到 100%。第三方代码内部调不在框架可见之列——但它被 Body 包调用时,Body 这一执行点保证有事件。

---

## 4. 事件 schema 与派生视图

### 4.1 事件 schema 基线

沿用 ADR-0164/0165 现有 `JournalEvent`,不引入新事件类。**新增字段**(全字段 opt-in):

```python
class JournalEvent:
    event_type: ClassVar[str]                              # 已有
    execution_point: ClassVar[str | None] = None           # 新增
    channel: Literal["fact", "control", "error", "diagnostic"]  # 来自 ADR-0165
    span_id: str | None = None                             # 新增
    parent_span_id: str | None = None                      # 新增
    failure: bool = False                                  # 新增
    recorded_at: datetime                                 # 已有,UTC
    run_id: str                                            # 已有
    step_id: str | None = None                             # 已有
    payload: dict[str, Any]                                # 已有
```

- **execution_point** 与 EXECUTION_POINTS 对齐;不在白名单 → fail-fast `UnknownExecutionPoint`。
- **channel** write-once,emitter 注册事件类型时声明。
- **span_id / parent_span_id** 形成 tree(§ 5)。
- **failure** 替代用 `payload["error"]` 散落的 bool。

### 4.2 Channel 用法

| Channel | 用在 |
|---|---|
| `fact` | 所有 `*.start` / `*.end`(成功) / `*.finished` / `*.completed` |
| `control` | `kernel.boot.*` / `kernel.run.*` / `cancel` / `mounted` / `unmounted` |
| `error` | `*.failed` / `*.exception` |
| `diagnostic` | 性能/计数类(`RuntimeObserved` / `ToolRetryProgress` / `PhaseGraphCompiled` / `LlmStreamToken`) |

### 4.3 孤儿事件(phase="orphan")

每个事件有两个 binding axis:

| axis | 取值 |
|---|---|
| `phase` | `"live"`(在 step 中)/ `"orphan"`(无 step) |
| `execution_point` | 来自白名单 |

孤儿事件不进入 StepTreeDeriver 派生,但**全部进 events.jsonl**。这是 ADR-0165 § 三 4 的事件显式化。

`reason` ∈ `{"stop_before_step", "fail_before_step", "pending_tool_call", "cancel_pre_boot", "panic"}` (close enum)。reason 扩展需新 ADR。

### 4.4 派生视图(读 spine,不写 spine)

| Deriver | 输入 | 输出 | 生命周期 |
|---|---|---|---|
| `StepTreeDeriver` | events.jsonl | journal.json (step-tree) | run end 后异步 |
| `NarrativeDeriver` | events.jsonl | journal.narrative.md | run end 后异步 |
| `GraphDeriver` | events.jsonl + phase_graph spec | phase_graph.dot | run end 后异步 |
| `LiveTailDeriver` | events.jsonl | SSE 推送 | run live |
| `MetricsDeriver` | events.jsonl | Prometheus(可选)| run end 后 |

所有 deriver `subscribe()` 注册,spine.append 内部 fan-out。**deriver 不是真值,events.jsonl 是真值**——deriver 文件可重放再生。

### 4.5 派生文件布局(取代 ADR-0164/0165 现有 4 文件)

```text
traces/runs/<run_id>/
├── events.jsonl              # ★ 真值
├── journal.json              # 派生:StepTreeDeriver(Phase B 后取代旧 backend)
├── journal.narrative.md      # 派生:NarrativeDeriver
├── phase_graph.dot           # 派生:GraphDeriver(新增)
├── manifest.json             # 保留
├── profile_snapshot.json     # 保留
└── events.legacy.jsonl       # 旧 file(Phase B rename 兜底,可选)
```

---

## 5. SpanTree 模型(派生视图)

### 5.1 为什么

事件序列扁平时,排查"用户一次请求触发什么"很难。SpanTree 给出 tree 而非 list。

### 5.2 Span 边界

| Span 类型 | 来源 execution_point | 父 span |
|---|---|---|
| `request` | `transport.route.enter` | None(根) |
| `kernel_run` | `kernel.run.start` | request |
| `kernel_boot` | `kernel.boot.start` | kernel_run |
| `agent_iteration` | `agent_loop.iteration.start` | kernel_run |
| `brain_think` | `brain.think.start/end` | agent_iteration |
| `llm_call` | `llm.call.start/end` | 最近激活的 brain_span |
| `body_tool` | `body.tool.execute.start/end` | 最近激活的 agent_span |
| `phase_node` | `phase_graph.node.start/end` | kernel_run |
| `reducer_apply` | `runtime.reducer.apply` | 父 context span |

Span 边界 = `*.start` ↔ `*.end`。spine 维护活跃栈,`*.end` 时 stack pop。

### 5.3 ContextVar 跨层传递

```python
# lca/infrastructure/observability/spine/context.py
class SpineContext:
    span_stack: ContextVar[list[SpanContext]] = ContextVar(...)
    current_run_id: ContextVar[str | None] = ContextVar(...)
    current_step_id: ContextVar[str | None] = ContextVar(...)

with spine.span("brain.think", execution_point="brain.think.start") as span:
    spine.append(BrainThinkingStarted, channel="fact",
                 execution_point="brain.think.start", span=span)
    ...
    spine.append(BrainThinkingFinished, channel="fact",
                 execution_point="brain.think.end", span=span)
```

ContextVar 跨 async / thread / task 传递。`asyncio.copy_context()` 默认 inheritance。

### 5.4 trace 命令

```sh
lca-ops journal trace run_c9fd294e5371 --include-orphan
```

```text
[trace] run_id=c9fd294e5371, span_count=14, orphan_count=3
├─ request [01HM...0] /v1/runs  [control] 200 OK
│  ├─ kernel_run [01HM...1] started
│  │  ├─ kernel_boot [01HM...2] start
│  │  │  ├─ PluginMounted(auditor) [control]
│  │  │  └─ ProfileResolved [control]
│  │  └─ kernel_boot.end [control]
│  ├─ phase_graph.node "perceive" [01HM...3] started
│  │  └─ PhaseNodeFinished (ms=145) [fact]
│  ├─ phase_graph.node "think" [01HM...4] started
│  │  ├─ BrainThinkingStarted [fact]
│  │  ├─ LlmCallStarted (model=deepseek) [fact]
│  │  ├─ LlmCallEnded (ms=2300) [fact]
│  │  └─ BrainThinkingFinished [fact]
│  ├─ [ORPHAN] AgentIterationCancelled [control]
│  │     phase=orphan reason=cancel_pre_iteration
│  ├─ exception.caught [error] CancelledError stack=...
│  └─ kernel_run.stop [control] phase=orphan reason=cancel_at_step_0
```

SpanTree **不持久化**,每次按需从 events.jsonl 重建。

---

## 6. EXECUTION_POINTS 白名单

`lca/infrastructure/observability/spine/manifest.py`:

```python
EXECUTION_POINTS: tuple[str, ...] = (
    # Transport(ADR-0112)
    "transport.route.enter",          # 每个 route handler 入口
    "transport.route.exit",           # 每个 route handler 出口(成功/异常)
    "transport.sse.publish",          # SSE 推送
    # Kernel lifecycle
    "kernel.boot.start",
    "kernel.boot.completed",
    "kernel.run.start",
    "kernel.run.stop",
    "kernel.run.cancelled",
    # Agent loop
    "agent_loop.iteration.start",
    "agent_loop.iteration.end",
    # Cognition
    "brain.perceive.start",
    "brain.perceive.end",
    "brain.think.start",
    "brain.think.end",
    "brain.gate.start",
    "brain.gate.end",
    "critic.eval.start",
    "critic.eval.end",
    "reasoner.reason.start",
    "reasoner.reason.end",
    "synthesizer.merge",
    "skill_router.route",
    "memory.read",
    "memory.write",
    # Body
    "body.tool.execute.start",
    "body.tool.execute.end",
    "body.tool.retry",
    "body.sandbox.enter",
    "body.sandbox.exit",
    # LLM
    "llm.call.start",
    "llm.call.end",
    "llm.stream.token",
    # Runtime
    "runtime.reducer.apply",
    "runtime.checkpoint.create",
    "runtime.resume.start",
    "runtime.resume.end",
    "runtime.event_publisher.publish",
    # Phase graph
    "phase_graph.node.start",
    "phase_graph.node.end",
    "phase_graph.edge.transit",
    # Exception/finally
    "exception.caught",
    "exception.finally",
)
```

任何新增必须 patch 这个常量 + 适配 spec + 加测试(I8)。

---

## 7. 织入机制

### 7.1 三条路径

| 路径 | 适用 | 实现 |
|---|---|---|
| **ctx.effect** | plugin lifecycle(mount/unmount, refresh) | compile_profile 时一次性注册 |
| **ctx.intercept** | cognition/runtime/agent 内部方法(`Brain.think`/`reducer.apply_*`/`runtime_event_publisher.publish`) | compile_profile 时一次性包 |
| **assembler wrap** | phase graph `ExecutableNode.runnable` | compile_phase_graph 时强制 wrap |

业务方**零改动**——所有路径在 framework install 阶段织入。

### 7.2 Forbidden escape hatch

- ❌ 不允许业务方写 `@instrument` 装饰器代替(违反 D2)
- ❌ 不允许 `@opt_out` 跳过埋点(没有 opt-out)
- ❌ 不引入 `sys.settrace` / `sys.addaudithook`(ADR-0165 已否决)
- ❌ 不允许 monkey-patch

**如果某路径你认为不该强制,那就是这条路径不该存在——把它删了,而不是开后门。**

### 7.3 runtime_hooks 实现骨架

```python
# lca/infrastructure/observability/spine/instrumentation/runtime_hooks.py

def install_spine_effects(ctx: Context, *, spine: EventSpine) -> Disposer:
    """把所有 plugin lifecycle 织入到 spine。"""
    dispose_mount = ctx.effect(
        lambda: spine.append(PluginMounted, ...))
    dispose_unmount = ctx.effect(
        call=lambda _: spine.append(PluginUnmounted, ...))
    return lambda: (dispose_mount(), dispose_unmount())
```

### 7.4 assembler wrap 实现

```python
# lca/harness/declarative/compile/assembler.py(改)
def wrap_instrument(runnable: Callable, node_id: str) -> Callable:
    @wraps(runnable)
    def wrapper(*args, **kwargs):
        with spine.span(f"phase_node.{node_id}",
                        execution_point="phase_graph.node.start") as span:
            spine.append(PhaseNodeStarted, ..., span=span)
            try:
                result = runnable(*args, **kwargs)
                spine.append(PhaseNodeFinished, ..., span=span)
                return result
            except Exception as e:
                spine.append(PhaseNodeFailed, failure=True, span=span)
                raise
    wrapper.__lca_instrumented__ = True
    wrapper.wrap_provenance = "assembler"
    return wrapper
```

---

## 8. Build-time 5 层校验

| Layer | 阶段 | 校验内容 | 失败抛错 |
|---|---|---|---|
| 1 | compile_profile | `registry.keys() ⊇ EXECUTION_POINTS` | `SpineMissingExecutionPoint` |
| 2 | compile_profile | 每个 wrap_fn + target_module 绑定 | `SpineUnboundExecutionPoint` |
| 3 | compile_phase_graph | 每个 `ExecutableNode.runnable.__lca_instrumented__=True` + `wrap_provenance="assembler"` | `SpineUninstrumentedNode(node_id)` |
| 4 | CI(importlinter) | `business-event-isolation`:lca.cognition/runtime/agent/application 禁 import 旧 backend 或 deriver | importlinter hard fail |
| 5 | CI(测试) | 每个 EXECUTION_POINTS 项一个测试断言"事件入 spine" | pytest fail |

### 8.1 Layer-4 importlinter 配置

```toml
[[tool.importlinter.contracts]]
name = "business-event-isolation"
type = "forbidden"
source_modules = [
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
]
forbidden_modules = [
    "lca.infrastructure.observability.journal.engine",
    "lca.infrastructure.observability.journal.backends",
    "lca.infrastructure.observability.journal.stream",
    "lca.infrastructure.observability.journal.step",
    "lca.infrastructure.observability.spine.derivers",
]
```

PR-5 期间 dry-run,逐个迁移后 hard fail。

### 8.2 Layer-5 测试模式

```python
def test_brain_think_end_emits_to_spine():
    spine = FakeSpine()
    with install_spine(spine):
        ModularBrain().think(ctx)
    assert spine.calls("brain.think.end") >= 1
```

---

## 9. 失败处理与故障域

### 9.1 故障域

| 域 | 包含 | 行为 | 业务影响 |
|---|---|---|---|
| FD-1 | FileSink.append(atomic write + fsync) | RuntimeError → 抛 | hard 终止 |
| FD-2 | Deriver.on_event 回调 | spine 吞 + 记 `spine.deriver_failed` 事件(走 FD-1) | 不阻断 |
| FD-3 | Catalog/schema 校验 | `UnknownExecutionPoint` / `UnknownEventType` 抛 | hard 终止 |
| FD-4 | ctx.effect / ctx.intercept / assembler wrap | compile_profile 抛 | Kernel 不 boot |

### 9.2 FD-1 写盘矩阵

| 场景 | 行为 | 恢复 |
|---|---|---|
| `OSError(28)` No space | 抛 + 标记 `disk_full_marker` | 运维清理 |
| `OSError(13)` Permission | 抛 + readonly 标记 | 重新挂载 |
| `OSError(5)` I/O error | 抛 + 重试 3 次指数回退 | 仍失败则终止 |
| `fsync` 失败 | 抛 Errno(profile `fail_on_fsync=false` 降级) | 默认抛 |
| 文件被运维截断 | 抛 `SpineStorageLost` | 终止 + 不重建(避免覆盖证据) |

### 9.3 FD-2 circular 防御

```python
_DERIVER_DEPTH = ContextVar("deriver_depth", default=0)
MAX_DERIVER_RECURSION = 8

def spine.append(event, ...):
    depth = _DERIVER_DEPTH.get()
    if depth > MAX_DERIVER_RECURSION:
        raise SpineDeriverRecursion(event)
    tok = _DERIVER_DEPTH.set(depth + 1)
    try:
        file_sink.append(...)
        for deriver in _subscribers:
            try:
                deriver.on_event(...)
            except Exception:
                _log_deriver_failure(deriver, event, exc_info=True)
    finally:
        _DERIVER_DEPTH.reset(tok)
```

### 9.4 进程崩溃防护(SIGKILL 中段)

**策略**:单 event ≤ 4096 bytes(linux PIPE_BUF),`O_APPEND` 保证原子写。事件 > 4KB 走 `<event_hash>.json` 旁路,events.jsonl 只记 `<event_hash>`。启动期 validate hash + 过滤截断行。

### 9.5 Profile 配置

```yaml
spine:
  fail_on_fsync: true   # 默认
  storage_root: ${LCA_STORAGE_ROOT:-/var/lib/lca/traces}
  fsync_interval_ms: 100
  deriver_failure_policy: log_and_continue
  event_size_cap_kb: 64
  max_deriver_recursion: 8
```

---

## 10. ADR 影响与文档

### 10.1 受影响 ADR

| ADR | 影响 |
|---|---|
| ADR-0165 | 本 spec 是它的扩展;不变量、章节保持兼容 |
| ADR-0164 | StepTreeDeriver 取代 StepGroupedBackend,语义不变 |
| ADR-0096 | spine 本身就是 Plugin(ADR-0165 §3.1);Plugin 配 instrumentation |
| ADR-0112 | 4 个 routes plugin 必须自动 emit |
| ADR-0119 | cordis creator_promotion 手写 PluginMounted 改成 ctx.effect |
| ADR-0115 | K7 BOOTSTRAP_NAMES 在 spine install 时注册 |

### 10.2 偏离 ADR-0165 的部分(需 ADR-0165.1 记录)

- 主路径在 effect, decorator(B 路径)不再被推荐为通用工具;只作为 escape hatch 与回退。
- 自动织入覆盖率优先级高于业务方显式标注。

### 10.3 文档产出

| 类型 | 路径 |
|---|---|
| 本 spec | `docs/superpowers/specs/2026-09-01-spine-execution-points-design.md` |
| ADR-0165.1 | `docs/adr/0165.1-execution-point-enforcement.md` |
| 事件目录 | `docs/observability/EVENT-CATALOG.md` |
| 运营手册 | `docs/operations/spine-observability.md`(`trace`/`span`/`orphan` 命令) |
| 开发者入门 | `docs/development/spine-for-plugin-authors.md`(业务方零埋点指南) |
| ADR-0165.2 | `docs/adr/0165.2-orphan-event-model.md`(phase=orphan 语义) |

---

## 11. 实施时间线(Graphite stack)

| PR | 内容 | 风险 | 估时 |
|---|---|---|---|
| **PR-1** spine-foundations | spine/ + FileSink + 单元 + importlinter dry-run + 占位 manifest | 低(纯加) | 2-3 天 |
| **PR-2** spine-derivers | StepGroupedBackend / StepNarrativeWriter / LiveTail → Deriver,旧 API deprecate | 中 | 3-5 天 |
| **PR-3** spine-execution-points | EXECUTION_POINTS + ctx.effect + ctx.intercept + 5 层校验 | 中-高 | 5-7 天(sub-PR 1-4 各 2-3 天) |
| **PR-4** spine-phase-graph-wrap | assembler 强制 wrap + wrap_provenance + 测试补 | 中 | 3-5 天 |
| **PR-5** spine-lint-hardfail | importlinter hard fail + 旧 import 清理 + vulture | 中 | 3-5 天 |
| **PR-6** spine-orphan-events | OrphanEventType + cancel pre-boot 跑通 | 中 | 3-5 天 |

**总计:13-25 天(单线),3-4 周(双线 sub-PR 并发)**

### 11.1 兼容性矩阵

| 时点 | events.jsonl | journal.jsonl | journal.json | SSE | 排查 |
|---|---|---|---|---|---|
| PR-1 后 | 新 | 旧 backend 仍写 | StepGroupedBackend | LiveTail | 多文件,以 events.jsonl 为真 |
| PR-2 后 | 新 | 无(→ legacy rename) | Deriver 派生 | LiveTailDeriver | events.jsonl 为主 |
| PR-3 后 | 新 + 自动覆盖 | 无 | Deriver 派生 | LiveTailDeriver | events.jsonl 唯一(框架强制) |
| PR-4 后 | 新 + 自动 wrap | 无 | Deriver 派生 | LiveTailDeriver | phase graph 节点自动有事件 |
| PR-5 后 | 新 + 旧 backend import 失败 | 无 | Deriver 派生 | LiveTailDeriver | CI 强制 |
| PR-6 后 | 新 + orphan | 无 | Deriver 派生 | LiveTailDeriver | 孤儿事件可查 |

### 11.2 上线阶段

1. **Stage 1**(单用户 internal): PR-1+2+部分 PR-3 → benchmark + 事件密度对比
2. **Stage 2**(高级用户 opt-in): PR-3 完整 + PR-4,`spine.enabled=true` 开关
3. **Stage 3**(默认): PR-5,所有 CI 强制
4. **Stage 4**(强制): PR-6,默认行为变化通告

每 Stage 7 天 soak time,跑 `lca-ops journal sanity`。

---

## 12. 验证矩阵

每 PR 必跑:

```sh
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports                          # 含 EXECUTION_POINTS 校验
uv run mypy lca
uv run pytest                                # 全量
uv run vulture lca --min-confidence 80
scripts/check_kernel_boundary.py             # 含 spine 边界
uv run pytest tests/observability/spine/ -v
uv run pytest tests/lca_kernel/test_boundary.py -v
uv run lint-imports --include business-event-isolation
```

每 PR 必须:

1. 一个新文件 `tests/observability/spine/test_*.py`
2. 更新 `docs/observability/EVENT-CATALOG.md`(自动生成 + 手写注解)
3. `lca-ops journal logs/steps/narrative` 输出格式不变
4. `events.jsonl` 是新增的可读文件

性能预算:

- spine.append 单次 < 50µs P95
- 织入后 cognition.think() 端到端 < 5% 退化
- FileSink fsync 间隔 100ms 或 100 event

---

## 13. 不做的事

- **不**自动迁移老的 7000+ run;用户主动跑 `lca-ops journal migrate --spine`
- **不**引入 OpenTelemetry 强制依赖;`otlp_sink` 可选
- **不**改 SSE wire format;LiveTailDeriver 产物不变
- **不**改 `JournalEvent` 已存在的公共字段;只新增 `execution_point` / `span_id` / `parent_span_id` / `failure`
- **不**立刻删除旧的 `InMemoryJournalStore` / `FilesystemJournalStore`;PR-5 集中清理
- **不**为 plan-mode/subagent 做特殊改造;它们用同一套 spine,只是 plugin-instrument 不同
- **不**100% 覆盖 stdlib / third-party 内部调用;承认边界,框架层 wrap 是必要条件
- **不**允许 opt-out;延迟敏感路径走 spine batch/async 模式或改源码

---

## 14. 替代方案考虑

### A. 业务方手动 emit(现状)
**否决**:这是问题源头。

### B. 用 `sys.settrace` 全局追踪
**否决**:性能不可控,生产不可用。

### C. 只在 SSE tail 上加 flush(已否决的 L1+L2)
**否决**:解决 30% 问题。

### D. OpenTelemetry 替代 in-house spine
**否决**:OTel 是外部 sink,不是真值流。spine 仍保留为内部真值,OTel 作为可选 sink。

### E. 重写 cognition / runtime / agent 为 plugin
**否决**:违背 LCA 分层依赖。改进路径是 D7——保持分层,通过 ctx.intercept 织入框架内部方法。

### F. 装饰器为主,effect 兜底
**否决**:装饰器方案下漏一个就没事件,不满足用户的"牢靠"。

---

## 15. 验收标准

本 spec 完成且正确的必要条件:

1. ✅ EXECUTION_POINTS 覆盖 webserver → backend 全部 10 个执行层
2. ✅ 5 层 build-time hard fail 可演示
3. ✅ 每个 EXECUTION_POINTS 项在 Layer-5 测试覆盖
4. ✅ `run_c9fd294e5371` 复现的 cancel pre-boot 场景在 PR-6 后,events.jsonl 含 phase=orphan 事件
5. ✅ 性能退化 < 5% 端到端
6. ✅ 业务代码 grep 不到旧 backend import
7. ✅ 老 run 仍可读
8. ✅ 全量 pytest 通过 + 87+24+19 kernel/transport/env 测试不退化 + 新增 ~150 测试

---

## 16. 评审 checklist(spec 提交前自审)

- [x] 无 `TBD` / `TODO` / `(...)` 占位
- [x] 内部一致(§ 1 表格 ↔ § 6 清单 ↔ § 7 不变量)
- [x] 单一职责 —— 仅 spine 强制埋点,不捎带 refactor 事件 schema
- [x] 可拆 plan —— 6 PR,每 PR < 5 天;可分 2 个 sub-agent
- [x] 关键决策可追溯到 § 1-8 具体段落
- [x] 风险列表对应放弃条件(§ 11 / § 12)
- [x] 不与现有 ADR 冲突(§ 10)
