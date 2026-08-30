# ADR-0095：LoopGuard 的解释器局部性

## 状态

**Accepted — 2026-08-28**

## 背景

`LoopGuardEvaluator` 是一个纯策略：它只在声明式阶段图选择下一条带 `loop` 的边时被调用，决定该边是否允许重新进入。此前它同时被建模为运行时 capability、`RuntimeCapabilityClosure` 字段、`ProductionRuntimeDeps` 字段和 `DeclarativeRuntimeBindings` 字段，再由运行时绑定转交给解释器。

这条路径使一个只属于阶段图 traversal 的策略穿过 Profile 闭合、运行时绑定和完整运行时接口。按照删除测试，删除这些中间字段不会减少解释器的能力；它只会把策略注入集中到解释器工厂。因此这些字段是浅 module 的重复适配，而不是第二个真实 seam。

## 决策

`LoopGuardEvaluator` 仍是可替换的 Profile-selected provider，但由 `DefaultDeclarativeInterpreterFactory` 在构造期闭合。解释器工厂是唯一的替换 seam；`GenericPlanInterpreter` 在内部持有该策略并用于 loop-edge traversal。

`loop_guard_evaluator` 可以继续作为启动期 provider binding 和插件依赖存在，以便完成审计与选择，但不得进入 `RuntimeCapabilityClosure`、`ProductionRuntimeDeps` 或 `DeclarativeRuntimeBindings` 的字段和公共装配参数。

| 位置 | 所有者 | 允许的职责 | 禁止的职责 |
|---|---|---|---|
| `lca.plugins.providers.loop_guard` | Profile provider | 提供可替换的 LoopGuard evaluator | 直接修改运行状态或拥有整个运行时 |
| `DefaultDeclarativeInterpreterFactory` | 解释器装配 seam | 在构造期接收并闭合 traversal 策略 | 将策略继续向 RuntimeBindings 外传 |
| `GenericPlanInterpreter` | 声明式 traversal module | 调用 evaluator 判断 loop edge 是否允许 | 重新解析 Profile 或 Context capability |
| `RuntimeCapabilityClosure` / `ProductionRuntimeDeps` / `DeclarativeRuntimeBindings` | 运行时可信内核 | 携带解释器工厂和其他必要闭包 | 持有 LoopGuard 顶层字段 |

## 后果

解释器 traversal 策略的接口深度增加，运行时绑定的字段复杂度降低；替换 LoopGuard 时只需替换 provider 或解释器工厂，其他认知图和运行循环不变。测试可以通过 `DefaultDeclarativeInterpreterFactory` 与 `GenericPlanInterpreter` 的公开构造接缝验证策略行为，而不必构造完整 RuntimeBindings。

这与 ADR-0094 的 StopPolicy 局部性一致：固定执行阶段或 traversal 内部的策略由其直接消费者闭合，不被提升为认知图或运行时的同级事实。

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 保留 `DeclarativeRuntimeBindings.loop_guard_evaluator` | 让 traversal 专属策略扩散到所有运行时装配调用方，降低 locality。 |
| 将 LoopGuard 放进 `AgentGraph.phase_capabilities` | 它不是认知群贡献，也不由任何 phase executor 消费；会把执行器内部策略伪装成图事实。 |
| 在 `GenericPlanInterpreter` 内硬编码默认 evaluator | 失去 Profile-selected 替换 seam，并使测试无法通过一个明确 interface 替换策略。 |

## 验证约束

- `RuntimeCapabilityClosure`、`ProductionRuntimeDeps` 和 `DeclarativeRuntimeBindings` 不得声明 `loop_guard_evaluator` 字段。
- `DeclarativeInterpreterFactory.create` 不得要求调用方传入 LoopGuard；具体工厂必须在构造期闭合它。
- 默认解释器工厂 provider 必须显式声明并审计其 `loop_guard_evaluator` require。
- `GenericPlanInterpreter` 必须继续保持 LoopGuard 的纯策略行为与 loop-edge 选择语义。

## 关联

本决策沿用 ADR-0075 的最小可信运行内核、ADR-0076 的能力布局和 ADR-0094 的策略局部性，不重新打开这些决策。
