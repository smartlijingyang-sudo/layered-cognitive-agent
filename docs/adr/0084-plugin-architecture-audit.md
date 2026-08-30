# LCA“一切皆插件”架构审查报告

## 结论

**你的判断基本正确：当前项目已经完成了“宏观能力插件化”，但还没有完成“所有可变化逻辑都以最小插件单元可组合、可替换”的强定义。** 更准确地说，仓库现在是三种状态并存：基础设施后端、Brain/Gate/Sensor/Strategy 等部分认知原语已经具备真实的 capability/registry 替换能力；声明式 phase graph 已经具备计划级组合能力；但运行时 effect/delta 接线、动作处理、控制贡献、Team 组装、网关 mode 和若干默认策略仍然通过组合器、聚合 provider 或固定 helper 绑定。

因此，“除了内核，其他全部都是插件”目前只能作为**目标架构宣言**，不能作为源码事实。源码事实更接近：**插件覆盖了能力目录和装配入口，但尚未覆盖所有行为最小单元的选择点**。

> 判断一个逻辑是否真正插件化，不能只看它是否位于 `lca/plugins/` 或是否有一个 `@plugin` 外壳，而要同时满足：有稳定 Protocol/capability、有独立 provider 或 contributor、有 profile/plan 选择入口、运行时确实消费该绑定，并且替换它时不需要修改相邻组合逻辑。

## 审查范围与可复现信息

本次审查针对仓库 `smartlijingyang-sudo/layered-cognitive-agent` 的 `main` 分支提交 `87bc05f3`；工作树无未提交改动。检查了插件 API、默认 bundle/profile、组合器、运行时、网关装配路径，并运行了与插件对齐和声明式运行时有关的测试。

| 检查项 | 结果 |
|---|---|
| `@plugin` 装饰模块数量 | 125 个 |
| 默认 `web-standard` active 插件 | 91 个，52 条 DAG 边 |
| 插件类型标注检查 | 通过，175 个文件 |
| 插件声明形状测试 | 失败，覆盖率 85.4%，低于 90% 门槛 |
| 针对性测试 | 14 通过，6 失败 |
| 最严重失败 | `CognitiveRuntime` 调用 `DeclarativeRuntimeDriver` 时缺少必需的 effect/delta registry 参数 |
| capability 门禁 | 报告 8 个未完成 wiring 项，且门禁脚本本身仍按旧的顶层 seam 路径扫描 |

## 一、已经真正插件化的部分

### 1. 基础设施 seam 基本成立

`llm`、`tools`、`transport`、`skills`、`file_store`、`observability`、`sandbox`、`memory`、`search` 和 `state_store` 都通过 Tier-1 seam 与 Tier-2 provider 进入 profile。默认插件树中可以看到这些 service/provider 的 DAG 关系，而不是由 `spawn.py` 直接 new 出后端对象。[1] [2]

LLM 的凭证读取也集中在 `lca-llm-resolver`，并通过 `llm_resolver` capability 向上层暴露，这个方向是正确的。不过 resolver 当前把“凭证读取、模型配置、OpenAI-compatible adapter 创建和 default 注册”集中在一个 provider 中，所以它是**可替换的基础设施入口**，但还不是“多个 LLM adapter 可由 profile 独立选择”的完整 provider registry。[3]

### 2. Brain、Sensor、Gate、Strategy 的插件边界相对真实

Brain 通过 `brains` registry 按名称解析，Sensor 和 Gate 作为 group contribution 加入 `perceive`/`gates` service，Team strategy 通过 `team_strategies` registry 按治理形态解析。这里至少已经具备“新增实现不必修改运行循环”的性质。[4] [5]

`plan_binding.py` 也做对了一件重要的事：它从编译后的 plan 中发现 `composer.*` capability，而不是在 binding 逻辑里写死 `composer.brain`、`composer.body` 等具体实现名。[6] 这说明声明式组合的骨架是真实存在的。

### 3. 六个 phase executor 已经具备较好的替换形状

`phase.perceive.standard`、`phase.think.standard`、`phase.act.standard`、`phase.reflect.standard`、`phase.remember.standard` 和 `phase.stop.standard` 分别作为 capability 进入 `declarative-phase-graph.yaml`。因此替换某一个 phase executor，理论上可以通过替换对应 capability，而不必改六阶段解释器。[7] 这是目前最接近“最小单元可替换”的一组实现。

但这些 executor 多数只是 `StandardPhaseExecutor(SemanticPhase.X)` 的薄包装，真正的通用行为仍集中在 `phase_executors/common.py`。所以它们是**按阶段拆开的可替换单元**，还不是阶段内部每个行为的最小单元。

## 二、明确没有达到最小可组合替换的部分

### 1. P0：声明式运行时存在断裂，当前默认路径无法完整运行

`DeclarativeRuntimeDriver.__init__()` 将 `effect_handler_registry` 和 `delta_handler_registry` 定义为必需的关键字参数，并在每次 run/resume 中使用它们执行 effect 和状态 delta。[8] 但是 `CognitiveRuntime.run()` 与 `CognitiveRuntime.resume()` 创建 driver 时没有传入这两个参数。[9]

仓库已经实现了对应 provider：`lca-effect-handler-provider` 和 `lca-delta-handler-provider`。前者注册 `body.act` 与 `memory.update`，后者注册 11 种 reducer operation。[10] [11] 但是 `bundles/base.yaml`、`bundles/web-app.yaml` 和 `bundles/declarative-phase-graph.yaml` 都没有把这两个 provider 或它们的 seam 加入默认 profile。[2] [7]

这不是抽象层次上的小瑕疵，而是“声明了可插件化运行时边界，却没有把它接入主链”的直接证据。针对性测试实际得到以下失败：

```text
TypeError: DeclarativeRuntimeDriver.__init__()
missing 2 required keyword-only arguments:
'effect_handler_registry' and 'delta_handler_registry'
```

所以当前的真实状态是：**effect/delta 已经被拆成插件化最小方向，但尚未完成默认装配和运行时注入。**

### 2. P1：ActionHandler 插件被 BodyComposer 绕过

仓库有 `action_handler_registry` seam 和 `lca-action-handler-provider`，其设计目标是让新增 action type 通过注册 handler 实现，而不修改核心代码。[12] 但默认 profile 没有加载这个 provider；`BodyComposer` 反而直接调用 `build_default_action_registry()`。[13]

更关键的是，`build_default_action_registry()` 在没有传入 registry 时自行 import 并 new `DefaultActionHandlerRegistry`，然后重新注册四个默认 handler。[14] 这使得已经存在的 `action_handler_registry` capability 变成了**名义上的扩展点**：上层 profile 中即使注册了自定义 ActionHandler，BodyComposer 也不会自动使用它。

同一文件还保留了 `_SCOPE_ACTIONS`、`BUILTIN_ACTION_SPECS` 和旧的 `_operation_for()` 固定表。前两个仍决定 action 的内建集合与 scope 许可，后者虽标注 deprecated，但仍保留具体 `if name == ActionType...` 分支。[14]

要满足最小单元替换，应该由 `BodyComposer` 注入一个已编译的 action handler registry，并让“允许哪些 action”成为 plan/control/authority 数据，而不是由 BodyComposer 内部的 `_SCOPE_ACTIONS` 决定。

### 3. P1：11 个 control contribution 被一个聚合插件绑定

`control.contributions.standard` 一次性提供 11 个 capability：`control.perceive.context`、`control.think.guard`、5 个 act 槽、remember、stop 和 observe 槽。[15] 它在 `_CONTROL_BINDINGS` 中固定了每个 capability 对应的 executor class、phase、顺序和聚合方式；各个 `act_authorize.py`、`act_budget.py`、`think_guard.py` 等文件本身没有独立 `@plugin` 声明。

这意味着当前可以“通过 plan 地址到达 11 个 executor”，但不能自然地做到：只替换 `act.budget` 而保持同一 control plugin 的其他 10 个实现不变。通常需要修改或整体替换 `control.contributions.standard`，或者制造 capability owner 冲突。

因此这里是**按 capability 名称细分、按 provider 文件聚合**，而不是“一个控制原语一个可独立装配插件”。如果项目对“最小单元”要求严格，这一层还没有完成。

### 4. P1：ComponentRegistry 是一个粗粒度默认实现聚合器

`lca.registries.component_registry` 的 setup 在一个插件中直接注册 `InMemoryStateStore`、`SimpleMemorySystem`、`SimpleEventBus`、`MustConsultAllMembers` 和 `LeadBudgetPolicy` 五种具体实现。[16]

这可以作为一个“默认 preset”存在，但它不是最小插件组合：替换其中的 memory 实现，不应该需要替换包含 state store、event bus、gate 和 budget policy 的同一个 L4 插件。更合理的结构是让各实现分别作为 provider/contributor 注入一个 typed registry，另加一个 bundle 负责选择默认实现。

### 5. P1：TeamComposer 内仍有不可替换的协作基础设施

`TeamComposer` 直接实例化 `TeamSharedMemoryStore`、`TransportMemberInvoker`，并直接调用 `build_team_transport()`。[13] 这些对象虽位于组合阶段，但它们决定了 Team 的共享记忆、成员调用和团队 transport 语义，已经不是单纯的“组合根胶水”。

当前 strategy 是可注册的，但 strategy 外层的 team stage、member invoker、shared memory store 和 team transport 仍是固定实现。也就是说，项目可以替换“团队策略”，却不能在不修改 `TeamComposer` 的情况下独立替换“团队成员调用协议”或“共享记忆实现”。

### 6. P1：PerceiveComposer 把 StopRule 选择硬编码为 `default`

`PerceiveComposer` 直接执行 `require_capability(scope, STOP_RULES.key).create("default")`。[13] StopRule 本身已经有 registry 和插件 `stop_rule.default`，因此这里不是完全没有扩展点；问题在于具体选择被组合器固定，`AgentSpec`、bundle 或 compiled plan 没有真正决定 stop rule。

这会导致替换 StopRule 有两种不对称路径：要么把新实现注册为名为 `default` 的替代品，要么修改 `PerceiveComposer`。前者会把“默认名字”当成隐式全局约定，后者又违反组合根只解释 plan 的原则。正确做法应是把 `stop_rule` 作为 graph/plan binding 的显式选择。

### 7. P2：Runtime 仍持有具体默认实现和固定 driver

`CognitiveRuntime` 的构造函数在 reducer 和 topology 缺失时直接创建 `DefaultReducer()` 与 `ClosedSetTopology()`。[9] `runtime_factory.py` 也直接 import 这些具体类并提供同样的 fallback。[17]

`ClosedSetTopology` 作为六阶段闭集的宪法实现，保留在内核是合理的；但 `DefaultReducer` 已经有 plugin setup，而 runtime fallback 意味着 profile 中的 reducer provider 并不是必经路径。更严重的是 `RuntimeDeps` 的字段默认值本身就是 `default_factory=DefaultReducer` 和 `default_factory=ClosedSetTopology`，因此通常不会进入“从 ctx 注入替代实现”的分支。[17]

此外，`CognitiveRuntime.run()`/`resume()` 直接 import 并实例化 `DeclarativeRuntimeDriver`。[9] phase executor 可以由 plan 选择，但 runtime driver 本身不能由 profile 替换。这可以被接受为 L2 内核的一部分，但就不能同时声称“运行时驱动本身也是插件”。目前实际情况是：**phase behavior 可插件化，phase interpretation driver 固定在内核。**

### 8. P2：网关 mode 仍是产品分支，不是 mode plugin

`CognitiveRunnableAssembler` 默认只建立 `solo` 与 `cordis-creator` 两个 adapter，其他 mode 全部落到 `TeamRunnableAdapter`。[18] `gateway/modes.py` 也通过 `if` 分支把模型名映射到三个产品 mode。[19]

这属于网关/产品适配层，不必强行塞进 L2 内核；但它确实是运行行为的一部分。新增一种模式仍然需要修改 `modes.py`、adapter 默认字典或 fallback 语义。要做到完全可组合，应把 `RunnableAdapter` 作为 `run_mode_registry` provider，由 profile/plan 选择 mode，并将 Creator 的工具过滤与 persona policy 一并放入 mode plugin。

### 9. `lca/plugins/` 目录仍混入大量普通 helper

仓库自带的 `test_tier1_plugin_shape` 扫描 `lca/plugins/**/*.py` 时，当前覆盖率只有 **85.4%**，具体缺失包括 `composer/plan_composers.py`、`composer/plan_composition_support.py`、全部 control contribution executor 文件、多个 Creator helper、`providers/llm.py`、多个 `cordis_control` helper 等。[20]

这些文件不应该机械地全部加上 `@plugin`：例如 `plan_composition_support.py` 可以是纯组合 helper，`creator_runtime.py` 可以是工具内部实现。真正暴露的问题是：**目录名称已经被当成插件边界，但代码组织仍是“插件 + 大量内部普通模块”的混合结构。**

因此有两个可选方向：

1. 如果这些 helper 的行为确实不需要独立替换，应把它们移到明确的 `internal/`、`implementation/` 或对应层目录，避免让 `lca/plugins/` 暗示它们是独立插件。
2. 如果这些 helper 的行为需要独立替换，就应为其建立独立 Protocol、capability、provider 和 profile entry，而不是只放在一个插件目录中。

## 三、当前架构的准确分层判断

| 领域 | 当前状态 | 是否满足“最小单元可组合替换” |
|---|---|---|
| LLM、工具、Memory、Sandbox、Transport 后端 | seam + provider + profile | 基本满足，但 LLM resolver 仍偏聚合 |
| Brain、Reasoner、Critic、Sensor、Gate、Strategy | registry/group contribution | 大体满足，部分组内行为仍聚合 |
| 六个 phase executor | 每 phase 一个 capability | 阶段级满足，阶段内部未完全满足 |
| Control contribution | 11 个 capability 由一个 provider 统一提供 | 不满足独立替换 |
| ActionHandler | seam/provider 已存在，但 BodyComposer 未接入 | 不满足，属于断线扩展点 |
| Effect/Delta handler | provider 已存在，默认 profile 和 runtime 未接线 | 不满足，且当前导致运行失败 |
| Reducer | 有 plugin 壳，但 runtime 有具体默认回退 | 部分满足 |
| Loop topology | 固定闭集内核 | 作为内核例外合理 |
| Team strategy | registry 可替换 | 满足策略级替换，但 Team 基础设施仍固定 |
| Team transport/shared memory/invoker | Composer 内直接构造 | 不满足 |
| Agent/CognitiveRuntime 对象闭合 | 组合根直接构造具体对象 | 作为组合根例外可接受 |
| Gateway mode | adapter 字典和字符串分支 | 不满足完全插件化，但可作为 L4 产品适配层例外 |
| Journal/Reducer 单写/CommandEnvelope 窄门 | 宪法约束 | 不应被插件改写 |

## 四、哪些确实应该保留在内核

不应该把“一切皆插件”理解成所有代码都必须动态加载。以下内容保留为内核或宪法边界是合理的：

第一，六阶段闭集及其基本解释语义应保持固定，否则插件可以通过新增 phase 改写认知协议。`ClosedSetTopology` 可以是可注入的实现，但它的闭集约束本身属于内核不变量。[21]

第二，Reducer 的唯一状态写入口、`CommandEnvelope` 的执行窄门、plan_ref 校验、幂等和安全策略不能交给任意插件绕过。插件可以提供 reducer handler 或 effect handler，但不能自行直接改写 State 或绕开 envelope。[8] [9]

第三，`CognitiveAgent`、`CognitiveRuntime` 这类最终对象的闭合可以由 L4 组合根负责。它们是“组合结果”，不是某一种业务行为实现。真正需要检查的是：组合根是否只消费已编译 capability，而不是在内部选择具体策略。

第四，HTTP 路由、OpenAI payload 适配和进程生命周期可以是 gateway 基础设施，不必都成为业务插件；但网关中的 mode 语义和运行 adapter 选择如果要宣称完全插件化，就应继续外置。

## 五、建议的重构顺序

### 第一阶段：先修复运行链断裂

将 `effect_handler_registry`、`delta_handler_registry` 作为 profile 必须提供的 capability，加入对应 seam/provider 和默认 bundle；再在 `CognitiveRuntime` 中从已绑定的 runtime dependencies 传入 `DeclarativeRuntimeDriver`。同时将默认 profile boot validation 改成：声明式 plan 存在时，两个 registry 必须可解析，不能等到第一个 turn 才失败。

这一阶段优先级最高，因为它不是“架构美观”，而是当前默认声明式 Agent 的可运行性问题。

### 第二阶段：把“已经存在但未接入”的 seam 接上

BodyComposer 必须消费 `action_handler_registry`，不能在 helper 内部自行 new 默认 registry。Runtime factory 必须消费 profile/plan 绑定的 reducer、topology、stop rule；如果需要测试默认值，应把 fallback 限定在 test-only constructor 或 Null profile，而不是生产组合路径。

### 第三阶段：将聚合 provider 拆成 contributor provider

建议把 `control.contributions.standard` 拆成每个 control slot 一个 provider，或者定义统一的 `ControlContributionRegistry`，每个插件只注册一个 slot contribution，另由 bundle 负责装载标准集合。ComponentRegistry 也应改为“空 registry seam + 多个独立 default contributor”，而不是一个插件直接 new 五种跨领域实现。

### 第四阶段：把 Team 组合基础设施外置

为 `TeamSharedMemoryStore`、`TransportMemberInvoker`、`build_team_transport` 建立 typed Protocol/capability，并把 `TeamComposer` 改为从 compiled plan 解析这些能力。Team strategy 继续使用现有 registry，但 strategy、stage、invoker、transport、shared memory 应成为不同的选择轴。

### 第五阶段：引入真正的替换性测试

当前很多测试验证的是“模块存在”“registry 能注册”“插件声明形状正确”，但还缺少替换性测试。至少应增加以下场景：替换一个 phase executor 不修改 interpreter；替换一个 ActionHandler 不修改 BodyComposer；替换一个 effect/delta handler 不修改 runtime；替换单个 control slot 不影响其他 slot；替换 Team invoker/shared memory 不修改 TeamComposer；新增 mode 只增加 profile/plugin 文件而不改 gateway 分支。

## 最终判断

**所以，答案不是“完全没有插件化”，也不是“已经全部覆盖”。** 当前项目已经有一个相当完整的插件治理外壳：Manifest、capability、DAG、profile、compiled plan、scope、control slot、phase graph 都已建立。但它仍然存在明显的“外壳先行、行为未完全接线”现象：一些能力只在文档或 provider 文件中插件化，一些组合器仍在直接选择具体实现，一些所谓独立 capability 实际由一个聚合插件统一拥有，还有一部分运行时插件当前根本没有进入默认 profile。

用一句更严格的话概括：

> **当前 LCA 是“插件化的 Agent 组装框架”，还不是“所有非内核行为都以最小插件单元闭合可替换的 Agent 内核”。**

## References

[1][ref-plugin-api]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/harness/plugin_api.py> — Plugin Manifest、PluginContext 与审计交互面。

[2][ref-bundles]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/bundles/base.yaml> — 基础 seam/provider；<https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/bundles/web-app.yaml> — 默认认知与组合插件。

[3][ref-llm-resolver]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/seam_definitions/llm_resolver.py> — LLM credential/adapter resolver。

[4][ref-plan-composition]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/composer/plan_composition_support.py> — Brain、Gate、Memory、StateStore 等 capability 解析。

[5][ref-plan-composers]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/composer/plan_composers.py> — Body、Perceive、Team 组合器中的直接绑定。

[6][ref-plan-binding]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/composer/plan_binding.py> — 从 compiled plan 发现 composer capability。

[7][ref-declarative-bundle]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/bundles/declarative-phase-graph.yaml> — phase executor、phase edge 与 control contribution 默认 entries。

[8][ref-declarative-runtime]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/layer2_runtime/declarative_runtime.py> — effect/delta registry 为声明式 driver 的必需依赖。

[9][ref-runtime-loop]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/layer2_runtime/runtime_loop.py> — `CognitiveRuntime` 直接构造声明式 driver 且未传入两个 registry。

[10][ref-effect-handlers]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/providers/effect_handlers.py> — 默认 effect handlers。

[11][ref-delta-handlers]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/providers/delta_handlers.py> — 默认 11 种 delta handlers。

[12][ref-action-handlers]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/providers/action_handlers.py> — ActionHandler provider。

[13][ref-composers]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/composer/plan_composers.py> — BodyComposer、PerceiveComposer、TeamComposer。

[14][ref-action-catalog]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/layer1_cognitive/body/action_catalog.py> — builtin action 表与默认 registry builder。

[15][ref-control-standard]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/control_contributions/standard.py> — 11 个 control capability 的聚合 provider。

[16][ref-component-registry]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/registries/component_registry.py> — 多个具体默认实现的集中注册。

[17][ref-runtime-factory]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/plugins/composer/runtime_factory.py> — reducer/topology/stop rule fallback。

[18][ref-runnable-assembly]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/gateway/runs/runnable_assembly.py> — mode adapter 和工具物化。

[19][ref-gateway-modes]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/gateway/modes.py> — gateway mode 映射。

[20][ref-plugin-shape-test]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/tests/test_plugin_alignment.py> — 插件目录声明形状与覆盖率门禁。

[21][ref-loop-topology]: <https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/main/lca/layer2_runtime/loop_topology.py> — 六阶段闭集拓扑实现。
