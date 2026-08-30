# ADR-0089：可组合的声明式阶段观察

## 状态

**Accepted — 2026-08-27**

## 背景

ADR-0088 已让 Profile 通过 `runtime_factory` 选择完整 Agent Loop，并让生产运行时从不可变 `DeclarativeRuntimeBindings` 获取显式闭包。循环事务仍只允许通过 Journal、Effect Gateway 和 Delta Reducer 记录事实、执行副作用和改变状态。

此前 `phase_observer` 是单值 capability，`TracingPhaseObserver` 直接作为唯一 provider 绑定。新增诊断、评测、合规计时或其他被动观测时，只能替换既有 provider 或将逻辑侵入 `PhaseExecutionTransaction`，两种方式都不能表达多个独立观察能力的有序组合。

## 决策

新增单值 seam `phase_observer_registry`。该 seam 仅承载 `PhaseObserverContribution` 的启动期注册；每个 contribution 包含稳定 ID、显式优先级和只读 `PhaseObserver`。重复 ID 使 profile boot 失败，registry 的 `snapshot()` 按 `(priority, id)` 返回确定性顺序。

`lca-phase-observer-provider` 保持为唯一 `phase_observer` capability provider，但由 primitive 变为 composite provider。它从 registry 取得一次冻结快照并构造 `CompositePhaseObserver`，因此运行时 binding 仍只拥有一个不可变、可审计的 `PhaseObserver`，无需扩大 `DeclarativeRuntimeBindings` 或 transaction 的依赖表面。

观察器接口接收 `PhaseStateSnapshot`，而非 live `AgentState`。该快照只复制 trace ID、角色、step、任务状态和不可变 budget 标量，刻意排除 task、working memory、artifacts、turn history、checkpoint、output、error、skills、team awareness 与任意 reducer/effect/journal 引用。这样“只读”不仅是约定，也由插件可见的类型表面和冻结对象共同约束。

默认 tracing 行为由独立的 `lca-phase-observer-tracing-provider` 贡献。Profile 可以省略、替换或增加观察贡献插件，而不必改动 runtime、phase executor、Journal、Reducer 或 Gateway。

| 边界 | 所有者 | 不允许承担的职责 |
|---|---|---|
| `phase_observer_registry` | L2 seam plugin | 不内置默认 observer，不在运行期更改 transaction 或 State |
| observer contribution provider | 独立 L2 provider plugin | 不直接提供 `phase_observer`，不访问 effect、reducer、journal 或可写 state |
| `PhaseStateSnapshot` | contracts 纯数据类型 | 不暴露 live `AgentState`、task、memory、artifact 或控制依赖 |
| `CompositePhaseObserver` | L2 composite provider | 不改写 observer 输入，不吞掉 executor 错误，不生成运行事实 |
| `PhaseExecutionTransaction` | 最小可信内核 | 不选择或实例化具体 observer，不隐式回退默认 observer |
| Profile / Bundle | 组合根 | 选择 observer 集合和明确故障策略 |

## 故障语义

观察故障策略由 composite provider 的 `failure_mode` 配置为 `fail_open` 或 `fail_closed`。

* `fail_open` 是默认值。observer 的构造、进入或退出失败仅写结构化运维日志，phase executor 与其原始异常语义不受影响。
* `fail_closed` 以包含 contribution ID 和阶段操作的 `PhaseObserverError` 中止执行，供将观测本身视作合规前置条件的严格 Profile 使用。

无论何种策略，observer 都不能通过 context manager 的返回值压制 executor 抛出的异常。该规则避免被动观测成为隐藏的控制 hook。

## 后果

该决策让 tracing、性能评测、审计计量和调试观察等能力可按插件贡献、按 Profile 组合，同时保持 `phase_observer` 的单值 production closure 与 ADR-0075 的最小可信内核。观察面因此获得可扩展性，但认知闭集、单写 Reducer、Journal-as-Truth 与 Effect Gateway 的控制边界不变。

替代方案如下。

| 方案 | 否决原因 |
|---|---|
| 每个 observer 直接提供 `phase_observer` | 单值 capability 的竞争会使启动顺序成为行为选择器，无法形成明确组合。 |
| 在 `PhaseExecutionTransaction` 内写死多个 observer | 重新把可替换观测逻辑耦合进可信内核。 |
| 将 observer 改成可写 waterfall middleware | 会引入 State/Decision 控制旁路，违背双平面与 Reducer 单写纪律。 |
| 继续保留单一 tracing provider | 无法以 Profile 叠加评测、审计和诊断能力，也无法显式表达故障策略。 |

## 验证约束

- registry 必须拒绝重复 contribution ID，并输出稳定有序快照。
- composite 必须在创建时冻结 observer 集合，运行中不从 ambient context 重新解析。
- 默认 `fail_open` 不得中断 executor；`fail_closed` 必须带 attribution 地失败。
- observer 不得吞掉或替换 executor 的原始异常。
- observer 只能接收冻结的 `PhaseStateSnapshot`；测试必须证明快照与 live state/budget 脱钩，且不泄露 working memory 等可写或敏感字段。
- 默认 base bundle 必须显式装配 registry、tracing contribution 与 composite provider。
- `runtime_assembly` 必须验证 `RuntimeFactory.create()` 返回 `Runtime` Protocol，错误 provider 在组合期失败。
