# ADR-0088：Profile 选择完整 Agent Loop Runtime

## 状态

**Accepted — 2026-08-27**

## 背景

尽管运行时的 Effect Gateway、Delta Reducer、Journal、Checkpoint Resolver 与终态投影已由独立 Capability Factory 提供，生产装配仍在 `runtime_assembly` 中直接调用 `build_cognitive_runtime()`。这使 `CognitiveRuntime` 成为唯一可执行的 Agent Loop：替换完整循环需要修改 L3/L4 组合代码，而不是通过 Profile 选择一个插件。

这种隐式耦合违背“实现通过插件替换”的组合纪律，也使替代性循环无法在保持同一 AgentGraph、Plan、Reducer、Effect Gateway 和 Journal 语义的前提下接入。

## 决策

新增单值 Capability `runtime_factory`，其实现必须满足 `RuntimeFactory` Protocol。生产装配只负责以下三件事：验证 AgentGraph、从 immutable plan 关闭已声明的能力、构造 `DeclarativeRuntimeBindings`。随后它调用 Profile 解析出的 `RuntimeFactory.create(bindings)`，不再选择或实例化具体运行时类。

默认行为由 `lca-cognitive-runtime-factory` 插件提供 `CognitiveRuntimeFactory`，并在 `bundles/base.yaml` 中显式启用。因此现有 Profile 的行为保持不变；需要替换完整 Agent Loop 的 Profile 只需以另一个 Provider 替换 `runtime_factory`，无需修改 L3 Agent 装配、L4 API 或 Gateway carrier。

| 边界 | 所有者 | 不可承担的职责 |
|---|---|---|
| `RuntimeFactory` Protocol | contracts | 不依赖 L2 具体运行时类 |
| `runtime_factory` Capability | Profile / Bundle | 不从环境或隐式默认选择 Loop |
| `runtime_assembly` | L3 composition adapter | 不直接构造或命名具体 Agent Loop |
| `CognitiveRuntimeFactory` plugin | L2 default implementation | 不解析环境配置或修改 Plan |

## 后果

生产运行时的完整 Loop 选择成为 Profile 的显式事实，并继续受 Plugin Manifest、`provides → requires` 拓扑装配与缺失能力 fail-closed 语义约束。`CognitiveRuntime` 保留为默认实现，既有测试和运行语义不变。

替代 RuntimeFactory 需接受 `DeclarativeRuntimeBindings` 所代表的不可变依赖闭包，并返回实现 `Runtime` Protocol 的对象。它不得绕过 Declarative Phase Graph、Reducer、Effect Gateway、Journal、checkpoint 或 capability grant 等既有控制面。

## 验证约束

- `profiles/web-standard.yaml` 必须在解析后显式提供 `runtime_factory`。
- `runtime_assembly` 不得直接调用 `build_cognitive_runtime()` 或导入具体 `CognitiveRuntime`。
- 默认 `CognitiveRuntimeFactory` 必须实现 `RuntimeFactory`，并拒绝未验证的 bindings 输入。
- 既有运行时装配、默认 Context、Session Spine 与 Gateway cognitive loop 回归测试必须通过。

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 继续直接调用 `build_cognitive_runtime()` | 完整 Loop 的选择仍硬编码在组合根，替换需要改核心代码。 |
| 在 `CognitiveRuntime` 内部注册所有替代循环 | 把实现选择藏进 L2，且扩大运行时内核职责。 |
| 将完整 Loop 选择放入 Gateway | Gateway 是 Carrier；该方案会让 HTTP 层依赖认知运行时实现。 |
| 为替代循环新增平行 AgentGraph / Plan | 会破坏共享的闭集、Journal 和治理机制，形成平行 schema。 |
