# Agent Loop 与认知原语插件化补充

**日期：**2026-08-27
**状态：**Implemented
**作者：**Manus AI

## 结论

当前 Agent Loop 已具备两层可替换边界。第一层是完整运行时：`RuntimeFactory` 根据编译后的 `DeclarativeRuntimeBindings` 创建 `Runtime`，使完整的认知运行时可以由 profile 替换。第二层是 carrier：Gateway 通过 `run_loop_driver_registry` 解析执行目标，无需按 loop 类型硬编码分支。阶段节点则由已编译的 `phase.*` capability 显式绑定，解释器只遍历已验证的 phase graph。

但 **“阶段可替换”不自动等于“阶段内部原语可替换”**。审查发现，默认 `ModularBrain` 曾把 Think 的 shortcut、skill routing、reasoner、classifier、gate 顺序，以及 Reflect 的 critic/空反思回退直接写在门面类中。虽然整个 `Brain` 可替换，替换其中任一原语仍需复制或修改相邻编排代码。这一变更将这两个认知子流程提升为独立的 profile-selected capability。

| 层级 | 变更前 | 变更后 | 替换粒度 |
|---|---|---|---|
| 完整 Loop | `RuntimeFactory` / `Runtime` | 保持不变 | 运行时实现 |
| 阶段节点 | `phase.perceive`、`phase.think` 等 capability | 保持不变 | 单个 phase executor |
| Think 子流程 | `ModularBrain.think()` 固定顺序 | `cognitive.think_pipeline` | Think 编排策略 |
| Reflect 子流程 | `ModularBrain._default_reflect()` 回退 | `cognitive.reflection_pipeline` | Reflect / fallback 策略 |
| 感知成员 | `PerceiveService` contributor | 保持不变 | 单个 Sensor |
| Think guard | plan-bound `control.think.guard` | 保持不变 | 控制贡献 |

> **边界原则：** 认知 pipeline 只组织候选 `Decision` 或 `Reflection`，不拥有外部 effect、Journal、Reducer 提交、phase cursor 或图遍历权。它只能使用被显式注入的协作者；技能路由导致的状态投影仍必须走 `Reducer.apply_skill_route()`。

## 本次实现

新增 `CognitiveThinkPipeline` 和 `CognitiveReflectionPipeline` 两个 runtime-checkable 协议，并在 contracts 层声明对应 capability 键。默认实现 `StandardCognitiveThinkPipeline` 与 `StandardCognitiveReflectionPipeline` 保持原有语义：Think 仍按 shortcut → skill route → reasoner → classifier → local gate → plan-bound gate 执行；Reflect 仍优先调用已配置 Critic，否则返回最小合法的 ON_TRACK 空反思。

两个默认实现分别由独立 provider 插件装配。`lca-cognitive-think-pipeline-standard` 与 `lca-cognitive-reflection-pipeline-standard` 都由 `bundles/base.yaml` 明确选入。`lca-brain-simple` 和 `lca-brain-modular` 以同一份声明的 dependency closure 构造 `SimpleBrainFactory`，从而将两个 registry alias 的 gate、reasoner、classifier 与 pipeline 绑定统一到一个组装点；`ModularBrain` 因而只做协议级委托。四个组成 Brain 与 Think / Reflect 子流程的插件均显式标注为 `G5_COGNITION`，使其在插件图中具有一致、可审计的主语义坐标。Lead Brain 包装也保留既有 pipeline 实例，不会在组合过程中悄然重选实现。

| 新契约 / 组件 | capability | 生产选择点 | 责任 |
|---|---|---|---|
| `CognitiveThinkPipeline` | `cognitive.think_pipeline` | `lca-cognitive-think-pipeline-standard` | 组织 Think 子步骤并返回 Decision |
| `CognitiveReflectionPipeline` | `cognitive.reflection_pipeline` | `lca-cognitive-reflection-pipeline-standard` | 组织 Critic / fallback 并返回 Reflection |
| `SimpleBrainFactory` | `BRAINS` registry | `lca-brain-simple` / `lca-brain-modular` | 通过共享的声明依赖闭合已选择的协作者，不再选择子流程默认值 |
| `ModularBrain` | `Brain` | phase Think / Reflect executor | 委托给已注入 pipeline，维持稳定调用面 |

## 未插件化实现的审查结果

下表将“可替换”与“应保留在内核”区分开来。不可替换不一定是缺陷；关键在于非内核行为是否有稳定契约、独立绑定和 profile 选择点。

| 区域 | 当前状态 | 结论 / 后续方向 |
|---|---|---|
| `GenericPlanInterpreter` 图遍历、checkpoint/resume、终态投影 | 固定内核 | **应保留**。插件不可绕过计划验证、访问预算、Journal、Reducer、Effect Gateway 或终态协议。 |
| `PhaseExecutionTransaction` 的提交顺序 | 固定内核 | **应保留**。这是事实追加与状态投影的可信计算基。 |
| `CognitiveRuntime` 生命周期事件载体 | 固定协议门面 | 可由完整 `RuntimeFactory` 替换；默认类本身不必按每个 `try/except` 拆成插件。 |
| `ModularBrain` Think / Reflect 编排 | 原先固定在类中 | **本次已修复**，细化为两个独立 L1 原语 provider。 |
| `PerceiveService` 的 production sensor 成员 | contributor registry | 已插件化；标准 bundle 显式声明 sensor 成员。`register_builtin_sensors()` 仅为非 booted 的兼容入口。 |
| Recovery Reflect executor 的失败判断 | phase executor 内部策略 | 仍是阶段内部的固定策略；如需替换“失败判定”本身，应后续增加独立 `ReflectionRecoveryPolicy`，而不是新增第七 phase。 |
| 默认 ActionHandler 集合 | registry/provider 加闭集动作目录 | action handler 本身已有接缝；动作类型许可与 command authority 必须仍受 plan / scope 治理。 |
| Phase graph 语义相与 edge selection | plan + 内核解释 | 节点实现、边和 loop guard 可经计划选择；图遍历和验证不能由任意 plugin 改写。 |

## 验证策略

`tests/test_cognitive_pipeline_plugins.py` 覆盖四类关键断言。第一，默认生产 profile 显式声明并提供两个新 capability；第二，两个 Brain registry alias 共享完整的认知依赖闭合，且 Brain 与子流程 provider 的主语义坐标均为 G5；第三，自定义 Think 或 Reflect pipeline 可在不修改 `ModularBrain` 的情况下被委托调用；第四，`ModularBrain` 源码不再包含 `generate_thoughts()` 或 `_default_reflect()` 等固定实现细节。现有 Think guard 与 skill-router 测试继续约束 Reducer 为唯一状态投影路径。

## 参考实现

[1]: ../../lca/plugins/composer/runtime_assembly.py "RuntimeFactory 组合边界"
[2]: ../../lca/harness/declarative/interpreter.py "声明式图遍历内核"
[3]: ../../lca/contracts/protocols/cognitive_pipeline.py "认知子流程协议"
[4]: ../../lca/layer1_cognitive/brain/cognitive_pipeline.py "默认认知子流程实现"
[5]: ../../lca/plugins/providers/cognitive_think_pipeline.py "Think provider"
[6]: ../../lca/plugins/providers/cognitive_reflection_pipeline.py "Reflect provider"
[7]: ../../tests/test_cognitive_pipeline_plugins.py "替换性测试"
