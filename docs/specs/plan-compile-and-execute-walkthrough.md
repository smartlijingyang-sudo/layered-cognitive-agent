# 计划编译与执行：从 Profile YAML 到解释器落地

> **状态：** Living note
> **维护者：** @lca-maintainers
> **适用：** 需要理解 `CompiledRunPlan` 如何被编出来、运行时如何被消费、以及"哪些东西在计划里、哪些不在"的所有读者。
> **不在此：** 节点边权细节由 [declarative-phase-graph-spec.md](declarative-phase-graph-spec.md) 负责；命名与术语见 [naming-constitution.md](../design/naming-constitution.md)；架构决策见 [ADR-0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md)、[ADR-0068](../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md)、[ADR-0115](../adr/0115-kernel-transport-boundary.md)。

本文用三段口语化问答给出 LCA 执行计划的"来龙去脉"。配套阅读 [declarative-phase-graph-spec.md](declarative-phase-graph-spec.md) 与 [harness-spine-spec.md](harness-spine-spec.md)。

---

## 0. 一句话总结

**`CompiledRunPlan` 是一张不可变的状态机图，由 PlanCompiler 在进程启动时从 Profile YAML 编译出来，运行期间被解释器照图执行；它只编排流程骨架，不编排具体实现，也不注入观察或副作用机制。**

理解 LCA 执行路径的核心是把三件事分开：

| 关注点 | 在 `CompiledRunPlan` 里吗？ | 真正管它的机制 |
|---|---|---|
| 阶段节点（perceive / think / act / reflect / remember / stop 的循环） | 是 | 拓扑 + 边 + 策略由 Profile 声明，编译器验证 |
| 节点内部"做什么"的逻辑 | 否 | 节点是个 `PhaseExecutor`，向 Cordis Context 查 `Body`、`PerceiveHub`、`Brain` 等能力 |
| Hook | 否 | `HookEvent` 枚举 + cordis events，独立于计划触发 |
| 沙箱 | 否 | `SandboxService` 是个 L0 Seam 插件，由 `SafeExecutor` 在执行工具调用时使用 |

---

## 1. 计划从哪来：源头是 YAML，不是 Python

关键设计（ADR-0075）：**图的形状完全由配置声明，编译器只做验证和投影，绝不注入任何默认值。**

`bundles/declarative-phase-graph.yaml` 是真实例子。节点部分（节录）：

```yaml
- id: phase.topology.standard
  config:
    nodes:
      - id: perceive.main
        phase: perceive
        binding: phase.perceive.standard
        max_visits: 8
        entry: true          # 唯一入口
      - id: think.main
        phase: think
        binding: phase.think.standard
        max_visits: 8
      - id: act.main
        phase: act
        binding: phase.act.standard
        max_visits: 8
      - id: reflect.main
        phase: reflect
        binding: phase.reflect.standard
        max_visits: 8
      - id: remember.main
        phase: remember
        binding: phase.remember.standard
        max_visits: 8
      - id: stop.main
        phase: stop
        binding: phase.stop.standard
        terminal: true
```

边部分（节录）——每个阶段都有"先错误边、再正常边"的固定顺序，编译器按声明顺序匹配：

```yaml
- id: phase.edge.standard
  config:
    approval_resume_node: think.main
    edges:
      - source: perceive.main
        target: stop.main
        when: result.result_kind == "phase_error"
      - source: perceive.main
        target: think.main
        when: true
```

执行策略（节录）——`think` 允许重试，`act` 因为有副作用不允许盲目重放：

```yaml
- id: phase.execution_policy.resilient
  config:
    policies:
      think:
        max_attempts: 2
        timeout_seconds: 90
        retry_on: [timeout, transient]
        on_exhausted: route_to_stop
      act:
        max_attempts: 1
        timeout_seconds: 90
        on_exhausted: route_to_stop
```

源码里这条铁律写得很直白（`lca/harness/declarative/graph/phase_graph_compiler.py:63-71`）：

> A profile that selects phase executors without a topology provider receives an empty graph projection rather than compiler-injected `*.main` nodes.

也就是说，不给节点，编译器就给你一张空图，外层直接拒绝启动——**没有隐藏的兜底工作流**。

---

## 2. 怎么编译：一条 10 步流水线

编译入口 `compile_plan()`（`lca/harness/profile/plan_compiler.py:81-156`）。文件末尾挂了一条 `DeprecationWarning`，指向 `lca_kernel.plan_compiler`（ADR-0115）；但 `lca_kernel/plan.py` 目前只是薄转发，**真正的编译逻辑只有 `plan_compiler.py` 这一处**。修改编译行为改点在 harness 那个文件。

### 2.1 外围

| 步骤 | 做什么 | 位置 |
|---|---|---|
| 运行时闭包校验 | 生产 Profile 必须提供完整运行时，否则拒编译 | `plan_compiler.py:102` |
| CapabilityPlan | 投影"谁提供什么能力" | `plan_compiler.py:104` |
| ScopePlan | 生命周期、可见性、ACL、预算天花板 | `plan_compiler.py:165-175` |
| 来源指纹 | profile / bundle / patch / task / env 五类溯源 | `lca/harness/plan.py:101-118` |

### 2.2 主体（10 步）

`compile_declarative_projection()`（`lca/harness/declarative/compile/compiler.py:74-114`）：

```python
specs           = profile.require_native_plugin_specs()   # 1 只收原生 PluginSpec
spec_report     = PluginSpecValidator().validate(specs)   # 2 PS-001..006 检查
active_specs, replacements = _resolve_replacements(specs) # 3 处理 REPLACES 关系
bindings        = _compile_capability_bindings(...)       # 4 每个能力选唯一提供者
graph, phase_bindings = _compile_phase_projection(...)    # 5 节点+边+策略 → 图
controls        = _compile_control_projection(...)        # 6 治理/观测投影为 ControlEntry
effect_policy   = _compile_effect_projection(...)         # 7 副作用白名单+审批要求
action_authority= _compile_action_authority_projection(..)# 8 允许/禁止的动作集
provenance      = _build_provenance(...)                  # 9 溯源
report          = _build_validation_report(...)           # 10 汇总三份校验
```

几个值得单独说的点：

**第 3 步 · 插件替换。** 插件可以声明 `REPLACES` 关系；若 `mode == "exclusive"`，被替换的插件从 active 集合剔除，同时留一条 `ReplacementDecision` 记录"谁替了谁、为什么"（`compiler.py:182-206`）。

**第 4 步 · 确定性选主。** 同一能力有多个提供者时，用字典序而非 import 顺序决胜（`compiler.py:218-230`）：

```python
chosen_spec, chosen = sorted(candidates, key=lambda pair: (pair[0].id, pair[0].revision))[0]
```

这行是整个计划可复现的关键之一——换机器、换 import 顺序，结果照样一致。

**第 6 步 · 控制面唯一事实源。** 只有 `role is GOVERN` 或 `output` 以 `observe.` 开头的贡献才变成 `ControlEntry`。治理类默认聚合是 `deny-on-any-deny`（一票否决），观测类是 `all-allow`（`compiler.py:243-272`）。所有横切控制都必须是计划里显式可见的条目，不允许隐式 hook 路径。

**第 7 步 · 副作用治理。** 默认规则（`effect_policy.py`）：`network`/`filesystem`/`world` 三类需要审批；除 `none` 外都要求幂等。

---

## 3. 编译时校验：三层门禁

错误早发现是"编译"而非"读配置"的真正分野。

| 层 | 代码前缀 | 典型拦截项 |
|---|---|---|
| PluginSpec | PS-001..006 | id 重复、必需能力无人提供、cardinality 冲突、关系目标不存在、grant 超出父作用域 |
| PhaseGraph | PG-001..010 | 入口不唯一、边指向未知节点、**有副作用的 act 前面没有 think**、reflect 后到不了 remember、**存在环但回边没有 loop guard**、终止节点不可达 |
| 控制闭包 | PG-010 | 声明了治理贡献却没有对应绑定；`(phase, executor)` 没有恰好一条 ControlEntry |

PG-002 / PG-004 / PG-006 是**因果性校验**：这不是语法检查，而是在强制认知闭集的语义——"不能没想就做"、"不能做完不反思就结束"。PG-007 的环检测用强连通分量算法找回边，任何回边没有 `LoopGuard`（最大迭代数 + 预算 + 终止谓词）一律拒绝。

最后一道闸（`plan_compiler.py:178-186`）：可运行的计划必须为 `SemanticPhase` 枚举里的**每一个**阶段都提供绑定，缺一个抛 `PlanCompilerError`。

---

## 4. 编译产物长什么样

`CompiledRunPlan`（`lca/contracts/protocols/state/plan.py:38`）是 `frozen=True, slots=True` 的不可变数据类，所有集合字段都是 tuple：

```python
profile_path, capability, scope           # ADR-0068 三件套
plugin_specs, capability_bindings         # 谁参与、谁提供什么
phase_graph                               # 节点 + 边 + approval_resume_node
phase_bindings                            # 节点 → 执行器 + 贡献列表
control_entries                           # 唯一的控制面投影
replacement_map, effect_policy, action_authority
provenance, validation_report
```

**它没有方法。** 散列、序列化、诊断投影全在 `lca/harness/plan.py`——数据形状和行为策略被刻意分开。

### plan_ref：计划的身份证

```python
def compiled_run_plan_ref(plan) -> str:
    payload = {
        "capability": capability_sub_plan_hash(plan),
        "control": control_entries_sub_plan_hash(plan),
        "scope": scope_sub_plan_hash(plan),
        "profile_path": ..., "plan_version": ..., "revision": ...,
        "input_provenance": sorted(...),
        "declarative": _declarative_payload(plan),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]
```

确定性靠四件事叠加：

1. `json.dumps(sort_keys=True, separators=(",", ":"))`
2. `_canonicalize` 把枚举转 value、dataclass 转 dict、Mapping 按 key 排序、set 按 canonical 形式排序
3. `provenance.plugin_revisions` 与 `actor_grant` 在编译时就已排序
4. 能力选主用字典序

注意 `plan_hash` 与 `plan_ref` 在 `compiled_run_plan_to_dict`（`plan.py:88-89`）里是**同一个值**，只是两个键名。

---

## 5. 谁产生它：启动时编译一次

```
python -m lca_kernel serve --profile profiles/web-standard.yaml
  └─ run_kernel_lifespan()                       lca_kernel/cli.py:166
      └─ boot_resolved_profile()                 lca/harness/profile/boot.py:67-82
          ├─ resolve_profile()   ← 读 YAML、校验、拓扑排序插件
          ├─ compile_profile_boot_products()     boot_products.py:40-55
          │    compile_plan(resolved, options=CompileOptions(
          │       require_executable_phase_graph=not profile_allows_test_defaults(resolved)))
          └─ attach_profile_boot_products(ctx, products)   boot.py:156
```

`compile_profile_boot_products` 里那个条件很关键：**生产 Profile 强制要求可执行图，只有显式标记的测试 Profile 才放宽。**

编译结果被原子地钉在 Context 上，且拒绝二次改写（`boot_products.py:63-67`）：

```python
if existing is not None:
    if existing != products:
        raise RuntimeError("Profile boot products are already attached to this scope")
    return existing
```

之后所有读取都走同一个封口接缝 `compiled_plan_from_scope(scope)`，缺失时抛 `MissingCapabilityError` 失败关闭。**每个 HTTP 请求不会重新编译**——Agent 在装配时已经绑定了计划，请求路径上只用 `plan_ref`。

---

## 6. 谁消费它：解释器照图执行

```
POST /runs
  └─ CognitiveRuntime.run(task)                  runtime_loop.py:138
      └─ bindings.require_executable_plan()      runtime_bindings.py:194
      └─ DeclarativeExecution.execute(state)     declarative_runtime.py:14
          ├─ GraphAssembler().assemble(plan, scope)   ← 计划 → 可执行节点
          └─ interpreter.run(executable, ...)         interpreter.py:104
              └─ _drive(): 循环 { 执行节点 → 选下一条边 }
```

**`require_executable_plan()` 是绑定期的最后一道校验**：计划声明的每个 `executor_capability` 都必须在实际注册的 `phase_executors` 里，缺一个就报错。

`GraphAssembler` 把静态计划变成可执行视图：遍历 `phase_bindings`，用 `scope.resolve()` 把能力键换成真正的执行器对象。**计划本身不持有任何可调用对象**，这正是它能被 hash、被序列化、被跨进程比较的原因。

### 走边的逻辑（interpreter.py:379-408）

```python
for edge in (edge for edge in edges if edge.source == source):
    if not evaluate_restricted_predicate(edge.when, result=result, artifacts=artifacts):
        continue
    if edge.loop is not None:
        verdict = self._loop_guard_evaluator.evaluate(...)
        if not verdict.allow:
            continue          # 守卫拒绝就跳过，继续看下一条边
    return edge
```

两个细节：

- **先声明先匹配**，所以 YAML 里错误边写在正常边前面才生效。
- loop guard 拒绝时是 `continue` 而非 `return None`——拓扑可以在受守卫的重入边后再写一条正常收敛边，解释器不需要知道任何阶段特定策略。

谓词是受限 AST 求值（`graph/predicate.py`），只允许 `result` / `artifact` / `observation` / `budget` 四个根，禁止下划线属性和函数调用。**不是 eval**。

### 恢复：plan_ref 是防串号的锁

```python
expected_plan_ref = compiled_run_plan_ref(plan)
if getattr(cursor, "plan_ref", None) != expected_plan_ref:
    raise DeclarativeValidationError("PG-008", ...)
```

`interpreter.resume()`（`interpreter.py:140-147`）在继续遍历前先比对游标的 `plan_ref`。含义很实际：**如果你改了 YAML 重启了服务，旧的 checkpoint 会被明确拒绝，而不是拿新图跑旧状态跑出诡异结果。** 同样的 `plan_ref` 还会盖在 `CommandEnvelope` 和 `RunFact` 上，成为跨进程的幂等与审批交接凭据。

---

## 7. 阶段节点本身是怎么"被编进去"的

节点身份本身是配置出来的。但更值得注意的是：**"节点行为"和"节点身份"是两件事**。

以 `phase.act.standard` 为例（`lca/plugins/phase_graph/act.py`）：

```python
async def execute(self, context, input):
    body = StandardPhaseCapabilities(context.capabilities).body
    decision = context.artifacts.get("think")
    envelope = mint_envelope(plan_ref=..., provider="effect.body",
                             grant=CapabilityGrant(capability="body.act", ...))
    return PhaseResult(result_kind="observation", command_envelope=envelope)
```

这段代码**完全是固定的**，没有任何 Profile 控制它的入口。它只做四件事：

1. 从 `context.capabilities` 取 `Body` 实现
2. 从上游 `think` 节点产的 artifact 拿 `Decision`
3. 用 `plan_ref` + `node_ref` 铸一个 `CommandEnvelope`
4. 把 envelope 交给 Effect Gateway

`perceive` 节点同理（`perceive.py:48-52`）：`hub = StandardPhaseCapabilities(context.capabilities).perceive_hub; await hub.perceive(state)`。它只调一个 `PerceiveHub.perceive`，具体怎么感知由注入的 `PerceiveHub` 决定。

**所以编译对象是"谁在什么阶段、用什么执行器"，而不是"执行器里写什么代码"。** 每个 `PhaseExecutor` 都是同一个模板：从 `context.capabilities` 拿出当前 Profile 选择的实现，转手就调，自己几乎不写逻辑。

协议层有强制（`compiler.py:139-174` 的 `_compile_phase_bindings`）：每个 phase binding 的 `executor_capability` 必须有对应 `kind == PHASE_EXECUTOR` 的插件提供，否则 `PG-001`。换言之，**计划决定了哪个能力键绑到哪个节点，但能力键背后的对象本身不在计划里**。

---

## 8. Hook 是怎么注入的（以及为什么它不归计划管）

钩子系统完全在另一个维度运行。

看 `lca/cognition/hook_registry.py:88-127` 的核心实现：

```python
class CordisHookRegistry(HookRegistry):
    def register(self, event_name, hook):
        self._ctx.events.on(_hook_event_name(event_name), hook)

    async def trigger(self, event_name, state, **kwargs):
        envelope = {"event_name": event_name, "state": state, **kwargs}
        with detached_span(_span_name_for_hook(event_name), **attrs):
            return await self._ctx.events.serial(
                _hook_event_name(event_name), envelope
            )
```

钩子挂在 cordis 的 `events.serial` 命名空间里，跟 `CompiledRunPlan` 完全是两个 dispatch 平面。计划运行时在三个固定点 trigger（`runtime_loop.py:170`、`result_finalizer.py:50`），但**谁来注册、注册什么、跑多少个监听器**都不在计划里。

注册入口在 `lca/plugins/runtime/hook_registry.py:33-41`：

```python
def build_simple_hook_registry(ctx):
    hooks = CordisHookRegistry(ctx)
    journal_hook = make_journal_emitting_hook(_journal_record)
    for event_name in HookEvent:
        hooks.register(event_name, journal_hook)
    return hooks
```

这是 L1 插件 `hook_registry.simple`，声明 `provides=[]`（**它不向 Profile 声明任何能力**），只通过工厂函数挂上 cordis。Hook 注册是平台启动时的全局装置，跟阶段图解耦。

`HookEvent` 是闭集枚举（`lca/contracts/atoms/enums.py`），不被计划扩展，也不被插件扩展。Hook 是观察者，永远不能返回改写后的 State——v3 认知原语宪法的硬约束。

### control_entries 跟 hook 不是一回事

**控制条目是计划里的治理和观测贡献的唯一事实源**（`compiler.py:243-272`），由解释器在 phase 执行时显式调用，效果是产生 `ControlVerdict`，可能阻断下一步。它们是**流程内的控制点**，而 hook 是流程外的旁路事件。

宪法里有一段更直接的判断（`docs/design/2026-08-19-cognitive-primitive-constitution-v3.md:974`）：

> `HookEvent.PRE_*` / `POST_*` 与 `COGNITIVE_PHASES` 的 `agent.before_*` / `after_*` 是**控制口伪装成观察口**。冻结（PR1）→ 忽略返回值（PR5）→ 拆除（PR10）。

也就是说项目**正在主动清理**把 hook 当控制点的用法，向计划内的 `control_entries` 收敛。当前是过渡态。

---

## 9. 沙箱是怎么注入的（以及为什么它根本不在计划里）

沙箱的整个存在方式跟阶段图正交，它是一条平行的 capability 链路。

### 9.1 沙箱自身是 L0 Seam

`lca/plugins/seams/act/sandbox.py:25-57`：

```python
@plugin(
    id="lca-sandbox-service",
    provides=["sandbox"],
    implements=[Sandbox],
    layer="L0",
    effects="world",
    ...
)
async def setup(ctx, config):
    from lca.infrastructure.capability.sandbox import SandboxService
    ctx.provide("sandbox", SandboxService())
```

它的层号是 **L0（基础设施）**，effect 标注 `world`，可见性低、风险高。它**完全不参与 phase graph**——计划里没有任何字段指向 `Sandbox`。

### 9.2 沙箱被 SafeExecutor 使用

`lca/cognition/body/safe_executor.py:100-101` 的类注释把流水线写得明明白白：

> Permission → validate → ToolStarted → cache → retry → **sandbox execute** → ToolInvoked

`SafeExecutor` 是 Body 平面管副作用的组件，对应 Protocol `lca/contracts/protocols/runtime/infra.py` 里的 `SafeExecutor`。它的工厂插件是 `lca/plugins/body/safe_executor.py:28-50`：

```python
@plugin(
    id="safe_executor.simple",
    provides=[SAFE_EXECUTOR_SIMPLE.key],
    implements=[SafeExecutor],
    layer="L1",
    effects="tools",
    control_slots=(ControlSlot.ACT_SAFE_BOUNDARY,),
)
async def setup(ctx, config):
    from lca.cognition.body.safe_executor import SimpleSafeExecutor
    ctx.provide(SAFE_EXECUTOR_SIMPLE.key, SimpleSafeExecutor)
```

注意 `control_slots=(ControlSlot.ACT_SAFE_BOUNDARY,)`——它声明自己占据手平面里"ACT 安全边界"这个控制槽。Body 里别的组件知道：执行 act 动作必须经过这里。

### 9.3 调用链：act 阶段 → Effect Gateway → SafeExecutor → Sandbox

```
act.main 节点
  → StandardActExecutor.execute()             # 在 act.py → mint_envelope(provider="effect.body")
  → Dispatcher (execute/dispatch.py:33-83)
      → 校验 effect_policy.allowed_effects / approval_required / idempotency_required
      → SafeExecutor.act()                     # safe_executor.py
          → permission → validate → sandbox.execute → ToolInvoked 事件
      → SandboxService.execute()                # infrastructure/capability/sandbox.py
      → 真实外部副作用
```

**计划里出现的是哪一段？** 只有最顶上两环：节点身份（`act.main`）+ Effect Gateway 的策略（`effect_policy` 字段：哪些 effect 允许、哪些需审批、哪些需幂等）。`act` 节点的 effect 声明是 `"tools"`（`act.py:40`），被 `_compile_effect_projection` 收进 `allowed_effects` 列表（`effect_policy.py:25-39`）：`tools` 不在 `network` / `filesystem` / `world` 之列 → 不要审批；要幂等。`phase_graph.effect_policy` 里能看到工具调用需不需要幂等键，但看不到 `SandboxService` 是怎么实现的。

### 9.4 沙箱被两个东西隔在计划之外

- **分层规则。** `lca/infrastructure/*` 是底层，`lca/harness/declarative` 是中高层。`pyproject.toml` 的 importlinter 契约 `transport-isolation` / `kernel-domain-isolation` 防止上层反向 import 底层实现。计划属上层，沙箱实现属下层。
- **不可哈希性。** `CompiledRunPlan` 必须能被 SHA-256 摘要。沙箱实例带网络句柄、文件系统描述符的可变对象，根本塞不进 `frozen=True, slots=True` 的 dataclass。

---

## 10. 边界速查

把整张图在脑子里摊平后，三类不同归属就清楚了：

**计划管（静态、可哈希、可序列化）：**

- 哪些 phase 节点存在、各是什么 semantic phase
- 谁绑哪个节点（`executor_capability` 名字，不是实例）
- 节点之间的边 + 谓词（`when` DSL）+ loop guard
- 每个阶段的执行策略（`max_attempts` / `timeout_seconds` / `retry_on` / `on_exhausted`）
- 哪些 effect 允许、哪些需审批、哪些需幂等（`effect_policy`）
- 哪些动作允许/禁止（`action_authority`）
- 治理贡献如何聚合（`control_entries` 的 `aggregation`）
- 治理裁决（`plan_ref` 是审批包凭据）

**计划不管（动态、可执行、有副作用）：**

- Body 怎么执行工具（`safe_executor.simple` 插件里的实现）
- 沙箱怎么隔离执行（`lca-sandbox-service` 插件里的实现）
- 感知具体怎么做（`PerceiveHub` 实现）
- LLM 怎么调（`llm.*` seam）
- 记忆怎么存（`memory.*` seam）
- 工具注册表（`ToolRegistry`）

**计划不管但会调用（接缝点）：**

- 每个 PhaseExecutor 通过 `StandardPhaseCapabilities`（`lca/plugins/phase_graph/capabilities.py:18-46`）从 `context.capabilities` 字典里按名字取 `Brain` / `Body` / `PerceiveHub` / `MemorySystem` 等
- Effect Gateway 用 `effect_policy` 字段做白名单校验
- Hook 在固定 runtime 节点（`runtime_loop.py:170`、`result_finalizer.py:50`）触发，但跟计划解耦

---

## 11. 一个补充原则：控制槽

`plugin-contract.py` 里 `control_slots` 是这套架构里很有信息量的设计：每个插件可以声明它占据哪些控制槽（`ACT_SAFE_BOUNDARY`、`OBSERVE_WILDCARD` 等）。**只有声明了控制槽的插件才有资格在那个控制点做事。**

- `safe_executor.simple` 占 `ACT_SAFE_BOUNDARY`
- `hook_registry.simple` 占 `OBSERVE_WILDCARD`

这就是治理边界的物理位置，而不是某个被 if-else 链忘记挂上的回调。

跟 `control_entries` 是互补的两条路：

- 计划里的 control 是**流程内**的精确治理（哪一步、谁有票、用什么聚合）
- 控制槽是**架构级**的全局分工（谁有资格在那个点做事）
- 两者都不靠全局 hook 链

---

## 12. 改动影响表

| 想改的东西 | 在哪改 |
|---|---|
| 改流程（节点、边、策略） | YAML / Bundle 配置 |
| 改某阶段的执行内容 | 改对应 `PhaseExecutor` 插件源码 |
| 改 Body 工具执行语义 | 改 `safe_executor.*` 插件 + 下游 Sandbox 实现 |
| 改 Hook 语义 | 改 `hook_registry.*` 插件和 `HookEvent` 枚举（后者是闭集，新增需要 ADR） |
| 改编译规则 | 改 `plan_compiler.py` 与 `declarative/compile/*.py`（注意：harness 版本是真源，kernel 是门面） |
| 改运行时执行语义 | 改 `interpreter.py` / `dispatch.py` / `phase_transaction.py` 等 |

---

## 13. 关键文件清单（速查）

| 文件 | 职责 |
|---|---|
| `lca/contracts/protocols/state/plan.py:38` | `CompiledRunPlan` 不可变数据类 |
| `lca/harness/profile/plan_compiler.py:81-156` | 外层编译入口（harness 唯一真源） |
| `lca/harness/profile/boot_products.py:40-77` | 启动产物对 + 钉到 Context |
| `lca/harness/declarative/compile/compiler.py:74-114` | 10 步声明式投影 |
| `lca/harness/declarative/graph/phase_graph_compiler.py:54-308` | 节点/边/策略投影 |
| `lca/harness/declarative/controls/validation.py` | PS/PG 校验规则 |
| `lca/harness/plan.py:42-55` | `compiled_run_plan_ref` |
| `lca/runtime/runtime_bindings.py:194-202` | 运行时绑定校验（必须可执行） |
| `lca/runtime/declarative_runtime.py:14-66` | 驱动入口 |
| `lca/harness/declarative/compile/assembler.py:68-122` | 计划 → 可执行节点 |
| `lca/harness/declarative/execute/interpreter.py:104-410` | 解释器主循环 + 走边 |
| `lca/harness/declarative/execute/dispatch.py:33-103` | Effect Gateway / Reducer |
| `lca/plugins/phase_graph/act.py:48-72` | 标准 act 节点（典型 20 行调度壳） |
| `lca/plugins/runtime/hook_registry.py:33-41` | Hook 注册工厂 |
| `lca/plugins/seams/act/sandbox.py:25-57` | 沙箱 Seam 插件 |
| `lca/plugins/body/safe_executor.py:28-50` | SafeExecutor 工厂插件 |

---

## 14. 同义术语表（仓促阅读时翻）

- **MTK**（minimal Trusted Core / 最小可信内核）—— 编译器 + 校验器 + 解释器 + Reducer + Effect Gateway 这套稳定机制。
- **phase** —— 7 个语义阶段之一（perceive / think / act / reflect / remember / stop + 可选 observe 类横切）。
- **node** —— phase graph 里一个具体节点（带 id 与 binding）。
- **edge** —— 节点之间的转移，含谓词和可选 loop guard。
- **phase binding** —— 节点到 `PhaseExecutor` 能力键的映射。
- **control entry** —— 计划里治理/观测贡献的唯一事实源。
- **plan_ref** —— `CompiledRunPlan` 的 SHA-256 短摘要，跨进程身份证。
- **control slot** —— 插件级声明，标明它占据哪个治理位置（架构级）。
- **seam / provider / adapter / registry / plugin / profile / bundle** —— 见 [lca-structured-cognition-guide.md](lca-structured-cognition-guide.md)。