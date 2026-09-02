# 2026-09-01 — Spine 强制埋点 · 执行点白名单 + 织入 + 编译期校验设计

> **Status**: Draft, pending user review
> **Parent ADR**: [ADR-0165 — Event Spine 统一事件真相](../../adr/0165-event-spine-unified-log.md)
> **Sub ADR planned**: [ADR-0165-execution-point-enforcement — Execution Point 强制织入与编译期校验](../../adr/0165-execution-point-enforcement.md)
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

**D2.** **主路径 = cordis `ctx.effect` + `ctx.intercept`**。cognition/runtime/agent 内部方法靠 intercept 包;plugin lifecycle 靠 effect 钩。**不允许业务方手写 `@instrument` 装饰器代替**。这是对 ADR-0165 § 三的偏离,需要在 ADR-0165-execution-point-enforcement 明确。

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

**D9.** **事件不是 log,是 stateful claim**。每个事件是"frame N 上的事实 M 发生了",而非"某对象 call 了 spine"。事件**必须携带**足以让他人独立判断"为什么"的字段。

**D10.** **`outcome` 是 enum 不是 bool**。失败有 `success / failure / timeout / cancelled / rejected / retrying / partial / exhausted / void` 等多语义,bool 表达不了。

**D11. — 全自动埋点原则(zero manual fields) + 自发现原则(no closed-list)**

**Part A — 业务方零字段声明**:业务方**不需要声明任何埋点字段**。所有事件字段在 wrap 时由框架**从四类信号源自动 derive**:

| 信号源 | 工具 | 推出字段 |
|---|---|---|
| **TypeAnnotation** | `inspect.signature` + `typing.get_type_hints` | `preconditions`(入参 schema)、`output_schema`、`docstring_captured`、`signature_fingerprint` |
| **运行时观察** | Python runtime(reflection + exception classifier + frame inspect) | `outcome` (return/exception)、`failure_envelope`、`traceback_last_10_frames`、`duration_ms`、`stalled_ms` |
| **ContextVar / 已存在 framework 层** | `SpineContext` + `BudgetContext` + `CircuitBreakerRegistry` | `preconditions`(运行时快照)、`progress.*`、`budget_consumed`、`circuit_breaker_state`、`side_effects` |
| **Plugin Manifest** | `@plugin(tiebreak=..., policy=...)` | `tiebreak_rule`、`policy_id`(插件作者本来就要写 plugin,这只是属性) |

**妥协点(只有这两个)**:`tiebreak_rule`、`policy_id`。这是真·领域知识,框架推不出,但已经写在 plugin manifest 里,**不是新增负担**。

**业务方心智模型**:`def think(self, ctx) -> Decision:` —— 一行代码,**0 字段声明**。事件长这样:

```python
BrainThinkingStarted {
    execution_point: "brain.think.start",
    span_id: 0x_abc...,                  # SpineContext 生成
    parent_span_id: 0x_def...,           # 栈顶
    sequence: 142,                       # 框架递增
    epoch: 17,                           # 框架单调时钟
    causality_id: sha256(signature + ctx_fingerprint),  # 框架 hash
    preconditions: {                     # 框架从 ctx + sig 自动
        "agent_state_has_user_input": True,
        "context_window_within_limit": True,
        "invariants_passed": ["I1", "I2", "I3"],
    },
    docstring_captured: "Brain.think: ctx -> Decision",  # inspect.getdoc
    signature_fingerprint: sha256(...),  # 函数签名
    output_schema: "lca.contracts.Decision",  # signature annotation
    when: 2026-09-01T12:40:00.123Z,      # 框架
    when_corrected: 2026-09-01T12:40:00.124Z,  # NTP
}

BrainThinkingFinished {
    execution_point: "brain.think.end",
    sequence: 143,                       # +1
    parent_event_id: 142,                # 严格前一事件
    outcome: "success",                  # 框架从 return type 推
    duration_ms: 230,                    # 框架算
    return_value_fingerprint: sha256(...),  # 框架 hash 输出
    post_state_delta: {...},             # 框架 diff ctx 前后
    budget_consumed: {"tokens": 432},    # BudgetContext
    circuit_breaker_state: "closed",     # CB registry
    side_effects: [...],                 # framework 层拦截
    prev_event_hash: sha256(...),        # 篡改检测
}
```

**spec 不做事清单**(D11 派生):
- ❌ 不要求业务方写 declaration
- ❌ 不允许业务方写 `@declarative_emit` 装饰器
- ❌ 不允许业务方 raise `StructuredDiagnostic` 异常代替 stdlib 异常(框架归一化)
- ❌ 不需要 profile 写 payload schema

profile **只需要声明 expected behavior**(timeout_ms、retry 策略、circuit breaker 阈值),这是 profile 已经在做的事,不是新增。

**D12. — spine 自身也是 plugin 化的(子系统的子系统)**

**核心反驳**:本 spec 第一轮把 6 个反射器 / classifier / deriver 堆进 `lca/infrastructure/observability/spine/instrumentation/` 包,这是反模式。

LCA 自己设计原则说:**Protocol → Seam → Provider → Adapter → Registry → Plugin**。一个高度模块化的子系统,它的**内部部件本身应该也是 plugin**。如果 spine 内部 6 个部件写死成一个 monolith,那么:

- 替换 SignatureReflector 实现(比如换成 inspect.get_source)必须改 spine 内部
- 给 Production 加 OII-Debug 信息(profile 不同)不可行
- 业务方扩展"自定义异常分类"必须改 framework
- 测试不能单独替换部件 mock

**正确方向**:spine 内部**每一个反射器、classifier、deriver、sink 都是一个 plugin**。spine 自己也是一个 plugin。Profile 决定装配:

```yaml
# profiles/web-standard.yaml(示意)
spine:
  reflectors:     # 提供 auto_source 字段的部件
    - spine.reflector.signature       # 必
    - spine.reflector.context         # 必
    - spine.reflector.budget          # 必
    - spine.reflector.circuit_breaker # 必
  classifiers:
    - spine.classifier.exception.builtin    # Layer-A 已知异常分类
    - spine.classifier.exception.unclass    # Layer-C 兜底
  derivers:
    - spine.deriver.step_tree        # 派生 journal.json
    - spine.deriver.narrative        # 派生 narrative.md
    - spine.deriver.graph            # 派生 graph.dot
    - spine.deriver.live_tail        # SSE
    - spine.deriver.anomaly          # I15/I16 anomaly
  sinks:
    - spine.sink.file                # events.jsonl 真值
    - spine.sink.console             # 开发用
  wraps:                             # 织入方式
    - spine.wrap.ctx_effect          # 监听 plugin lifecycle
    - spine.wrap.ctx_intercept       # 拦截 cognition 方法
    - spine.wrap.assembler           # phase graph 节点包
```

**为什么不"一个 spine 包搞定"**:因为 wiring 决策是 **runtime composition decision**,profile 之间可差很大。Production 装最小子集;OII-Debug 装 introspection profile;Local-Trace 装 console sink;Benchmark 关所有 deriver。

**为什么不是"一个 plugin 包所有反射器"**:测试隔离、版本升级、A/B 都要求部件独立可换。LCA 自己的 `webserver-4-routes-plugin` 之所以拆四个 plugin,就是为了任意组合。

**LCA 是模块化的,它的 spine 应该更模块化** —— 因为 spine 是系统级关注点,粒度更小、复用诉求更高。

**D13. — Source-level trace:文件 + 行号 + 函数 + 变量值(第四轮修订)**

前三轮 spec 的事件**只能告诉你执行协议**(ep = brain.think.start),**不能告诉你代码位置**(`modular_brain.py:142`)、**不能告诉你当时的变量**(`ctx`、`self`、`memory` 的值)。trace 命令拿到的 metadata 是「函数级」,不是「源码级」。**生产事故排查中,这是核心缺失**。

**承诺**:每个 `*.start` 事件**强制**携带**真正的源码位置**(file:line:fn) + **调用栈**(10 帧)+ **locals 的 repr**(`'ctx': CognitiveContext(messages=[...])`,截断到 4KB)。

**关键性质**:
- 框架强制默认开 —— 业务方不写一行代码
- 安全第一 —— `repr()` 不 pickle,不会爆;secret 字段自动 redact
- profile 可调 `max_locals_bytes`,可加 `redact_patterns`
- 与 D11/D12 协同 —— SourceAttacher 是 `spine.reflector.source` plugin,profile 决定装配

详见 § 19 (新章节)。这是 spec 第四轮修订要点。

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
| I12 | 每个事件字段必填,且 `auto_source` 不为 `manual`(除 `tiebreak_rule`、`policy_id` 外) | schema 校验,FieldSourceRule | PR-7 |
| I13 | 同一 execution_point 在同 span 内的事件序列严格 `start` → N 个 `progress?` → `end`(success/failure) | sequence 链校验,PhaseMachine | PR-7 |
| I14 | 每个 event 的 `failure_envelope`(若 outcome≠success)**必须**含 `what_was_tried`、`what_was_NOT_tried`、`recoverable`、`retry_recommended`;否则 spine fail-fast | EnvelopeCompleteness check | PR-7 |
| I15 | 框架维护一个**可生长的** edge case catalog;新 case 出现时无需事先全列举 —— 异常 classifier 兜底 + AnomalyDeriver 自检发现未见过的模式 | EdgeCaseDiscoveryRuntime + AnomalyDeriver | PR-7 |
| I16 | AnomalyDeriver 必派生 stuck/cycle/over-budget 信号;UI 默认显示 anomaly banner | AnomalyDeriver build-time 装载 | PR-7 |
| I17 | 每个 `*.start` 事件强制包含 `source_location` / `call_frames` / `locals_snapshot`;`*.end` 包含 `locals_diff`;缺则 fail-fast | SourceAttacher plugin + I17 schema check | PR-9 |

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
    sequence: int | None = None                            # 新增,run 内严格单调
    epoch: int | None = None                               # 新增,跨 run 单调
    causality_id: str | None = None                        # 新增,hash(input)
    outcome: Outcome | None = None                         # 新增,见 D10
    when: datetime                                         # 已有
    when_corrected: datetime | None = None                 # 新增,NTP 修正
    run_id: str                                            # 已有
    step_id: str | None = None                             # 已有
    prev_event_hash: str | None = None                     # 新增,篡改检测
    payload: dict[str, Any]                                # 已有
```

- **execution_point** 与 EXECUTION_POINTS 对齐;不在白名单 → fail-fast `UnknownExecutionPoint`。
- **channel** write-once,emitter 注册事件类型时声明。
- **span_id / parent_span_id** 形成 tree(§ 5)。
- **sequence** 严格 +1 在同一 span 内。I13 保证 start→N×progress→end。
- **epoch** 跨 run 单调,用作 de-dup / replay ordering。
- **causality_id = sha256(signature_fingerprint + ctx_fingerprint + clock_skew_corrected_epoch)** — 同输入同 ID,跨 run 可 grep。
- **outcome** 完整 enum。
- **prev_event_hash** = sha256(serialize(prev_event)) — 启动期可篡改检测 + 截断行定位。

### 4.2 字段必填 + auto_source 表(D11 落地)

| 字段 | 必填 | auto_source | 推出器 |
|---|---|---|---|
| `execution_point` | ✅ | `manifest_const` | manifest.py 的 enum |
| `channel` | ✅ | `caller_decl` | 事件类注册时声明(注册一次,所有 emit 复用) |
| `span_id` | ✅ | `SpineContext.generate()` | wrap 时 |
| `parent_span_id` | ✅(非根) | `SpineContext.stack_top()` | wrap 时 |
| `sequence` | ✅ | `SpineContext.next_sequence()` | wrap 时 |
| `epoch` | ✅ | `SpineClock.next_epoch()` | wrap 时 |
| `causality_id` | ✅ | `inspect.signature(callable) + context.fingerprint()` | wrap 时 |
| `outcome` | ✅(end 事件) | `return_type_or_exception` | wrap 后;return type → outcome, raise → exception_classifier → outcome |
| `preconditions` | ✅(start 事件) | `signature_signature_context` | wrap 时;`inspect.signature` + `Context.snapshot()` |
| `post_state_delta` | ✅(end 事件) | `context_diff` | wrap 时;`Context.before_after_diff` |
| `docstring_captured` | optional | `inspect.getdoc` | wrap 时 |
| `signature_fingerprint` | ✅ | `inspect.signature.encode()` | wrap 时 |
| `return_value_fingerprint` | ✅(end 事件) | `hashlib.sha256(result)` | wrap 后 |
| `output_schema` | ✅ | `inspect.get_type_hints` | wrap 时 |
| `input_fingerprint` | ✅ | `hashlib.sha256(args/kwargs)` | wrap 时 |
| `duration_ms` | ✅(end 事件) | `time.perf_counter` | wrap 时 |
| `when` | ✅ | `datetime.utcnow()` | wrap 时 |
| `when_corrected` | ✅ | `ntp_corrected()` | wrap 时(同步 NTP 偏移) |
| `prev_event_hash` | ✅ | `sha256(serialize(prev))` | wrap 时 |
| `side_effects` | ✅(end 事件, 如适用) | `framework_observer.observe()` | 每次 fs write / net call / tool invoke 时 |
| `budget_consumed` | ✅(end 事件) | `BudgetContext` | wrap 时;框架全局 token 计数 |
| `circuit_breaker_state` | ✅(end 事件, 如适用) | `CircuitBreakerRegistry` | wrap 时 |
| `progress.*` | optional(长 run) | `interceptor.observe()` | 通过 StreamTap / BudgetContext 推 |
| `cycle_count` | ✅(end 事件) | `SpineContext.ep_call_count` | wrap 时自检 |
| **`tiebreak_rule`** | optional(仅 gate) | **`plugin_manifest_decl`** | 业务方在 @plugin 装饰器写 `tiebreak=` |
| **`policy_id`** | optional(仅 gate/reducer) | **`plugin_manifest_decl`** | 业务方在 @plugin 装饰器写 `policy=` |

**I12 校验**:每个字段必填;`auto_source ∈ {signature, runtime, context, framework_observer, plugin_manifest_decl}` —— **`manual` 不在允许来源列表**(除 `tiebreak_rule`、`policy_id` 外,这两条已在 `@plugin` 写过)。

### 4.3 Channel 用法  *(合并到 § 4.1;见上文)*

### 4.4 失败 envelope(I14)

每个 `outcome ∈ {failure, timeout, cancelled, rejected, exhausted}` 的事件**必须**携带:

```python
failure_envelope: {
    exception_type: str,                    # 框架从 type(e).__name__ 推
    exception_message: str,                 # 框架 str(e)
    traceback_last_10_frames: list[str],    # 框架截断 traceback
    input_fingerprint: str,                 # 框架 hash(args)
    what_was_tried: list[AttemptRecord],    # 框架从 SafeExecutor 拉 retry chain
    what_was_NOT_tried: list[str],          # 框架查 declared fallback vs actual
    downstream_blast_radius: list[str],     # 框架推哪些后续事件被取消
    recoverable: bool,                      # 框架从异常类型 classifier
    retry_recommended: bool,                # 框架查 retry policy
    circuit_breaker_state: str,             # 同上
    edge_case_id: str,                      # 框架归类到 edge_case_catalog
}
```

**I14 校验**:`build_wrap_spec` 时对每个 wrapped executable 检查 `envelope_completeness() == True`,否则 spine fail-fast 拒 emit。

### 4.5 Edge case **discovery** 而非 enumeration(I15)

> **核心反驳**:edge case **不可**完整列举。系统会遇到从没见过的新 case。网络抖动、CPU 抢占、新 plugin 互冲、没有预料的 LLM 输出格式 —— 任何列表都漏。

**设计核心**:框架不列举 edge case,而是构建一个**自我发现**(self-discovering)环境 —— 任何异常状态、不变量违反、行为偏离,都会被框架捕获并显式化为可观察事件。**新 case 自动登记**,无需业务方列举。

#### 三层发现机制

| 层 | 触发 | 输出事件 | 来源 |
|---|---|---|---|
| **Layer-A:已知分类器**(BUILTIN_MAP) | 框架认识的异常类型(asyncio.TimeoutError / ConnectionError / PermissionError / OverflowError / 60+ 种) | 自动 emit 对应 typed edge event(`Timeout` / `NetworkUnavailable` / 等) + auto-set `outcome` + `failure_envelope.edge_case_id` | ExceptionClassifier(I14 / § 7.5.2) |
| **Layer-B:不变量违例检测器**(runtime anomaly) | 不需要预知哪些错 —— 检测**违反不变量**的行为模式 | emit `AnomalyDetected(kind, ep, evidence)` | AnomalyDeriver(§ 4.6) |
| **Layer-C:开放域探测器**(unknown error detector) | 任何**不属于 Layer-A 也不被 Layer-B 捕捉**的异常 | emit `UnclassifiedError(exception_type, exception_module, frames_signature, similar_to=None, first_seen=true)` | framework 兜底 |

**新 case 出现时的真实路径**(举例):

```text
某天 LLM provider 引入新 SDK 版本,抛 "ProviderBadRequestError",
这个异常 framework 没见过:

Layer-A: BUILTIN_MAP 没这层 → 跳过
Layer-B: 不变量检查未触发 → 跳过
Layer-C: framework 兜底兜到 → 自动 emit:
   UnclassifiedError {
     exception_type: "ProviderBadRequestError",
     exception_module: "provider_sdk.exceptions",
     frames_signature: sha256(traceback),
     similar_to: null,         # 全新 case,无相似
     first_seen: true,         # 标记"我第一次见"
     when_first_seen: timestamp,
     context_at_exception: {  # 框架已捕获全 context
       tool_called: "executeCode",
       llm_call_id: "abc123",
       budget_consumed_before_error: 1200,
       circuit_breaker_state: "closed",
     },
     recommended_clinical_trial: "review ProviderBadRequestError; add to BUILTIN_MAP if recurring",
   }
```

**业务方心智模型**:故障出现 → 必有事件。**没有"沉默故障"**。事件可以标 `first_seen=true` 提示「这是第一次出现,你没见过」,但**该有的观察数据全有**。

#### 不变量违例(Layer-B)的范围明确

| 不变量类别 | 检测器 | 输出 |
|---|---|---|
| 时间 | duration_ms > declared.timeout_ms × 0.94 | AnomalyDetected(kind=near_timeout, ep=X, ratio=0.94) |
| 周期 | 同 execution_point 在同 span 内连续 > MAX_REPEATS 次 | AnomalyDetected(kind=cycle, ep=X, repeats=N) |
| 序列 | start 出现但 end 没出现,> expected_window | AnomalyDetected(kind=stuck, ep=X, since_ms=Y) |
| 进度 | progress event 跨 N 时间窗口停止更新 | AnomalyDetected(kind=stalled, ep=X, stalled_ms=Z) |
| 因果 | 应该 exit 但没 exit / 应该 pause 但没 pause | AnomalyDetected(kind=state_machine_violation, ep=X, expected=Y, actual=Z) |
| 资源 | budget_consumed 接近 limit 但无 BudgetExceeded 声明 | AnomalyDetected(kind=near_budget, ep=X, ratio=0.94) |
| 一致性 | input_fingerprint 在多次相邻调用相同(可能 dedup 误判) | AnomalyDetected(kind=collision, ep=X, fingerprint=Y) |
| 副作用 | side_effects.added 但没对应 end event | AnomalyDetected(kind=orphan_side_effect, ep=X, side_effect=Z) |

**8 类不变量违例**足够覆盖"出问题"的常见特征 —— 因为 **违反不变量 = 出问题**,不依赖于事先知道错的形式。

#### AnomalyDeriver 与 edge case catalog 的关系

- **edge_case_catalog** 不存"已知 case 列表",**存"已自动分类的 case 索引"** —— ExceptionClassifier 兜底后,如发现异常类型已见过,直接复用历史 envelope;首次见则标 `first_seen=true`。
- catalog 自动成长:运营期间凡遇到新异常类型,**自动加索引**(无显式重新部署),下次相同异常走历史 envelope。
- catalog 增长 = 框架"渐进式增加对世界的认识",**bug fix 不再"等下次出现"** —— 异常出现即记录,出现 3 次后自动 tag recommendation「add to BUILTIN_MAP」。

**I15 校验目标**:**不是"列举全"**,而是 **"未列举的 case 必须能被自动分类为 UnclassifiedError 并保留完整 context"**。

#### 业务方心智模型再次更新

```text
旧心智模型:
  edge case 必须被列举 → 列举全 → 不可能 → 系统漏 case

新心智模型:
  框架观察不变量违例 + 异常兜底 →
    已知 → 标 known_edge_case + 完整 envelope
    异常但已知 → 标 similar_to + recategorize recommendation
    完全未知 → 标 first_seen + 全 context 捕获 + 推荐下次分类
  **没有未观察的故障** —— 只有"已知故障的子集";
  故障发生时,不论已知未知,都有完整可读的事件记录
```

**这是 plugin framework 能做到的** —— 因为 framework 是所有路径的必经点。框架看到所有事件、看到所有异常、看到所有不变量违例,自然能自我发现新 case。

### 4.6 派生视图(读 spine,不写 spine)

| Deriver | 输入 | 输出 | 生命周期 |
|---|---|---|---|
| `StepTreeDeriver` | events.jsonl | journal.json (step-tree) | run end 后异步 |
| `NarrativeDeriver` | events.jsonl | journal.narrative.md | run end 后异步 |
| `GraphDeriver` | events.jsonl + phase_graph spec | phase_graph.dot | run end 后异步 |
| `LiveTailDeriver` | events.jsonl | SSE 推送 | run live |
| `MetricsDeriver` | events.jsonl | Prometheus(可选)| run end 后 |
| **`AnomalyDeriver`** | events.jsonl + profile 声明 | anomaly report (stuck / cycle / over-budget) + root cause hypothesis | run live + run end 后补全 |

**AnomalyDeriver**(PR-7 新增):
- 周期扫描事件,匹配 `"stuck" pattern`(started_X → never_completed_X within expected_window)→ emit `AnomalyDetected(kind=stuck, ep=X, since_ms=Y)`
- 匹配 `"cycle" pattern`(同 execution_point 在同 span 内 sequence 差 < N 的连续出现 > M 次)→ emit `AnomalyDetected(kind=cycle, ep=X, repeats=M, span_ids=...)`
- 匹配 `"over_budget"`(duration_ms > declared.timeout_ms × 0.94)→ emit `AnomalyDetected(kind=near_timeout, ep=X, ratio=0.94)`
- UI 默认显示 anomaly banner(不静默)

### 4.7 派生文件布局(取代 ADR-0164/0165 现有 4 文件)

```text
traces/runs/<run_id>/
├── events.jsonl              # ★ 真值
├── journal.json              # 派生:StepTreeDeriver(Phase B 后取代旧 backend)
├── journal.narrative.md      # 派生:NarrativeDeriver
├── phase_graph.dot           # 派生:GraphDeriver(新增)
├── manifest.json             # 保留
├── profile_snapshot.json     # 保留
├── anomaly_report.json       # 派生:AnomalyDeriver(PR-7 新增)
└── events.legacy.jsonl       # 旧 file(Phase B rename 兜底,可选)
```

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
    "llm.stream.stall",
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
def wrap_instrument(runnable: Callable, node_id: str, *,
                    execution_point_start: str = "phase_graph.node.start",
                    execution_point_end: str = "phase_graph.node.end",
                    edge_cases: tuple[str, ...] = ()) -> Callable:
    @wraps(runnable)
    def wrapper(*args, **kwargs):
        with spine.span(f"phase_node.{node_id}",
                        execution_point=execution_point_start) as span:
            spine.append(PhaseNodeStarted,
                         execution_point=execution_point_start,
                         span=span)  # 其余字段由 § 7.5 自动装配
            try:
                result = runnable(*args, **kwargs)
                spine.append(PhaseNodeFinished,
                             execution_point=execution_point_end,
                             outcome="success",  # 自动从 return_type 推
                             span=span)
                return result
            except Exception as e:
                # 不需要业务方手动 raise Diagnostic
                # framework 的 builtin_exception_classifier 自动归类
                failure_envelope = ExceptionClassifier.classify(
                    e, runnable, args, kwargs, edge_cases)
                spine.append(PhaseNodeFailed,
                             execution_point=execution_point_end,
                             outcome=ExceptionClassifier.to_outcome(e),
                             failure_envelope=failure_envelope,
                             span=span)
                raise
    wrapper.__lca_instrumented__ = True
    wrapper.wrap_provenance = "assembler"
    return wrapper
```

### 7.5 反射式自动字段装配(I12 落地) + Plugin 化部件(§ 7.6 / D12)

> **本节第一版把所有反射器写成单包内的类。这违反 D12,已重写。**

wrap 函数**不允许业务方手工填字段**;全部由 **field producers** 在 wrap 时注入。这些 field producers **每一个都是独立的 plugin**(§ 7.6),不是单包内 monolith。

**Seam 协议**(在 `lca/contracts/observability/spine/`):

```python
# lca/contracts/observability/spine/producer.py
class FieldProducer(Protocol):
    """任何一个能往事件注入 (key, value) 的部件。"""

    name: str                          # 用于 debug + assembly order
    priority: int                      # 数值小 → 早注入
    enabled: bool                      # profile 可关

    def produce(self, *, fn: Callable,
                args: tuple, kwargs: dict,
                ctx: Any, span: SpanContext,
                phase: Literal["pre", "post", "exception"]
                ) -> dict[str, Any]:
        """返回要注入的字段 dict;空 dict 表示本事件不产生字段。"""
        ...
```

每个 reflector / classifier / deriver 都满足 FieldProducer。

#### 7.5.1 Signature Reflector plugin — 提供 signature_fingerprint / output_schema / preconditions

```python
# lca/plugins/observability/spine/reflectors/signature.py
from lca.contracts.observability.spine.producer import FieldProducer
from lca.harness.plugin_api import plugin, PluginContext

class SignatureFieldProducer(FieldProducer):
    name = "spine.reflector.signature"
    priority = 10  # 早
    enabled = True

    def produce(self, *, fn, args, kwargs, ctx, span, phase):
        if phase != "pre":
            return {}
        sig = inspect.signature(fn)
        hints = typing.get_type_hints(fn)
        return {
            "signature_fingerprint": sha256(repr(sig).encode()).hexdigest(),
            "input_params": [p.name for p in sig.parameters.values()],
            "input_fingerprint": sha256(pickle_safe(args) + pickle_safe(kwargs)).hexdigest(),
            "output_schema": str(hints.get("return", None)),
            "docstring_captured": inspect.getdoc(fn),
            "is_async": inspect.iscoroutinefunction(fn),
        }

@plugin(
    id="spine.reflector.signature",
    provides=("field_producer.signature",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    description="auto-source: TypeAnnotation. provides signature_*, output_schema, docstring, input/output fingerprint.",
    test_suite="tests.lca_plugins.observability.spine.test_reflector_signature",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    ctx.provide("field_producer.signature", SignatureFieldProducer())
```

#### 7.5.2 Exception Classifier plugin — 提供 outcome / failure_envelope

```python
# lca/plugins/observability/spine/classifiers/exception_builtin.py
class ExceptionBuiltinClassifier(FieldProducer):
    name = "spine.classifier.exception.builtin"
    priority = 30
    enabled = True

    BUILTIN_MAP = {
        asyncio.TimeoutError: ("timeout", "Timeout"),
        asyncio.CancelledError: ("cancelled", "Cancel"),
        ConnectionError: ("failure", "NetworkUnavailable"),
        PermissionError: ("rejected", "PermissionDenied"),
        # ... 60+ 异常类型
    }

    def produce(self, *, fn, args, kwargs, ctx, span, phase):
        if phase != "exception":
            return {}
        exc = ctx.current_exception
        exc_type = type(exc)
        outcome, edge_id = self.BUILTIN_MAP.get(exc_type, (None, None))
        if outcome is None:
            return {}  # 本 producer 不覆盖;留给 unclass
        return {
            "outcome": outcome,
            "edge_case_id": edge_id,
            "failure_envelope": self._build_envelope(exc, fn, args, kwargs, edge_id),
        }

@plugin(
    id="spine.classifier.exception.builtin",
    provides=("field_producer.classifier_builtin",),
    requires=("safe_executor",),
    layer="L0",
    kind=PluginKind.SEAM,
    description="Layer-A known exception classifier. 60+ stdlib types → outcome + envelope.",
    test_suite="tests.lca_plugins.observability.spine.test_classifier_builtin",
)
async def setup(ctx, config): ctx.provide(...)
```

#### 7.5.3 Context Reflector plugin — 提供 budget_consumed / circuit_breaker / side_effects

```python
# lca/plugins/observability/spine/reflectors/context.py
class ContextFieldProducer(FieldProducer):
    name = "spine.reflector.context"
    priority = 20
    enabled = True

    def produce(self, *, fn, args, kwargs, ctx, span, phase):
        if phase == "pre":
            return {
                "preconditions": self._capture_preconditions(ctx, fn),
                "budget_at_entry": BudgetContext.snapshot(),
                "circuit_breaker_state_entry": CircuitBreakerRegistry.get(fn),
            }
        if phase == "post":
            return {
                "post_state_delta": ContextDiffer.diff(...),
                "budget_consumed": BudgetContext.diff(...),
                "circuit_breaker_state": CircuitBreakerRegistry.get(ctx),
                "side_effects_added": FrameworkObserver.diff(...),
            }
        return {}

@plugin(id="spine.reflector.context", provides=("field_producer.context",), ...)
async def setup(ctx, config): ...
```

#### 7.5.4 Edge Case Discovery plugin — Layer-C 兜底异常捕获

```python
# lca/plugins/observability/spine/classifiers/exception_unclass.py
class UnclassClassifier(FieldProducer):
    """Layer-C: 任何不在 builtin map 的异常 → UnclassifiedError + 全 context。"""

    name = "spine.classifier.exception.unclass"
    priority = 99  # 兜底,最后
    enabled = True

    def produce(self, *, fn, args, kwargs, ctx, span, phase):
        if phase != "exception":
            return {}
        exc = ctx.current_exception
        # builtin 已经被前面的 7.5.2 抢答 → 这里只接住它的空 produce
        # 但我们要做的是发 UnclassifiedError 事件本身,不是填 failure envelope
        sig = self._exception_signature(exc, fn, ctx)
        similar = self._find_similar(sig)
        record = self._seen_signatures.setdefault(sig, EdgeCaseRecord(
            exception_signature=sig,
            first_seen=similar is None,
            seen_count=(similar.seen_count + 1) if similar else 1,
        ))
        # 关键:UnclassifiedError 是事件本身,不是 failure_envelope 字段
        self.spine.emit(UnclassifiedError(
            exception_signature=record.exception_signature,
            first_seen=record.first_seen,
            seen_count=record.seen_count,
            context_at_exception=self._capture_full_context(exc, fn, ctx),
            recommended_action=("add_to_BUILTIN_MAP" if record.seen_count >= 3 else None),
            span=span,
        ))
        return {"outcome": "failure"}  # 兜底 outcome

@plugin(id="spine.classifier.exception.unclass", provides=("field_producer.classifier_unclass",), ...)
async def setup(ctx, config): ...
```

#### 7.5.4.1 AnomalyDetector plugin(I15 Layer-B)

```python
# lca/plugins/observability/spine/derivers/anomaly.py
class AnomalyDetector(FieldProducer):
    """8 类不变量违例检测(I15 Layer-B)。订到 spine 流,产出 AnomalyDetected 事件。"""

    name = "spine.deriver.anomaly"
    priority = 50
    enabled = True

    # I16 校验要求:8 类 detector 全有
    DETECTORS = (
        "near_timeout",         # duration_ms > declared.timeout_ms × 0.94
        "cycle",                # 同 ep 在同 span 内 repeats > MAX_REPEATS
        "stuck",                # start 没 end,since_ms > expected_window_ms
        "stalled",              # progress event 跨窗口停止更新
        "state_machine_violation",  # 应该 exit / pause 但没
        "near_budget",          # budget_consumed / limit > 0.94
        "collision",            # 多次相邻 input_fingerprint 相同
        "orphan_side_effect",   # side_effects.added 但无对应 end event
    )

    def produce(self, *, fn, args, kwargs, ctx, span, phase):
        if phase not in ("pre", "post"):
            return {}
        # 实际处理由 spine.subscribe 调 on_event(...)
        return {}

    def on_event(self, event: EventRecord) -> None:
        for detector_name in self.DETECTORS:
            fn_detector = getattr(self, f"_check_{detector_name}")
            anomaly = fn_detector(event)
            if anomaly:
                self.spine.emit(AnomalyDetected(
                    kind=detector_name,
                    execution_point=event.execution_point,
                    span_id=event.span_id,
                    evidence_hash=sha256(event.serialize()).hexdigest(),
                    **anomaly,
                ))

@plugin(
    id="spine.deriver.anomaly",
    provides=("field_producer.anomaly",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    description="I15/I16 invariant violation detection (8 detectors). Emits AnomalyDetected events.",
    test_suite="tests.lca_plugins.observability.spine.test_anomaly_detector",
)
async def setup(ctx, config): ...
```

**I16 校验**:AnomalyDetector plugin 必须 subscribed;缺则 build fail。8 类 detector 必须每类对应一个 `_check_*` 方法;缺则 build fail。

#### 7.5.5 SpanTree plugin — 提供 sequence / span_id / parent_span_id(I13)

```python
# lca/plugins/observability/spine/spantree.py
class SpanTreeProducer(FieldProducer):
    name = "spine.spantree"
    priority = 5   # 最先注入:其他 producer 依赖
    enabled = True

    def produce(self, *, fn, args, kwargs, ctx, span, phase):
        if phase == "pre" and not span.span_id:
            span.span_id = self._gen_id(span.execution_point)
            span.parent_span_id = self._stack_top_or_none()
            self._stack_push(span)
        if phase == "post":
            span.pop_match = self._stack_pop_match(span.execution_point)
        return {
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "sequence": self._next_sequence(span.span_id),
            "epoch": self._next_epoch(),
            "prev_event_hash": self._last_hash_or_zero(),
            "cycle_count": self._cycle_count(span.execution_point),
        }

@plugin(id="spine.spantree", provides=("field_producer.spantree",), ...)
async def setup(ctx, config): ...
```

#### 7.5.6 装配顺序(由 EmitPipeline plugin 完成)

wrap 函数执行时,**所有 enabled producer plugins 按 priority 顺序产出字段**,最后 EmitPipeline 合并:

```text
wrap_instrument(fn, ep_start, ep_end, edge_cases)
  ├─ 1. EmitPipeline plugin 拉取所有 enabled producer
  │     ├─ 按 priority 升序
  │     ├─ phase="pre" 时一并调 produce(...)
  │     └─ 合并 dict,冲突时 low-priority 优先(早写胜)
  ├─ 2. emit Started 事件(空 payload + producer 注入的字段)
  ├─ 3. result = fn(*args, **kwargs)
  │     └─ 异常时 phase="exception" → builtin + unclass producer 抢答
  ├─ 4. phase="post" 调 produce(...) 合并 post_state_delta 等字段
  └─ 5. emit Finished 事件
```

**注意**:没有任何 `if name == "main"` 找具体类的逻辑——producer list 来自 plugin registry,profile 可关可加。

#### 7.5.7 EmitPipeline plugin(装配车间本身也是 plugin)

```python
# lca/plugins/observability/spine/emit_pipeline.py
class EmitPipeline:
    """spine.append 前的最后一道装配车间;按 priority 拉所有 producer,合并字段。"""

    def __init__(self, producers: list[FieldProducer], assembler: AnomalyDetector):
        self.producers = sorted(producers, key=lambda p: p.priority)
        self.assembler = assembler

    def emit(self, event_cls, *, execution_point, span_ctx, caller_payload=None):
        # 1. 拉所有 producer(pre / post / exception 各自一次)
        pre_fields = {}
        for p in self.producers:
            if not p.enabled: continue
            pre_fields.update(p.produce(phase="pre", span=span_ctx, ...))
        # 2. 异常时
        exc_fields = {}
        if span_ctx.current_exception:
            for p in self.producers:
                if not p.enabled: continue
                exc_fields.update(p.produce(phase="exception", span=span_ctx, ...))
        # 3. 装配 event
        assembled = EventFactory.create(
            event_cls=event_cls,
            execution_point=execution_point,
            span=span_ctx,
            auto_fields={**pre_fields, **exc_fields, **(caller_payload or {})},
        )
        # 4. I12/I13/I14 校验
        self._validate(assembled)
        # 5. 入 spine 真值流 + 触发 AnomalyDetector.on_event
        record = spine.append(assembled)
        self.assembler.on_event(record)  # 8 类不变量检测
        return record

    def _validate(self, event):
        FieldSourceRule.check(event)         # I12
        PhaseMachine.check(event)            # I13
        EnvelopeCompleteness.check(event)    # I14
        assert event.execution_point in EXECUTION_POINTS, "UnknownExecutionPoint"

@plugin(
    id="spine.emit_pipeline",
    provides=("emit_pipeline",),
    requires=("field_producer.*",),  # 等待所有 producer 装好
    layer="L1",  # 整合 producer plugins
    kind=PluginKind.SEAM,
    description="emit pipeline: pulls all enabled FieldProducer plugins by priority, merges, validates I12/I13/I14.",
    test_suite="tests.lca_plugins.observability.spine.test_emit_pipeline",
)
async def setup(ctx, config):
    producer_ids = config["reflectors"] + config["classifiers"]  # 来自 profile
    producers = [ctx.require(pid) for pid in producer_ids]
    anomaly = ctx.require("spine.deriver.anomaly")
    ctx.provide("emit_pipeline", EmitPipeline(producers, anomaly))
```

### 7.6 Spine = composition of plugins(D12 核心)

#### 7.6.1 Spine 顶层 plugin

```python
# lca/plugins/observability/spine/core.py
@plugin(
    id="spine",
    provides=("event_spine", "spine_context"),
    requires=(
        "emit_pipeline",           # 等所有 producer + assembler 装好
        "file_sink",               # 必
        # optional derivers 由 profile 决定:
        # "step_tree", "narrative", "graph", "live_tail"
    ),
    layer="L2",  # 整合 emit_pipeline + sinks
    kind=PluginKind.SEAM,
    description="LCA Spine core. Composes emit_pipeline + sinks + optional derivers into single EventSpine instance.",
    test_suite="tests.lca_plugins.observability.spine.test_core",
)
async def setup(ctx, config):
    pipeline = ctx.require("emit_pipeline")
    sinks = [ctx.require(sid) for sid in config["sinks"]]
    deriver_ids = config.get("derivers", [])
    derivers = [ctx.require(did) for did in deriver_ids]
    spine = EventSpine(pipeline=pipeline, sinks=sinks, derivers=derivers)
    ctx.provide("event_spine", spine)
    ctx.provide("spine_context", SpineContext(spine))
```

#### 7.6.2 Deriver 也是 plugin

```python
# lca/plugins/observability/spine/derivers/step_tree.py
class StepTreeDeriver:
    name = "spine.deriver.step_tree"
    def on_event(self, event): self.step_tree_writer.write(event)

@plugin(id="spine.deriver.step_tree", provides=("step_tree",), layer="L0",
       kind=PluginKind.SEAM, ...)
async def setup(ctx, config):
    ctx.provide("step_tree", StepTreeDeriver(...))
```

每种 deriver(narrative / graph / live_tail / anomaly)都是独立 plugin,profile 可独立开关。

#### 7.6.3 Sink 也是 plugin

```python
# lca/plugins/observability/spine/sinks/file.py
class FileSink:
    name = "spine.sink.file"
    def write(self, event): ...

@plugin(id="spine.sink.file", provides=("file_sink",), layer="L0",
       kind=PluginKind.PRODUCER, ...)
async def setup(ctx, config):
    ctx.provide("file_sink", FileSink(path=config["path"], ...))
```

#### 7.6.4 Wrap 函数也是 plugin

```python
# lca/plugins/observability/spine/wraps/ctx_effect.py
@plugin(id="spine.wrap.ctx_effect", provides=("ctx_effect_wrap",),
       requires=("event_spine",), layer="L0", kind=PluginKind.SEAM, ...)
async def setup(ctx, config):
    spine = ctx.require("event_spine")
    ctx.effect(lambda: spine.emit(PluginMounted, ...))
    # dispose goes to ctx.effect(call=...)
```

#### 7.6.5 完整 plugin 列表(PR-8 抽出)

| Plugin ID | Layer | provides | requires |
|---|---|---|---|
| `spine.core` | L2 | `event_spine`, `spine_context` | `emit_pipeline`, `file_sink` |
| `spine.emit_pipeline` | L1 | `emit_pipeline` | 各 field_producer |
| `spine.reflector.signature` | L0 | `field_producer.signature` | - |
| `spine.reflector.context` | L0 | `field_producer.context` | `safe_executor`, `circuit_breaker_registry` |
| `spine.reflector.runtime` | L0 | `field_producer.runtime` | - |
| `spine.classifier.exception.builtin` | L0 | `field_producer.classifier_builtin` | `safe_executor` |
| `spine.classifier.exception.unclass` | L0 | `field_producer.classifier_unclass` | - |
| `spine.spantree` | L0 | `field_producer.spantree` | - |
| `spine.deriver.anomaly` | L0 | `field_producer.anomaly` | - |
| `spine.deriver.step_tree` | L0 | `step_tree` | - |
| `spine.deriver.narrative` | L0 | `narrative` | - |
| `spine.deriver.graph` | L0 | `graph` | - |
| `spine.deriver.live_tail` | L0 | `live_tail` | `webserver_bootstrap` |
| `spine.sink.file` | L0 | `file_sink` | - |
| `spine.sink.console` | L0 | `console_sink` | - |
| `spine.wrap.ctx_effect` | L0 | `ctx_effect_wrap` | `event_spine` |
| `spine.wrap.ctx_intercept` | L0 | `ctx_intercept_wrap` | `event_spine` |
| `spine.wrap.assembler` | L0 | `assembler_wrap` | `event_spine`, `compile_profile` |

**总数 ~18 plugins,每个 ~50-200 行,职责单一,profile 任意组合**。

#### 7.6.6 Profile 决定装配

```yaml
# profiles/web-standard.yaml(spine 段)
spine:
  reflectors:
    - spine.reflector.signature
    - spine.reflector.context
    - spine.reflector.runtime
    - spine.spantree
  classifiers:
    - spine.classifier.exception.builtin
    - spine.classifier.exception.unclass
  derivers:
    - spine.deriver.anomaly
    - spine.deriver.step_tree
    - spine.deriver.narrative
    - spine.deriver.graph
    - spine.deriver.live_tail
  sinks:
    - spine.sink.file
  wraps:
    - spine.wrap.ctx_effect
    - spine.wrap.ctx_intercept
    - spine.wrap.assembler

# profiles/oii-debug.yaml(spine 段)—— 加深度 introspection
spine:
  reflectors: [..., spine.reflector.debug]
  classifiers: [..., spine.classifier.exception.third_party, ...]
  derivers: [..., spine.deriver.metrics, ...]
  sinks: [..., spine.sink.console, ...]

# profiles/benchmark.yaml(spine 段)—— 最小
spine:
  reflectors: [spine.reflector.signature]   # 最小子集
  classifiers: [spine.classifier.exception.unclass]  # 只有兜底
  derivers: []   # benchmark 关掉 deriver 开销
  sinks: [spine.sink.file]
  wraps: [spine.wrap.assembler]  # 只在 phase graph 包
```

#### 7.6.7 为什么必须 plugin 化(防御性论据)

| 反对 plugin 化(infra 包写死) | 事实 |
|---|---|
| "反正没人会替换" | 测试要替换 mock;不同 profile 要不同行为;第三方要用 —— **不是假设** |
| "performance 开销" | plugin 装配一次性,运行时 producer list 固定;overhead 与包结构相同 |
| "代码分散难查" | 每个 plugin ~50-200 行,职责单一,**反而好查**;新增 plugin 不改 framework |
| "plugin registration 开销" | cordis 已经解决(参见 ADR-0119 webserver plugin template);LCA 自身模式 |
| "难理解" | LCA 整个代码库用 plugin pattern;**spine 例外反而不一致** |

**核心论据**:LCA 自己原则 "Protocol → Seam → Provider → Plugin" 强调**横切关注点必须可插拔**。spine 是横切关注点的典范,**它本身不插拔 = 违反自己原则**。

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

### 10.2 偏离 ADR-0165 的部分(需 ADR-0165-execution-point-enforcement 记录)

- 主路径在 effect, decorator(B 路径)不再被推荐为通用工具;只作为 escape hatch 与回退。
- 自动织入覆盖率优先级高于业务方显式标注。

### 10.3 文档产出

| 类型 | 路径 |
|---|---|
| 本 spec | `docs/superpowers/specs/2026-09-01-spine-execution-points-design.md` |
| ADR-0165-execution-point-enforcement | `docs/adr/0165-execution-point-enforcement.md` |
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
| **PR-7** spine-auto-fields | D9-D11 全部落地 — 反射器 / classifier / deriver / sink / wrap 全部以 plugin 形式定义,Profile 配置 | 中-高 | 5-8 天 |
| **PR-7.1** spine-auto-fields-wiring | 把 PR-7 各种 producer plugin 接入 ctx.intercept / assembler wrap / plugin lifecycle;全部已有 wrap 改用 EmitPipeline | 中 | 2-4 天 |
| **PR-8** spine-plugin-extraction | D12 落地 — 把 § 7.6 表格 18+ plugins 全部装出来;`lca/infrastructure/observability/spine/instrumentation/` 整个包删掉;全 framework 一致 plugin 模式 | 中 | 3-5 天 |
| **PR-9** spine-source-attacher | D13 / I17 落地 — `spine.reflector.source` plugin,每个 `*.start` 必带 source_location + call_frames + locals_snapshot;redact 默认开;OII-Debug profile 开 source_snippet | 中 | 3-5 天 |

**总计:24-42 天(单线),7-9 周(双线)**

### 11.1 兼容性矩阵

| 时点 | events.jsonl | journal.jsonl | journal.json | SSE | 排查 |
|---|---|---|---|---|---|
| PR-1 后 | 新 | 旧 backend 仍写 | StepGroupedBackend | LiveTail | 多文件,以 events.jsonl 为真 |
| PR-2 后 | 新 | 无(→ legacy rename) | Deriver 派生 | LiveTailDeriver | events.jsonl 为主 |
| PR-3 后 | 新 + 自动覆盖 | 无 | Deriver 派生 | LiveTailDeriver | events.jsonl 唯一(框架强制) |
| PR-4 后 | 新 + 自动 wrap | 无 | Deriver 派生 | LiveTailDeriver | phase graph 节点自动有事件 |
| PR-5 后 | 新 + 旧 backend import 失败 | 无 | Deriver 派生 | LiveTailDeriver | CI 强制 |
| PR-6 后 | 新 + orphan | 无 | Deriver 派生 | LiveTailDeriver | 孤儿事件可查 |
| PR-7 后 | 新 + 全自动字段 | 无 | Deriver 派生 | LiveTailDeriver + AnomalyDeriver | `anomaly_report.json` 显式 stuck/cycle/over-budget |
| PR-7.1 后 | 新 + 反射装配线接入 | 无 | Deriver 派生 | LiveTail + Anomaly | 业务方零字段声明,全 framework auto-derive |
| PR-8 后 | 同上,全 framework 一致 plugin 模式 | 无 | Deriver 派生 | LiveTail + Anomaly | `lca/plugins/observability/spine/` 下 ~18 plugins,profile 任意组合 |
| PR-9 后 | 同上,每个 `*.start` 自动含 source_location + call_frames + locals_snapshot | 无 | Deriver 派生 | LiveTail + Anomaly | `trace --locals` 直接看每事件当时的文件/行/变量 |

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
- **不**要求业务方手写埋点字段(I12 / D11);所有字段从 reflect / runtime / context / manifest 自动派生
- **不**允许业务方写 `@declarative_emit` / `@instrument` / StructuredDiagnostic 装饰器或 raise;framework wrap 接管
- **不**允许 profile YAML 写 payload schema;profile 只声明 expected behavior(timeout/retry/CB threshold)
- **不**让 spine 子系统自成一体的 monolith:每个 Reflector / Classifier / Deriver / Sink 都是独立 plugin,profile 决定装配(§ 7.6 / D12)
- **不**在 `lca/infrastructure/observability/spine/instrumentation/` 单包堆 6 个不同职责类;**全部 plugin 化**(§ 7.5 重构 / D12)

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
- [x] 不列举 edge case;采用三层发现机制(§ 4.5 / D11 Part B / I15)
- [x] 所有字段由 D11 信号源自动派生;I12 校验保证 `auto_source ≠ manual`(除 manifest-tied)

## 17. 自发现原则备忘(本 spec 第二轮修订要点)

**用户原话追问**:**"各种 case 包括 edge case 是无法列举完全的。我只是举例。我希望的是复杂的整个链路里面,能有发现问题的环境,是这个插件化框架做到的。"**

这一追问**修正了本 spec 第一版的核心方向**。原 § 4.5 / D11 把 edge case 列成 12 类 + I15 校验要求 "12 类全列",这是反模式 —— 任何列举都漏,且试图列举本身就是错的。

**正确方向**:

| 旧 | 新 |
|---|---|
| "列举 12 类 edge case" | "三层发现机制 + 异常 classifier + 不变量检测 + open-domain fallback" |
| I15: "绑全 12 类触发器,fail-fast" | I15: "未列举的 case 必须能被自动分类为 UnclassifiedError 并保留完整 context" |
| EdgeCaseBinder 写死 trigger_table | EdgeCaseDiscovery 兜底所有异常,自动建索引成长 |
| "框架能列举的错 = 全错" | "框架观察到的错 = 已知错;未观察到的错 = 自动建索引 + 全 context 兜底;**永远不沉默**" |
| 业务方 + framework 列举错 | **业务方不参与列举**;framework 通过不变量违例 + 异常兜底 + 异常相似度检索**自增长认识** |

**这是 plugin framework 真正的设计优势**:framework 是所有路径的必经点,**因此 = 唯一能看到的全量观察点**。不变量检测 + 异常 classifier + 相似度检索,三者合起来形成 self-discovering 观察系统 —— **bug 修复不需要"等下次出现"**,异常出现即落索引,3 次重复后自动建议分类。

**spec 写完后 self-review 至此完整**:
- D9-D11 给出"事件是 claim + 全自动 + 自发现" 三层承诺
- I12-I16 把承诺转为可校验的不变量
- § 4.5 / § 7.5.4 / § 7.5.4.1 给出三层发现的具体实现
- § 17 记录设计原意变更,防后人误读

## 18. Spine 内部插件化原则(D12 / 第三轮修订)

**用户原话追问**:**"这个本来是高度模块化,职责清晰,边界清晰,本身也要做出插件最好。"**

这一追问**修正了本 spec 第二轮的核心设计**。原 § 7.5 把 6 个反射器 / classifier / deriver 堆在 `lca/infrastructure/observability/spine/instrumentation/` 单一包内,这是**违反 LCA 自己设计的扩展路径**。LCA 的原则:`Protocol → Seam → Provider → Registry → Plugin`,每个横切关注点都要 pluggable。spine 是系统中**最横切的关注点**(所有路径必经),它自己**不**可插拔 = 原则违背。

**正确方向**(已写入 § 7.6 / D12):

| 旧(第二轮) | 新(第三轮) |
|---|---|
| 6 个反射器在 `lca/infrastructure/observability/spine/instrumentation/` 单一包 | 18+ plugin 在 `lca/plugins/observability/spine/` 下 |
| `class SignatureReflector: ...` | `@plugin(id="spine.reflector.signature") async def setup(ctx, config): ...` |
| `context.require("field_producer.signature")` | 同样拿,plugin 装配一次,profile 控制开关 |
| 测试中替换具体类时 patch import | 测试中替换 `ctx.require` 的返回值 |
| 替换实现 = 改 framework 内部 | 替换实现 = 写新 plugin + profile 引用 |
| Profile 写死装配清单 | Profile 自由组合 reflectors / classifiers / derivers / sinks / wraps |

**6 个原反射器 / deriver 全部重写为 plugin**:

| 旧类 | 新 plugin |
|---|---|
| `SignatureReflector` | `spine.reflector.signature` |
| `ContextSnapshotter` | `spine.reflector.context` |
| `ExceptionClassifier` | `spine.classifier.exception.builtin` + `spine.classifier.exception.unclass` |
| `EdgeCaseDiscovery` | 拆为 builtin + unclass 两个 plugin(职责分裂) |
| `SpanTreeAssembler` | `spine.spantree` |
| `AnomalyDeriver` | `spine.deriver.anomaly` |

**新 plugin(原 monolith 没有)**:`spine.emit_pipeline`、`spine.core`、`spine.deriver.step_tree`、`spine.deriver.narrative`、`spine.deriver.graph`、`spine.deriver.live_tail`、`spine.sink.file`、`spine.sink.console`、`spine.wrap.ctx_effect`、`spine.wrap.ctx_intercept`、`spine.wrap.assembler`。

**新增 PR-8 `spine-plugin-extraction`**:把 § 7.6 表格 18+ plugins 全部 install,删掉整个 `infrastructure/observability/spine/instrumentation/` 包,framework 一致 plugin 模式。

**Plugin 化防御性论据(反驳常见反对意见)**:
- "反正没人会替换" → 测试、profile、第三方,**会替换**
- "performance 开销" → plugin 装配一次性,运行时 producer list 固定;与 monolith 开销相同
- "代码分散难查" → 每个 plugin ~50-200 行,职责单一,**反而好查**
- "注册开销" → cordis 已解决(参见 ADR-0119 webserver plugin template)
- "难理解" → LCA 全 codebase 用 plugin pattern;**spine 例外反而不一致**

**§ 7.6 的 5 个核心子节**:
- § 7.6.1 `spine.core` 顶层 L2 整合 plugin
- § 7.6.2 deriver 也 plugin(每个一种独立)
- § 7.6.3 sink 也 plugin(file / console 等)
- § 7.6.4 wrap 也 plugin(ctx_effect / ctx_intercept / assembler)
- § 7.6.5 18+ plugin 完整表格
- § 7.6.6 profile 决定装配(web-standard / oii-debug / benchmark 三个示意 profile)
- § 7.6.7 防御性论据

---

## 19. Source-level trace:行号 + 变量值 + 调用栈(第四轮修订)

**用户原话追问**:**"能不能做到记录到哪一个文件、哪一行代码、哪个函数、当时的变量值、这个维度 trace 也有?"**

这一追问修正了本 spec 第三轮的核心盲点。前三轮做的事:

- 知道执行了哪些 execution_point(协议层)
- 知道事件因果链(SpanTree 视图)
- 知道 outcome / failure_envelope(异常层)

**遗漏**:每个 execution_point 进入时**真正的代码位置**(`file.py:42`)、**当前所有变量值**(`locals()`)、**调用栈**(`frames[:10]`)。光知道"brain.think.start" 不够,还要知道"在 `modular_brain.py:142` 的 `think()` 函数里、`ctx.user_input="..."`、`self.memory=...`,这是第几层栈"。

**正确方向**(新增 D13 + I17):

### 19.1 新增承诺 D13

每个 `start` 事件**强制**携带执行时的源位置、调用栈、变量快照。这条不是 plugin 可关 —— 框架强制的默认行为,对应事件基础事实。

### 19.2 新增不变量 I17

每个 `*.start` 事件必含 `source_location` / `call_frames` / `locals_snapshot` 三个字段,缺失则 fail-fast。`*.end` 携带 `return_locals_diff`(变量变化 diff)。

### 19.3 字段定义

```python
class SourceLocation:
    file: str                    # "lca/cognition/brain/modular_brain.py"
    line: int                    # 142
    function: str                # "ModularBrain.think"
    class_name: str | None       # "ModularBrain",module 函数为 None
    method_qualifier: str        # "lca.cognition.brain.ModularBrain.think"
    source_snippet: str | None   # 该行原始源码(可选,debug-only profile)

class CallFrame:
    file: str
    line: int
    function: str
    local_var_keys: tuple[str, ...]    # 仅 keys,不存值,默认
    local_var_summary: dict[str, str]  # key → repr(value),截断

class LocalsSnapshot:
    pre_call: dict[str, str]     # 入口时 locals 的 key→repr(value),截断
    post_call: dict[str, str]    # 出口时 locals
    diff_added: tuple[str, ...]  # 新增 keys
    diff_changed: tuple[str, ...]  # 变化 keys
    diff_removed: tuple[str, ...]  # 删除 keys
```

### 19.4 实现:SourceAttacher plugin

```python
# lca/plugins/observability/spine/reflectors/source.py
class SourceAttacher(FieldProducer):
    name = "spine.reflector.source"
    priority = 8                  # 比 spantree 早一点
    enabled = True                # 默认必开

    def produce(self, *, fn, args, kwargs, ctx, span, phase):
        if phase == "pre":
            frame = inspect.currentframe().f_back
            return {
                "source_location": self._capture_source(frame, fn),
                "call_frames": self._capture_frames(inspect.stack()[1:11]),
                "locals_snapshot": LocalsSnapshot(
                    pre_call=self._safe_locals_repr(frame, max_bytes=4096),
                    post_call=None, diff_added=(), diff_changed=(), diff_removed=()
                ),
            }
        if phase == "post":
            frame = inspect.currentframe().f_back
            # 与 pre_call diff
            return {
                "locals_snapshot": LocalsSnapshot(
                    pre_call=None, post_call=None,
                    diff_added=self._diff_keys(...),
                    diff_changed=self._diff_changed(...),
                    diff_removed=self._diff_removed(...),
                ),
            }
        return {}

    def _capture_source(self, frame, fn) -> SourceLocation:
        return SourceLocation(
            file=frame.f_code.co_filename,
            line=frame.f_lineno,
            function=frame.f_code.co_name,
            class_name=self._enclosing_class(frame),
            method_qualifier=f"{frame.f_globals.get('__name__')}.{frame.f_code.co_qualname}",
            source_snippet=None if not self.config.debug_profile
                       else linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip(),
        )

    def _safe_locals_repr(self, frame, max_bytes: int) -> dict[str, str]:
        """截断 + 防爆 —— 防 memory blowup,防 pickle 失败"""
        out = {}
        total = 0
        for k, v in frame.f_locals.items():
            try:
                r = repr(v)
                if len(r) > 256:
                    r = r[:253] + "..."
                if total + len(r) > max_bytes:
                    out[f"__truncated__"] = f"budget={max_bytes}b"
                    break
                out[k] = r
                total += len(r)
            except Exception:
                out[k] = f"<unreprable:{type(v).__name__}>"
        return out

@plugin(id="spine.reflector.source", provides=("field_producer.source",),
       layer="L0", kind=PluginKind.SEAM,
       description="I17: attach source_location + call_frames + locals_snapshot to every start event.",
       test_suite="tests.lca_plugins.observability.spine.test_source_attacher",)
async def setup(ctx, config):
    ctx.provide("field_producer.source", SourceAttacher(
        debug_profile=config.get("debug_profile", False),
        max_locals_bytes=config.get("max_locals_bytes", 4096),
    ))
```

### 19.5 trace 命令扩展

```sh
lca-ops journal trace run_c9fd294e5371 --include-orphan --locals
```

输出新增 4 列数据:

```text
[trace] run_id=c9fd294e5371, span_count=14

  sequence 142  BrainThinkingStarted
    ep            : brain.think.start
    source        : lca/cognition/brain/modular_brain.py:142 in ModularBrain.think
    call_frames   : 10
      ├─ modular_brain.py:142 think    (locals: ctx, self)
      ├─ modular_brain.py:78  iterate  (locals: iteration)
      ├─ runtime_loop.py:203 _step    (locals: run_state)
      └─ ...
    locals at entry:
      ctx           : CognitiveContext(messages=[...15 items...], user_input="写一个python笑话", ...)
      self          : <ModularBrain reasoner=PromptReasoner critic=SimpleCritic ...>
      memory        : <MemoryBackend size=42 entries>

  sequence 143  BrainThinkingFinished
    ep            : brain.think.end
    source        : lca/cognition/brain/modular_brain.py:142 in ModularBrain.think
    duration_ms   : 230
    locals diff   : +{'decision': Decision(action='respond', text='...')}
                    -{'pending_reasoning': <list of 3>}
                    ~{'iteration': 3 → 4}

  sequence 144  LlmCallStarted
    source        : lca/infrastructure/llm/resolver.py:78 in LlmResolver.call
    call_frames   : [...]
    locals at entry:
      model         : 'deepseek-chat'
      prompt        : str(len=1240, head='You are a friendly assistant...')
      temperature   : 0.7
```

### 19.6 安全边界(D13 关键)

| 类别 | 处理 |
|---|---|
| 包含 secret 的字段(密码、token、key) | `redact_in_locals` 用正则 + SecretDetector 替换为 `<redacted:reason>` |
| 包含 PII(用户输入、邮箱、手机) | `redact_pii` profile-level config;默认关,合规 profile 开 |
| 大对象(binary buffer、image) | `repr()` 自动截断到 256 字符,加上 `<binary:len=N>` |
| 不可 pickle 对象(numpy、asyncio.Task) | fallback `<unreprable:ClassName>` |
| 内存爆 | `max_locals_bytes` 截断(默认 4KB);超限标 `__truncated__` |
| 死循环(self-reference) | 检测 `repr()` 内部 `__repr__` 长度 > 5KB → 截断 |
| 嵌套对象 | 浅一层 dict;不再下钻(spec 不卷 deep serialization) |

**没有不安全的字段** —— `repr()` 永远不出错,只是可能不准。

### 19.7 与 D11 / D12 / 第三轮的协同

| 维度 | 字段来源 | plugin |
|---|---|---|
| 协议层 ep | manifest | framework |
| 字段层 metadata | signature / runtime / context / manifest_decl | producer plugins |
| 异常层 | builtin / unclass classifier | classifier plugins |
| **源层(本节)** | **frame inspect + locals** | **`spine.reflector.source` plugin** |

每层都是独立 plugin + I 不变量,profile 仍可独立关。

### 19.8 关键设计取舍

| 决策 | 取向 | 理由 |
|---|---|---|
| locals 是 `repr()` 还是 pickle | `repr()` | 安全第一;不可 pickle 不爆;UI 调试够用 |
| 默认最大 4KB | 4KB | 多事件叠加不会让 events.jsonl 爆炸 |
| 默认包含所有 locals? | 是 + 截断 | 默认安全;profile `enabled=false` 全关 |
| post_call 完整 locals? | 否,只 diff | pre 已全;post 给 diff 即可;爆量控制 |
| source_snippet 默认开? | 否 | 大文件不必要;OII-Debug profile 开 |
| frame capture 深度 | 10 | 太深没意义,默认 10 与异常 traceback 一致 |
| redactor profile 默认开? | 否 | 由 profile 控制;合规 profile 必开 |
| 全 frame 重写为 SourceContext Snapshot | 否(且建议真值发生) | frame 在切栈时已失;必须在 wrap 内 capture |

### 19.9 修正 § 13 不做的事

- ❌ 不让业务方关 `spine.reflector.source`(`I17` 强制);但允许业务方**配置** `max_locals_bytes` 和 `redact_patterns`
- ❌ 不在生产默认开 `source_snippet` 原文;只在 OII-Debug profile 开
- ❌ 不做 deep serialization(只 repr + 浅 dict)

### 19.10 PR-9:spine reflector source

新增 PR-9:实现 `spine.reflector.source` plugin + I17 不变量校验 + 测试 `test_source_attacher` 覆盖 frame/locals/redact 三路径。

PR-8 之后;估时 3-5 天。
