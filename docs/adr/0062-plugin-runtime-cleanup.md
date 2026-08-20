# ADR-0062: 插件运行时收口 — 单一事实源 + Cordis Fiber Boot + L4 严格闭合

## 状态

Proposed

Amends: [ADR-0056](0056-plugin-group-contribution.md)、[ADR-0061](0061-plugin-manifest-resolve-boot.md)、[ADR-0004](0004-protocol-first-pluggability.md)、[ADR-0005](0005-composition-root-l4.md)

## 背景

ADR-0061 已确立：Manifest `requires`/`provides` 是当前唯一强制的依赖事实源；`Capability[T]` 是 contracts 命名原语；`PluginContext` 只暴露四个动作；boot 失败须逆序 dispose。

但仓库现状仍有四套并行的"事实源"，每套都自称"运行时真相"：

| 现象 | 证据 |
|---|---|
| **Manifest 双字段** | 59 个装饰插件中 53 个仍用 legacy `name` / `inject` / `side_effects` / `policy_class`；只有 6 个用 canonical `id` / `kind` / `effects`（静态 AST 审计）。`lca/plugins/_cordis_adapter.py` 是迁移期 shim，仅承担字段重命名。 |
| **Capability 双解析路径** | `lca/contracts/mechanisms/capability.py:91` 的 `require_capability` 在 plain key 失败后回退到 `seam:<key>` / `SeamRegistry` 路径；`lca/plugins/seam_definitions/` 13 个 alias bundle plugin 在 boot 时写 13 个 `SeamRegistry` 到 ctx。 |
| **Boot 双实现** | `lca/harness/profile/boot.py` 有 `started: list[...]`、`_call_setup()`、`_dispose_started()` 三件套；vendored cordis 已有 `ctx.registry.plugin()` + `Fiber.await_()`，但 LCA 没走它。失败时手工 dispose 路径吞掉清理异常（`lca/harness/profile/boot.py:220-240`）。 |
| **L4 双路径** | `lca/layer4_app/spawn.py` 同时有 plugin tree path 与 `register_builtin_sensors()` / `build_default_registries()` / `_is_plugin_tree()` / `_resolve_named_factory(scope, key, ConcreteClass)` / `register_defaults()` 等 fallback。`lca/layer4_app/defaults.py` 把协作策略工厂（lead / pipeline / debate 等）以静态 `Registries` 形式固定在 L4。 |
| **运行时反向 import** | `lca/plugins/loop_cognitive.py:93` `from gateway.runs.loop_drivers import CognitiveRunDriver` —— LCA 插件反向依赖 Gateway。同一文件 `provides=["agent_loop", "run_loop_driver_registry[cognitive]"]` 担任两个职责（PRD-5 关注点）。 |

每多一个并行事实源就多一条"读哪边才对"的歧义。`vulture` 80% 阈值扫到 `spawn.py` 内多个 dead branch；`import-linter` 没卡住 L1→gateway 是因为 L1 的 `loop_cognitive` 是从 `lca.plugins.loop_cognitive` 命名的，不在 lint 范围内。

这不是新设计缺失，是 ADR-0061 已设计但尚未收口。

## 第一性原理

| # | 不变量 | 含义 |
|---|---|---|
| **B1** | **Manifest 是装饰器编译产物** | `@plugin(id=..., provides=..., requires=..., kind=..., effects=..., test_suite=...)` 在 import 期冻结为不可变 `PluginDefinition`；YAML 不写依赖 |
| **B2** | **注解推导并校验 requires** | 函数形参类型 → `Capability[T]` 集 ⊆ Manifest `requires`；签名漂移 → Resolve 失败 |
| **B3** | **`Capability[T]` 是唯一交互键** | 删除 `seam:<key>` / `SeamRegistry` 解析路径；多实现经 registry seam（`BRAINS`/`BODIES`/`DRIVERS`...） |
| **B4** | **Cordis Fiber 负责生命周期** | 删除手工 `_call_setup` / `started[]` / `_dispose_started`；失败由根 Fiber 逆序 dispose，清理异常以 `ExceptionGroup` 聚合 |
| **B5** | **`spawn_*` 仅消费 booted capability** | 删除 `build_default_registries()` / `register_builtin_sensors()` / `_is_plugin_tree()` / `_resolve_named_factory()` 的 concrete fallback；测试用 `profiles/test-minimal.yaml` 替代 |
| **B6** | **driver plugin 不反向 import gateway** | `CognitiveRunDriver` 等移至 `lca/plugins/drivers/`；Gateway 只从 `RUN_DRIVERS` capability 消费 |
| **B7** | **删兼容层不留双轨** | `_cordis_adapter.py` / `seam_definitions/` / `SeamRegistry` 一次性删除；不再有"过渡期兼容旁路" |

## 决定

### 1. Manifest canonical fields 是唯一字段

`lca/harness/plugin_api.py:plugin()` 签名收紧为：`id` / `provides` / `requires` / `kind` / `effects` / `test_suite` / `layer` / `Config`。`name` / `inject` / `side_effects` / `policy_class` 一律删除（不再有 legacy kwarg）。

```
@plugin(
    id="sensor.clock",          # 唯一字段
    requires=(PERCEIVE,),          # 注解推导 + 显式声明同时存在时以注解为准
    kind=PluginKind.PRIMITIVE,
    layer="L1",
    effects=(EffectClass.NONE,),
    test_suite="tests/plugins/test_sensor_clock.py",
)
def setup(ctx: PluginContext, config: ClockConfig, perceive: PerceiveService) -> None:
    perceive.add(build_clock_sensor, id="clock", order=10)
```

### 2. `PluginDefinition` 是不可变 dataclass

```python
@dataclass(frozen=True, slots=True)
class PluginDefinition:
    id: str
    module: str
    provides: tuple[Capability[Any], ...]
    requires: tuple[Capability[Any], ...]
    kind: PluginKind
    layer: str
    effects: tuple[EffectClass, ...]
    test_suite: str
    config_model: type[BaseModel] | None
    setup: Callable[..., Any]   # 由装饰器捕获
```

`@plugin` 在 import 期冻结为 `PluginDefinition`；Resolve 用它构建 DAG，不读 `meta`、不读 legacy 字段。

### 3. `Capability[T]` 是唯一交互键

- 删除 `lca/contracts/mechanisms/seam_registry.py`（SeamRegistry）
- 删除 `lca/plugins/seam_definitions/`（13 个 bundle entry + `__init__.py`）
- 删除 `lca/contracts/mechanisms/capability.py` 中 `Path 2: seam-namespaced registry` 解析路径
- 删除 `bundles/base.yaml:64-65` 的 `lca_seam_definitions` 入口

多实现轴改用单一 registry seam：

```python
BODIES = Capability["BodyFactory"]("bodies")        # 注册：simple / tools-only / ...
BRAINS = Capability["BrainFactory"]("brains")
DRIVERS = Capability["RunDriver"]("run_drivers")
STOP_RULES = Capability["StopRule"]("stop_rules")
HOOKS = Capability["Hook"]("hooks")
STRATEGIES = Capability["TeamStrategy"]("team_strategies")
```

Provider 用 `registry.register(BODIES, "simple", factory)` 注册；`spawn_*` 经 `BRAINS.create(spec.brain)` / `BODIES.create(spec.body)` 取出。

### 4. Boot 走 Cordis Fiber

- `lca/harness/profile/resolve.py` 是**纯编译器**：展开 bundle、深合并 patch、import `$module`、校验 Manifest/Config/DAG、解析 `{from_env}`、冻结 `ResolvedProfile`。不做业务对象、不执行 setup、不请求网络。
- `lca/harness/profile/boot.py` 重写为：
  ```python
  async def boot_resolved_profile(resolved: ResolvedProfile) -> Context:
      ctx = cordis.Context()
      for entry in resolved.entries:
          fiber = ctx.registry.plugin(entry.definition.setup, config=entry.config)
      try:
          await asyncio.gather(*[fiber.await_() for fiber in fibers])
      except BaseException:
          await ctx.dispose()  # cordis 内部按依赖逆序释放
          raise
      return ctx
  ```
- 删除 `_call_setup` / `started` / `_dispose_started` / `boot_entries` 双路径。
- 失败时 `ExceptionGroup` 聚合"启动异常 + 清理异常"；不静默吞掉。

### 5. `spawn_*` 只接受 booted scope

`lca/layer4_app/spawn.py` 收敛为：

```python
async def spawn_agent(spec: AgentSpec, *, scope: Context) -> CognitiveAgent:
    perceive = scope.require(PERCEIVE).assemble(scope, spec)
    memory = scope.require(MEMORY).create(spec.memory)
    body = scope.require(BODIES).create(spec.body, scope=scope)
    brain = scope.require(BRAINS).create(spec.brain, perceive=perceive, body=body, scope=scope)
    stop = scope.require(STOP_RULES).create(spec.stop)
    hooks = scope.require(HOOKS).assemble(scope)
    return build_cognitive_runtime(spec, perceive, memory, body, brain, stop, hooks, scope)
```

- 不 import `SimpleBody` / `PerceiveService` / `TransportService` / `DefaultStopRule` 等 concrete class
- 不调 `build_default_registries()` / `register_builtin_sensors()` / `register_defaults()`
- 不接受 `registries: Registries | None` 入参
- 没有 booted scope 时**显式 boot 一个 minimal profile**，不调用"全局默认 ctx 缓存"

测试用 `profiles/test-minimal.yaml`（仅含 team assembly 所需的 L0/L1 子集），取代 `build_default_registries()`。

### 6. Driver plugin 边界

`lca/plugins/loop_cognitive.py` 拆为：

- `lca/plugins/drivers/cognitive.py` —— 注册 `DRIVERS["cognitive"] = CognitiveRunDriver`
- `lca/plugins/registry/run_loop_driver_registry.py` —— 提供 `RUN_DRIVERS` capability 与 registry

`CognitiveRunDriver` 实现位于 `lca/layer2_runtime/drivers/cognitive_run_driver.py`（不引 gateway）。Gateway 仅消费 `RUN_DRIVERS["cognitive"]`，不反向被 LCA 插件 import。

删除 `provides=["agent_loop", "run_loop_driver_registry[cognitive]"]` 双职责。

### 7. L4 协作策略工厂迁为 plugin

`lca/layer4_app/defaults.py` 整体删除。`_lead_strategy` / `_pipeline_strategy` / `_fan_out_strategy` / `_peer_relay_strategy` / `_peer_swarm_strategy` / `_debate_strategy` / `_graph_strategy` / `_register_defaults` 改为：

- `lca/plugins/strategies/lead.py` —— `register(STRATEGIES, STRATEGY_KEY_LEAD, _lead_strategy)`
- `lca/plugins/strategies/pipeline.py`
- `lca/plugins/strategies/fan_out.py`
- `lca/plugins/strategies/peer_relay.py`
- `lca/plugins/strategies/peer_swarm.py`
- `lca/plugins/strategies/debate.py`
- `lca/plugins/strategies/graph.py`
- `lca/plugins/registries/component_registry.py` —— STATE_STORE / MEMORY / EVENT_BUS / BUDGET_POLICY 等

`registries.components` / `registries.brain_factories` / `registries.orchestration` 三个静态 `Registries` 整体淘汰；改为 `scope.require(COMPONENT_REGISTRY).create()` 路径。

### 8. 删除清单（强制同步）

| 删除项 | 删除前替代 | 删除条件 |
|---|---|---|
| `lca/plugins/_cordis_adapter.py` | `from lca.harness.plugin_api import plugin` | 全部 25 个插件 import 迁移完成 |
| `lca/plugins/seam_definitions/` | `BODIES`/`BRAINS`/... capability registry seam | `bundles/base.yaml` 入口移除 |
| `lca/contracts/mechanisms/seam_registry.py` | capability `register` / `create` | 无 import |
| `lca/contracts/mechanisms/capability.py` 的 `Path 2` | 单一路径 | 无运行时分支 |
| `lca/layer4_app/defaults.py` | strategy plugin + component registry plugin | 测试 fixture 改用 minimal profile |
| `lca/layer4_app/spawn.py` 的 `_is_plugin_tree` / `_resolve_named_factory` / `build_default_registries()` 调用 | 仅 booted scope | spawn 重写完 |
| `lca/plugins/loop_cognitive.py` 的 Gateway import + 双职责 | `lca/plugins/drivers/cognitive.py` | driver plugin 路径绿 |
| `lca/harness/profile/boot.py` 的 `_call_setup` / `started` / `_dispose_started` | cordis Fiber | boot 重写完 |
| `plugin_api.py` 的 legacy kwarg (`name` / `inject` / `side_effects` / `policy_class`) | 一次性删除 | 全部 53 个插件迁移完成 |

**禁止** 在 PR 中保留 legacy kwarg 作为"迁移期兼容"——一律删干净；任何残留 import 必须修复。

## PR 序列

每 PR 独立可回滚；每 PR 跑全量门禁。

| PR | 范围 | 关键验收 |
|---|---|---|
| **PR-1.a** ADR + 不可变 `PluginDefinition` | 本 ADR 接受；`plugin_api.py` 改为返回 `PluginDefinition`；不动 53 个 legacy 插件 | 新建插件可用 canonical 字段；`PluginDefinition` 是 dataclass(frozen=True) |
| **PR-1.b** 53 个插件 Manifest 迁移 | 53 个插件改用 `id` / `requires` 推导；删除 `_cordis_adapter.py` import；`plugin_api.py` 删 legacy kwarg | ruff / mypy / 全量 pytest；`test_plugin_alignment.py` 升级为 100% canonical |
| **PR-2** Boot 走 Cordis Fiber | `resolve.py` 拆分纯编译器；`boot.py` 重写走 `ctx.registry.plugin()`；删 `_call_setup` / `_dispose_started` | 缺能力、循环、Config 错误均在 Resolve 失败；setup 失败逆序 dispose；`ExceptionGroup` 聚合 |
| **PR-3** Seams & registries 收敛 | 引入 `BODIES` / `BRAINS` / `DRIVERS` / `STOP_RULES` / `HOOKS` / `STRATEGIES` registry seam；删 `seam_definitions` / `SeamRegistry` / `Path 2` 解析 | "每个 capability 恰一个 owner"；重复 registry entry 失败；Sensor/Gate 排序稳定 |
| **PR-4** L4 严格闭合 | `spawn.py` 收紧到只消费 booted capability；`defaults.py` 整体删除；strategy 工厂迁 plugin；测试改用 fixture 或 minimal profile | `spawn.py` AST 不引 concrete service；integration test 走 minimal profile |
| **PR-5** Driver 边界 | `loop_cognitive.py` 拆为 `drivers/cognitive.py`；`CognitiveRunDriver` 移至 `lca/layer2_runtime/`；Gateway 仅消费 `RUN_DRIVERS` capability | `lca/plugins` 不 import `gateway`；`/runs` 在 driver 启用时工作 |

## 关键验收矩阵

| 维度 | 必须证明 | 推荐测试 |
|---|---|---|
| Manifest 单一事实源 | 59/59 插件用 canonical 字段；无 legacy kwarg；YAML 无 `inject` | AST audit + `tests/test_plugin_alignment.py` |
| Capability 单一交互键 | `require_capability` 只有一条路径；`seam:` 字面量在仓库内 0 命中 | grep audit + integration test |
| Cordis Fiber 生命周期 | 失败插件的前驱被逆序释放；清理错误与启动错误同时可见 | `test_boot_failure_disposes_fibers_in_reverse_order` |
| Spawn 严格闭合 | `spawn.py` AST 不引 `SimpleBody` / `PerceiveService` / `build_default_registries` | AST import test |
| Driver 边界 | `lca/plugins` 不 import `gateway` | import-linter contract |
| 策略工厂 | 7 个 strategy factory 都是 plugin；测试用 minimal profile | integration test + boot report |

## 放弃的方案

- **保留 legacy kwarg 作为过渡期兼容** —— 评审点名的"`vulture` 只是兜底，人工判断优先"原则要求一次到位
- **拆 6 个 PR 为 1 个大 PR** —— 单 PR 触发 contracts 改动，回滚半径 = 全仓库
- **把 DSH 的 npm 包布局搬入 LCA** —— Python 模块路径已是插件物理定位，额外 manifest 文件只会扩大维护面
- **把六步循环插件化** —— 违反宪法 C1 / C6
- **回退群服务投稿 / 重引 Composer 点名** —— 违反 ADR-0056
- **保留 `SeamRegistry` 作为"语义版本"保留** —— ADR-0061 §3 已确立 Capability[T] 是唯一交互键；保留只会制造第二真相源

## 后果

- 一次 PR-1.b 之后 `manifest` 静态审计从 6/59 → 59/59，YAML 不再写依赖
- 删除 `_cordis_adapter.py` / `seam_definitions/` / `defaults.py` 后，仓库内 "兼容层" 计数 = 0
- Boot 失败路径在 `ExceptionGroup` 内可观测启动异常 + 清理异常，调试不再"控制流丢一半"
- `spawn.py` 由 694 行收敛到 ~150 行；fixtures 由 8 个 `build_default_registries()` 收敛到 1 个 minimal profile
- 跨边界 import (`lca/plugins → gateway`) 计数 = 0，`import-linter` 加一条 contract
- 协作策略工厂从 L4 静态注册表变为 plugin，`bundles/` 多 7 个 strategy entry（与 `lca/plugins/strategies/*.py` 一一对应）

## 相关

- [ADR-0056 群服务投稿](0056-plugin-group-contribution.md) —— Sensor/Gate/Brain 仍按群服务 `add()`
- [ADR-0061 Manifest 声明式](0061-plugin-manifest-resolve-boot.md) —— B1-B7 是其推迟落地的部分
- [ADR-0004 Protocol-First 可插拔](0004-protocol-first-pluggability.md) —— 不变量 P1（交互键 ⊆ Manifest 声明）
- [ADR-0005 L4 组合根](0005-composition-root-l4.md) —— `spawn_*` 仍是 L4 唯一对象图闭合入口
- [宪法 v3](../design/2026-08-19-cognitive-primitive-constitution-v3.md) C1/C4/C6/C7