# Agent Loop 插件化审计与演进说明

**日期：**2026-08-27
**状态：**Implemented（与本次变更同步维护）
**作者：**Manus AI

## 背景与审计结论

当前 LCA 已完成关键的“完整运行时由 Profile 选择”迁移：`runtime_assembly` 仅负责闭合 `AgentGraph`、计划声明的 capability 与不可变 `DeclarativeRuntimeBindings`，然后经 `RuntimeFactory.create()` 交给 Profile 选择的运行时实现。Gateway 则通过 `run_loop_driver_registry` 解析 carrier 侧 driver。因此，LCA 已经具备了将**核心认知循环**和**HTTP carrier loop driver**分别替换的两层插件化边界。

| 层面 | 现有责任 | 当前有效机制 | 审计结论 |
|---|---|---|---|
| 语义执行 | 解释已验证的 phase graph，提交事实、effect 与 delta | `DeclarativeRuntimeBindings` → `RuntimeFactory` → `Runtime` | 完整 loop 选择已脱离 L3/L4 硬编码 |
| 领域能力 | 感知、推理、执行、反思、记忆与停止 | Phase executor capability bindings | 通过不可变 plan 提前闭合，避免运行期 ambient lookup |
| 执行治理 | Journal、effect gateway、idempotency、checkpoint、reducer、终态投影 | 独立 provider factory | 已成为 profile 显式事实，且受单写与可恢复约束 |
| 观察面 | phase span / 诊断 | 单值 `phase_observer` capability | 需要支持多个纯观察插件并保持对 transaction 的零控制权 |
| Carrier | 请求到可运行对象的适配 | `run_loop_driver_registry` | Gateway 不再按 loop 类型硬编码分支 |

> 本次不引入第七个认知阶段，不允许 observer 改写 `AgentState`、`Decision` 或 phase payload，也不允许绕过 Journal、Reducer、Effect Gateway、checkpoint 与 capability grant。扩展发生在既有观察面和组合面。

## 业界对照及可采纳原则

LangGraph 将调用期依赖、存储、流输出、执行标识及服务端元信息放进显式 Runtime，并把它注入工具和 middleware，而非使用全局状态；这强化了依赖注入、可测试性和运行隔离的边界。[1]

OpenAI Agents SDK 将 agent loop、循环中的工具调用、委派、guardrail、会话与 trace 区分为独立能力；在用户希望自行控制自定义循环和分支时，建议由应用拥有 loop，而 SDK 负责提供结构化能力表面。[2]

DeepSeek Harness 的 plugin-first 结构将模型、工具、会话日志与 agent loop 都作为可从 profile/bundle 配置替换的插件；注册行为是可卸载 effect，Profile 以有序 bundle 与 patch 组合实际运行树。[3]

| 原则 | LCA 对应实现 | 本次落点 |
|---|---|---|
| 显式 runtime DI | `DeclarativeRuntimeBindings` | 不增加运行期全局查找；observer 只接收当前 phase 的只读输入 |
| 完整 loop 可替换 | `RuntimeFactory` capability | 新增 factory 输出的运行时协议后置校验，及时 fail-closed |
| 行为与观察分离 | `PhaseExecutionTransaction` | 新增只读 observer 组合器，不参与 Journal/effect/delta/state commit |
| 配置驱动组合 | `@plugin`、bundle、profile | 观察 contributor 各自独立注册，由 profile 控制组合与排序 |
| 可诊断、可审计 | Phase spans 与 Journal | 观察者故障隔离为显式策略；默认不让遥测故障改变业务执行 |

## 缺口与实施决策

`phase_observer` 是单值 capability，默认实现只能覆盖或替换，无法优雅地组合 tracing、评测计时、审计计数或调试观察等多个独立的纯观察能力。把这些逻辑塞回 transaction、把多个 provider 直接竞争单值 seam，或借由控制 hook 回写 State，都会破坏 LCA 的插件化和双平面边界。

为此，本次采用 **Observer Contributor Registry + Composite Observer Provider** 模式：

1. 每个观察插件只提供 `PhaseObserverContribution`，声明稳定 ID、优先级与只读 observer；注册表负责拒绝重复 ID、按优先级稳定排序，并冻结快照。
2. `CompositePhaseObserver` 顺序嵌套已冻结 observer 的 context manager；所有 observer 仅包裹 executor 调用，不能访问 transaction、effect gateway、reducer 或 journal。
3. `lca-phase-observer-provider` 仍是唯一的 `phase_observer` provider，但它从注册表构造复合对象，维持 production closure 的单值能力与原有 API。
4. 观察器只接收冻结的 `PhaseStateSnapshot`，不再接收 live `AgentState`。快照仅含 trace、角色、step、状态及复制后的 budget 标量，排除 task、working memory、artifact 与所有控制依赖；因此 observer 无法将“观测”变成绕过 Reducer 的可写状态旁路。
5. 失败策略显式配置。默认 `fail_open`：观测器进入、退出或构造失败仅以结构化日志记录，不干扰 agent 执行；`fail_closed` 可由严格测试/合规 profile 选择。
6. `runtime_assembly` 在 factory 返回后验证对象满足 `Runtime` protocol，以便 provider 配置错误在组合期失败，而不是延迟到 gateway 或用户请求处理时。

此设计符合“Protocol → Seam → Provider / Adapter → Registry → Plugin → Profile / Bundle”的扩展路径，同时把**控制能力**继续收敛在 declarative plan、effect gateway 和 reducer 内。

## 验收标准

| 标准 | 验证方式 |
|---|---|
| 多个 observer 可由独立插件贡献并按优先级组合 | 单元测试覆盖排序、嵌套顺序与冻结快照 |
| observer 不可引入 State / effect / journal 控制旁路 | 冻结 `PhaseStateSnapshot`、API 最小化、transaction 不变及架构测试 |
| 单个 telemetry observer 失败不会默认中断 agent | `fail_open` 单元测试 |
| 严格 profile 可要求 observer 故障阻断 | `fail_closed` 单元测试 |
| runtime provider 返回非 Runtime 时立即拒绝 | runtime assembly 单元测试 |
| 既有默认 profile 和回归场景保持通过 | 全量质量门禁与相关集成测试 |

## References

[1]: https://docs.langchain.com/oss/python/langchain/runtime "LangChain Runtime documentation"
[2]: https://developers.openai.com/api/docs/guides/agents "OpenAI Agents SDK documentation"
[3]: https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md "DeepSeek Harness Architecture"
