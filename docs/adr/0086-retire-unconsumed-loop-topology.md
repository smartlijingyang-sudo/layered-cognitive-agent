# ADR-0086：退役未消费的 LoopTopology 生产闭包

## 状态

**Accepted — 2026-08-26**

Supersedes: ADR-0070 中 `LoopTopology` Protocol 的生产运行时职责，以及 ADR-0076 §四中将 `loop_topology` 作为生产闭包必需 binding 的部分决定。

## 背景

声明式运行时已经将阶段语义、顺序、可达性、循环守卫与执行器绑定收敛到 `CognitivePhaseGraphPlan`、`SemanticPhase`、`PhaseBinding` 和 `PhaseGraphValidator`。生产 `CognitiveRuntime` 及其 `DeclarativeRuntimeBindings` 只读取编译计划与完整运行 binding，不读取 `loop_topology` capability。

但仓库仍保留 `LoopTopology` Protocol、`ClosedSetTopology` provider、基础 bundle 条目、production closure 目录、profile fallback 以及一组静态测试。该模块的接口几乎等于实现；删除它不会把复杂度集中到任何真实消费者，而只是移除一条没有运行时消费方的平行拓扑表示。因此它是一个浅模块，导致理解六阶段语义时需要在声明式 `PhaseGraph` 与旧拓扑之间跳转，破坏局部性。

## 决策

`PhaseGraph` 是认知阶段闭集和执行顺序的唯一生产事实源。

- `SemanticPhase` 继续定义封闭的六阶段词表：`perceive`、`think`、`act`、`reflect`、`remember`、`stop`。
- `PhaseGraphValidator` 继续在编译期验证每个语义阶段存在、可达、因果顺序、终态路径与带 guard 的回边。
- 移除 `LoopTopology`、`LoopPhase`、`LoopPhaseKind`、`ClosedSetTopology` 和 `loop_topology` capability，且不再将其列入 production closure、bundle 或 test profile fallback。
- HookRegistry 保持为观察接缝；hook 不再定义或暗示认知阶段顺序、控制流或 state mutation 权限。
- 生产闭包目录只能收录 `DeclarativeRuntimeBindings`、运行 driver 或其已编译计划实际读取的 capability。新增闭包 capability 时，必须同时提供运行时消费测试。

## 后果

| 维度 | 结果 |
|---|---|
| 模块深度 | 删除无消费者的浅模块，阶段约束集中到深度更高的 `PhaseGraph` 接缝。 |
| 局部性 | 修改阶段语义只需查看声明式 plan 和 validator，不再在旧 topology、bundle、closure 和测试之间跳转。 |
| 杠杆 | production closure 校验直接反映运行时所需依赖，缺失 binding 的错误更可信。 |
| 测试表面 | 阶段闭集由 `SemanticPhase` 与 `PhaseGraphValidator` 覆盖；不再测试没有消费者的 provider 存在性。 |
| 兼容性 | 移除未执行的 Python API 与 profile plugin id。下游若仍引用它，应迁移到声明式 `PhaseGraph`。 |

## 验证约束

- `rg "loop_topology|LoopTopology|ClosedSetTopology" lca bundles profiles tests` 不应再返回生产代码或有效测试引用。
- `tests/declarative/test_phase_graph.py` 必须验证完整 phase binding、稳定 plan hash 和声明式执行器路径。
- `tests/test_boot_binding_completeness.py` 必须只对实际生产 binding 验证缺失即失败。
- `tests/test_architecture_conformance.py` 必须断言 `SemanticPhase` 的六阶段闭集，并保持 hook 的观察性约束。

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 保留 LoopTopology 作为“未来扩展点” | 没有两个独立适配器或任何生产消费者，所谓接缝只是推测性的，违反 YAGNI。 |
| 继续将其列入 production closure | compile gate 会拒绝运行时根本不读取的能力，测试表面与真实装配脱节。 |
| 将 PhaseGraph 再投影回 topology | 重新创建平行事实源，增加同步负担且不提高运行时可替换性。 |
| 让 HookRegistry 承担阶段顺序 | hooks 是观察机制；允许其驱动控制流会重新引入不可验证的双轨语义。 |
