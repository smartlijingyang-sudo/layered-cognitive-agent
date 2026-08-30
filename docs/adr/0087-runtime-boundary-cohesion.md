# ADR-0087：运行时边界内聚与遗留 Run 注册表拆分

## 状态

**Accepted — 2026-08-27**

## 背景

`base` bundle 曾同时提供基础存储/投影能力和 L4 的 `session_live_builder`。后者必须依赖已经选择的 `agent_loop`；虽然轻量 Profile 可以通过 `runtime-core` 显式选择 loop 以支持其他运行行为，但它们不会选择 Session Spine。因此 Profile 解析曾在启动前因 `base` 中的 builder 声明了不存在的 `agent_loop` 而失败；基础 bundle 对外承诺了一个实际不能运行的 Session Spine。

同时，运行时装配和遗留 `/runs` 兼容路径各自混合了多种生命周期。`runtime_assembly` 同时承担图校验、capability 查找、恢复适配器选择、阶段执行器绑定和对象构造。`RunRegistry` 同时维护进程内索引、去重、保留策略、RunLocator 路径、进程 Journal 投影和实时统计。`RunLifecycleCoordinator` 又在状态转换之外手写 scoped Journal 失败事实。这些职责虽然相关，却有不同的所有权、替换频率和失败语义，使读者必须跨越多层细节才能判断一项改动的位置。

## 决策

将运行时与基础设施的边界按可执行承诺和生命周期拆分。

| 边界 | 决策 | 原因 |
|---|---|---|
| 基础 bundle | `base` 不再提供 `session_live_builder` | 基础设施、只读工具和观测 Profile 不应隐式承诺 Session Spine。 |
| 运行 bundle | `runtime-core` 或 `web-app` 可显式提供 `agent_loop`；`web-app` 提供 `session_live_builder` | loop 是可独立选择的运行行为；builder 与其已选择的 loop 构成不可拆的 Session Spine 闭合。 |
| 运行时装配 | `runtime_assembly` 只编排“校验图 → 闭合能力 → 构造 runtime” | capability 解析、阶段绑定和恢复 adapter 归入 `composer.internal.runtime_capabilities`，避免细节泄漏到组合根。 |
| Run 注册表 | `RunRegistry` 保持兼容门面，委托 `RunSessionIndex`、`RunLocator` 和 `ProcessJournalBinding` | 进程内缓存、耐久路径与进程投影拥有独立生命周期，不应由一个可变 registry 字典隐式耦合。 |
| 失败观测 | `failure_recording.record_run_failure` 单独拥有 best-effort Journal 失败事实 | 失败事实记录不能遮蔽原始错误，也不应与生命周期状态机纠缠。 |

`RunSession` 暂时保留为 legacy carrier 的单 run 可变聚合；该兼容表面不等于 durable Session Spine。跨重启恢复和 command-driven Session 的演进仍应通过 `lca/harness/session/` 与 `AgentRegistry` 推进，不在本 ADR 中通过拆字段制造第二份会话状态。

## 后果

| 维度 | 结果 |
|---|---|
| Profile 可理解性 | 轻量 Profile 可显式选择其所需 loop，但只在需要 Session Spine 时声明 live builder。 |
| 局部性 | runtime capability 的错误和替换集中在内部闭合模块；装配代码不再知道每个 capability key。 |
| 生命周期 | 进程索引、耐久 locator、共享 Journal 投影和单次执行失败记录均有唯一 owner。 |
| 兼容性 | `RunRegistry`、`RunSession` 及其方法保持既有调用面；Gateway 无需同时迁移。 |
| 风险边界 | 本重构不改变 phase graph、Reducer、Effect Gateway、Journal schema 或任何外部副作用语义。 |

## 验证约束

- `profiles/coding-agent.yaml` 与 `profiles/genai-traced.yaml` 必须能解析；它们可通过 `runtime-core` 提供 `agent_loop`，但不得提供 `session_live_builder`。
- `profiles/web-standard.yaml` 必须同时提供 `agent_loop` 与 `session_live_builder`。
- production runtime closure 必须通过 `composer.internal.runtime_capabilities` 从 immutable plan 的 provider bindings 解析；`runtime_assembly` 不得直接使用 `ScopeCapabilityResolver`。
- `RunRegistry` 的 locator、去重、终端保留、Journal 绑定与实时统计兼容测试必须通过。
- lifecycle 执行、HIL resume、terminalization 和取消路径必须继续通过现有 Gateway 回归测试。

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 让 `session_live_builder` 去掉 `agent_loop` 依赖 | 仅把错误推迟到首次创建 Agent，Profile 已解析却不具备运行闭合，违反 fail-closed。 |
| 将 `agent_loop` 无条件下沉到 `base` | 使基础设施 Profile 隐式携带 Gateway/L4 行为，并扩大每个轻量部署的对象图；需要 loop 的 Profile 应通过 `runtime-core` 或专用运行 bundle 明确选择。 |
| 直接以新 durable Session 取代 `/runs` | 这是更大迁移，超出本次保持兼容的职责边界；应有独立的 command/session cutover。 |
| 继续以单一 `RunRegistry` 管理全部生命周期 | 路径、投影和内存索引的故障/清理规则不同，聚合会持续增加隐式耦合。 |
