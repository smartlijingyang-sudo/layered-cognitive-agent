# ADR-0066：声明式原子控制插件——认知闭集内的可组合治理

## 状态

**Proposed — 2026-08-21**

Amends: [ADR-0033](0033-declarative-agent-spec.md)、[ADR-0056](0056-plugin-group-contribution.md)、[ADR-0061](0061-plugin-manifest-resolve-boot.md)

Keeps: [ADR-0001](0001-five-layer-separation.md)、[ADR-0004](0004-protocol-first-pluggability.md)、[ADR-0005](0005-composition-root-l4.md)、[ADR-0037](0037-journal-as-truth.md)、[ADR-0065](0065-recoverable-evidence-ledger.md)

> **核心决策：LCA 采用“认知闭集 + 声明式原子控制插件”的双层架构。所有可变化、可独立启停、可独立授权、可独立审计的 harness 行为——包括 prestep、预算、授权、约束、停止、降级、审批、重试与观察——必须以最小插件或插件组贡献的形式声明并组合；六步认知循环、类型契约、Reducer 单写状态、Journal 提交边界与执行窄门仍是不可由配置改写的宪法。**

## 背景

DeepSeek Harness（DSH）所代表的“一切皆插件”并不主要是一句“所有功能都放进插件目录”的工程口号。它的本质是将运行时能力、生命周期、服务提供、依赖注入、事件订阅和配置覆盖统一放入可装卸的插件图中：使用者通过装载、卸载或替换插件改变系统行为，而不是修改中心框架。其优点是**扩展自由、生态可生长、局部替换成本低**；代价是事件与上下文注入面如果过宽，编排逻辑会在插件、默认装载和 hook 之间分散，读者无法只通过配置判断一个决策究竟在哪里发生。[1]

LCA 已经具备比“模块可加载”更强的基础。现有 `PluginDefinition` 已包含稳定 ID、配置、`provides`、`requires`、实现契约、层级、种类、效果类别、测试套件和描述；审计上下文会拒绝未声明的 capability 交互。[2] ADR-0061 已将 profile 建模为可解析、可验证的 capability DAG，并将 Resolve、Boot、Run 和 Dispose 分开。[3] ADR-0056 已规定群服务负责收集同类投稿、L4 负责闭合对象图，避免组合根点名具体传感器或 gate。[4]

然而，当前对象图仍保留若干组合根硬编码。以 `spawn_agent()` 为例，它直接选择 `simple` hooks、`simple` body、`default` stop rule，直接构造工具注册表、安全执行器、行动目录与运行时依赖；这些选择即使使用 capability 工厂，仍主要藏在 Python 编排代码里。[5] 这意味着 Profile 能说明“启动了哪些插件”，却不能完整说明“本次决策在哪些控制点受到哪些策略、授权和预算约束”。

认知原语宪章已经给出正确方向：原语、策略和群必须分层；每个原语默认 no-op；预算、审批、约束与停止属于既有原语群内的可替换策略，而不是新增循环阶段或任意 `pre_*` hook。[6] 本 ADR 将这条方向收敛为可执行的声明式控制模型，使“读取 plugin 声明与配置即可理解逻辑脉络”成为受验证的工程属性，而不是仅依靠命名约定。

| 目标 | 本 ADR 的回应 |
|---|---|
| 逻辑可读 | Profile、插件 Manifest 与组合图共同成为控制逻辑的唯一装箱单。 |
| 最小粒度 | 一个插件只表达一个可验证的变化轴或一个明确的群投稿。 |
| 自主组合 | prestep、预算、授权、约束、停止和审批可独立启停、替换、排序与审计。 |
| 安全不退化 | 不以“插件化”为名开放任意状态改写、任意 hook 或任意世界副作用。 |
| 不造平行架构 | 扩展现有 `@plugin` Manifest、Profile、Capability DAG 与群服务，不新建第二套插件 schema 或工作流引擎。 |

## 决策

### 一、采纳“受宪法约束的一切插件”，而非“任意代码都可成为 hook”

本 ADR **接受**用户所追求的方向：Harness 中一切具有独立变化价值的行为都应可声明、可配置、可组合、可替换、可审计。这里的“一切”不是把每一个方法、字段或 `if` 分离为一个插件；它是一个明确的架构判据：若一项行为具有独立的启停、授权、预算、顺序、审计、故障处理或版本演进需求，它就必须从中心编排中抽出，成为原子插件、策略插件或受群服务收集的投稿。

同时，本 ADR **拒绝**把可替换性扩大到认知宪法。六步循环的阶段集合、阶段输入输出类型、Reducer 的状态写入权、Journal 的提交协议、Capability 衰减、执行窄门和 L4 组合闭合是系统可信边界，不是 YAML 的自由变量。配置可以决定“本阶段有哪些策略、其顺序与参数为何”，不能决定“是否绕过阶段、直接改状态、直接执行世界副作用或吞掉审计记录”。

| 层次 | 是否插件化 | 例子 | 是否可由 Profile 改写 |
|---|---:|---|---:|
| 宪法 / 协议闭集 | 否 | 六步循环、`Decision` / `Observation` 类型、Reducer 单写状态、Journal 提交先于投影 | 否；变更必须经 ADR。 |
| 原语实现 | 是 | `PerceiveHub`、`Brain`、`Body`、`Memory`、`StopRule` 的 Null 或标准实现 | 是；通过 capability 替换。 |
| 原语内控制策略 | 是 | budget checker、授权规则、约束规则、审批策略、循环检测、重试规则 | 是；向类型化 control slot 投稿。 |
| 观察与投影 | 是 | 诊断、指标、轨迹图、告警、UI 投影 | 是；只能读取已提交事实。 |
| 任务实例数据 | 否 | 用户请求、授权决定、实际余额、工具结果 | 否；作为 Journal 事实与运行时输入。 |

> **判定原则：先问“它改变哪个既有原语或控制槽位”，再问“它是否是一个可独立演进的策略”。无法回答前一个问题的插件，不得以便利名义进入运行时。**

### 二、将控制逻辑表达为有限、类型化的 Control Slot，而不是无限 hook 名称

`prestep` 不是新的认知原语，也不是允许任意插件改写一切的万能切口。它应先被归属到一个已有的控制槽位；其输入、输出、可写对象、冲突规则和失败语义必须由该槽位固定。这样既保留 DSH 的细粒度可扩展性，也避免“谁监听了哪个事件、谁在何处改了对象”的 hook soup。

首期控制槽位如下。它们是**有限枚举**，新增槽位需要 ADR 或对相应原语协议的审查；插件只能向现有槽位投稿，不能以字符串临时发明 `agent.before_everything`。

| Control Slot | 所属原语 / 阶段 | 允许输入 | 标准输出 | 禁止事项 | 典型原子插件 |
|---|---|---|---|---|---|
| `perceive.context` | Perceive | `StateView`、Journal cursor、任务契约 | `ContextContribution` | 直接改 State、读未授权世界 | clock、workspace 指令、证据检索、上下文预算器。 |
| `think.guard` | Think / Gate | `StateView`、候选 `Decision`、已提交 `PolicyFact` | `DecisionVerdict`、`PolicyFact` | 调用工具、直接改 Decision / State | action constraint、循环检测、模型路由守卫。 |
| `act.authorize` | Act / Execution Control | `ExecutionEnvelope`、grant、风险级别 | `AuthorizationVerdict` | 执行副作用、读取未声明秘密 | capability grant、HIL 审批、域名 / 文件路径许可。 |
| `act.budget` | Act / Execution Control | `ExecutionEnvelope`、预算快照、价格引用 | `BudgetVerdict` | 修改余额、静默超支 | token / 金额 / 时间 / 调用次数检查。 |
| `act.constrain` | Act / Execution Control | `ExecutionEnvelope`、策略事实 | `ConstraintVerdict` 或受限 envelope | 绕过授权 / 审计 | 幂等、速率、租约、文件范围、数据分类。 |
| `act.execute` | Body / SafeExecutor | 已授权、已约束的 envelope | `Observation` | 回写认知状态 | sandbox、HTTP、工具、设备、A2A transport。 |
| `remember.admit` | Memory | 候选 `WriteSet`、分类与保留策略 | `MemoryVerdict` | 直接写持久存储 | 去重、隐私过滤、记忆预算、保留策略。 |
| `stop.decide` | Stop | `StateView`、预算、终态事实 | `StopVerdict` | 修改 State、吞掉失败 | step / 时间 / 成本上限、完成度、人工终止。 |
| `observe.*` | 各原语的观察口 | 已提交事件或不可变快照 | 无业务返回值 | 修改 State、Decision、envelope 或 Journal 历史 | metrics、debug trace、告警、可视化。 |

控制槽位以**返回类型和聚合器**定义，而不以“调用前后”定义。例如，授权、预算和约束可分别产生 verdict，由固定的 `ExecutionControl` 聚合器以 fail-closed 规则折叠；插件不会因为排序靠前就获得直接执行权。Think/Gate 中的规则产生 `PolicyFact` 与 `DecisionVerdict`，由 Journal 记录后才进入下一轮 Perceive；它们不再向 `working_memory` 塞入无来源警告。[6]

### 三、每个控制插件必须是“声明 + 纯评估或受限执行 + 证据”的三件套

控制插件在既有 `PluginDefinition` 上增加**派生的控制声明**，而不是另造 `PrimitiveManifest`。代码仍然是实现策略的地方；配置只表达组装与参数，不能嵌入 JS、Python 或模板形式的任意可执行编排。Manifest 与 YAML 的合并投影必须足以回答：它属于哪个槽位、何时激活、需要什么事实与 capability、可能产生什么 verdict / effect、与同槽位插件如何排序，以及失败时怎样处理。

```yaml
# 示例：一个可独立启停的工具调用预算检查器
id: control.budget.tool-calls
$module: lca.plugins.control.budget_tool_calls
config:
  limit: 40
  scope: run
control:
  slot: act.budget
  activation:
    all:
      - fact: task.action_type
        in: [USE_TOOL, DELEGATE]
  order: 100
  aggregate: deny_on_any_deny
  failure_mode: deny
  reads: [task.contract, budget.snapshot, execution.envelope]
  emits: [policy.budget.checked, policy.budget.denied]
  authority: [budget.read]
  effect_boundary: none
```

`activation` 是一个小型、总是可判定的数据 DSL，只允许对已登记事实做布尔组合、等值、集合、数值比较和存在性判断。它不得读取环境变量、执行表达式、调用网络或反射对象。需要复杂策略时，复杂性留在插件实现内部，而该实现仍必须通过输入、输出、effects 和测试套件声明自己的边界。

| Manifest / 配置字段 | 目的 | Resolve 可验证性 | Run 可验证性 |
|---|---|---:|---:|
| `id`、`$module`、`Config`、`description` | 身份与可读性 | 唯一、模块一致、配置严格 | 输出诊断与审计。 |
| `provides`、`requires`、`implements` | capability 图 | DAG、单例、层级与交互声明 | 审计实际交互。 |
| `control.slot` | 归属到有限控制面 | 槽位存在、插件种类兼容 | 只接收该槽位类型输入。 |
| `activation` | 声明式启用条件 | DSL schema、事实注册、无自由代码 | 对冻结事实求值并记录结果。 |
| `order`、`aggregate` | 同槽位组合语义 | 值域、并列稳定性、聚合器兼容 | 按确定性顺序折叠。 |
| `failure_mode` | 失败治理 | 只允许槽位规定的模式 | `deny` / `stop` / `degrade` 必须生成事实。 |
| `authority`、`effects` | 权限与副作用 | grant 可满足，effect 与槽位相容 | 通过执行窄门再次强制。 |
| `reads`、`emits` | 事实依赖与可观测性 | descriptor / policy fact 已登记 | 记录输入版本、激活与 verdict。 |

### 四、排序、冲突与失败语义由槽位拥有；插件不拥有流程控制权

插件组合最容易退化的地方，是将“按 YAML 顺序执行一串钩子”误认为声明式。YAML 文本顺序只能是无依赖条目的稳定并列顺序，不能承载隐藏优先级、短路行为或安全语义。Control Slot 必须显式拥有聚合器；同一类插件必须共享可预测的单调规则。

| Verdict 类别 | 默认聚合 | 语义 | 可否被后续插件推翻 |
|---|---|---|---:|
| `AuthorizationVerdict` | `deny_on_any_deny` | 任一拒绝即不进入执行窄门。 | 否；只能经新的、已审计的授权事实重新评估。 |
| `BudgetVerdict` | `deny_on_exhausted` | 不足时拒绝或产生已定义的降级请求。 | 否；余额更新必须来自受控账本事实。 |
| `ConstraintVerdict` | `deny_on_any_deny`，`rewrite` 必须可证明收紧 | 约束只能保持或缩小 envelope 权限。 | 不可扩大 scope。 |
| `DecisionVerdict` | `stop > ask_human > rewrite > allow` | Think 中的确定性治理优先于候选决策。 | 仅按格结构向更保守结果演进。 |
| `StopVerdict` | `stop_on_any_stop` | 任一硬终止条件结束循环。 | 否；续跑需新的 run / resume 事实。 |
| `Observation` | 不聚合业务控制 | 观察口只投影，不改写控制结果。 | 不适用。 |

任何 `rewrite` 必须保留 `degraded_from`、原始因果引用和所适用的策略 ID；任何 `deny`、`ask_human`、`stop` 与 `degrade` 必须提交可检索的 Journal 事实。由此，授权为什么发生、预算在哪一项耗尽、哪个约束停止了执行，都能从 profile 与 run 账本共同解释，而不需要阅读散落的条件判断。

### 五、组合单位是“原子插件 + 群服务 + 复合 Bundle”，不是巨型万能插件

一个原子插件的责任必须可以写成一句话，并拥有单一槽位、单一主要 verdict / contribution 类型和一组最小 capability。`prestep`、预算检查、文件路径约束、是否需授权、何时停止都符合这一条件，应该单独实现并由 Bundle 或 Profile 组合。多个原子插件可以构成一个领域 Bundle，例如 `safe-code-execution`，但 Bundle 只是声明性装箱单，不应重新实现控制流。

下例展示目标阅读体验。一个 reviewer 不打开任何 Python 实现，也能看到对“高风险网络工具调用”的完整治理脉络：先适用工具权限，再做调用次数预算、网络域名约束和人工审批，全部通过后才允许执行。

```yaml
# bundles/safe-network-tool-call.yaml
plugins:
  - control.authorize.capability-grant
  - control.budget.tool-calls
  - control.constraint.network-egress
  - control.authorize.high-risk-approval
  - executor.network-tool

patch:
  - id: control.authorize.capability-grant
    config:
      required_grant: tool.network
  - id: control.budget.tool-calls
    config:
      limit: 20
  - id: control.constraint.network-egress
    config:
      allow_domains: [api.github.com, docs.python.org]
  - id: control.authorize.high-risk-approval
    config:
      risk_at_or_above: high
      approval_scope: invocation
```

群服务仍是收集与组装的唯一入口。`act.authorize`、`act.budget` 与 `act.constrain` 的插件向相应 ExecutionControl registry 投稿；运行时从 registry 得到已排序的不可变 pipeline。L4 只请求 `execution_control_factory` / `body_factory` 等领域 capability，而不得重新点名 `control.authorize.*` 或在 `spawn_agent()` 内写 `if risk >= ...`。这延续 ADR-0056 的“群服务投稿、L4 闭合”边界。[4]

### 六、Profile 是人类可读的控制叙事；解析图是机器可验证的执行叙事

Profile 不必、也不应暴露每一个底层 provider；它应呈现用户和审阅者关心的行为切面。Bundle 负责复用安全基线，Patch 负责参数化，TaskContract / capability grant 负责本次运行的具体事实。Resolve 输出必须生成一个可导出的 `ControlPlan`，与现有 capability DAG 并列：它不是新运行时，而是现有 `ResolvedProfile` 的检查视图。

```text
Profile / Bundle / Patch
          │
          ▼
Resolve：插件 Manifest DAG + Control Slot 校验 + grant / effect 校验
          │
          ├── capability graph（谁提供 / 依赖什么）
          └── ControlPlan（每槽位有哪些投稿、何时激活、怎样折叠）
          │
          ▼
Boot：构造群服务与注册表；注册原子插件；禁止业务 fallback
          │
          ▼
Run：对冻结的事实求 activation；产生 verdict；经 Journal / 执行窄门
          │
          ▼
Inspect：profile / graph / why / explain-control / run evidence
```

`ControlPlan` 至少应支持 `inspect-tree`、`dump-profile`、`graph` 与新增的 `explain-control <slot>`。对每个 Control Slot，工具输出必须展示插件 ID、来源 Bundle / Patch、顺序、激活条件、所需 grant、effect class、聚合规则与测试套件。运行期还应能将某次 verdict 映射回计划项、解析来源和 Journal 证据。

### 七、权限、预算、约束、审批和停止是可组合策略，但其事实与强制点不可插件化绕过

授权、预算、约束、审批和停止都应是插件，因为它们需要因环境、租户、任务、工具或产品策略而变化。但是它们不是普通“建议器”：每一项都必须有一个唯一的事实 owner 与强制边界。

| 关切 | 策略插件负责 | 事实 owner | 最终强制点 |
|---|---|---|---|
| 授权 | 基于 grant、风险与任务契约提出 allow / deny / ask-human | 授权决定与 grant 的 Journal 事实 | `act.authorize` 聚合器与执行窄门。 |
| 预算 | 评估调用、时间、token、成本或并发余量 | 版本化预算快照与价格引用 | `act.budget`、`stop.decide`；不得由本地计数器越权扣减。 |
| 约束 | 收紧 envelope 的工具、参数、域、路径、数据分类或租约 | TaskContract、策略事实与 envelope 因果 | `act.constrain`；只允许等价或更小权限。 |
| 审批 | 按风险产生可恢复的 `ask_human` / pending | Approval Requested / Resolved 事实 | 调用前的 authorize slot；恢复后重新评估。 |
| 停止 | 根据确定性条件提出 stop / continue | run 账本、状态视图、预算事实 | `stop.decide`；终态经 reducer / ledger 封存。 |

这一区分防止两种常见错误。第一种是将预算与授权硬编码在 Composer，使替换不可见；第二种是让任意插件自己扣减预算、弹出审批或直接调用工具，使系统失去唯一事实源和可恢复性。前者牺牲扩展性，后者牺牲可信性；本 ADR 要求策略可替换、事实与强制点唯一。

## 后果

| 维度 | 正面后果 | 成本与约束 |
|---|---|---|
| 可读性 | Profile + `ControlPlan` 可展示完整治理脉络，配置成为架构阅读入口。 | 每个新增策略都必须写清所属槽位和聚合语义。 |
| 独立性 | 预算、授权、停止、审批、约束与观察可各自替换，不再依附于中心 `if`。 | 插件数量上升，需要严格命名、目录、测试与文档治理。 |
| 安全性 | deny、预算、授权和约束以 fail-closed 单调聚合，无法靠插件顺序绕过。 | 灵活的“后一个插件允许前一个拒绝”模式被禁止。 |
| 可观测性 | 每次激活、verdict、重写、拒绝和停止都能关联 Manifest、Profile 来源与 Journal 证据。 | 需要为 control plan 和 policy 事实新增 descriptor、查询与可视化。 |
| 性能 | Resolve / Boot 期完成大部分静态校验；Run 期只评估已编译计划。 | activation DSL 和 verdict 聚合器需要缓存、基准测试与明确的热路径预算。 |
| 演进 | 原语协议稳定，策略可快速增加；闭集变化仍受 ADR 保护。 | “新增一个方便的万能 pre-hook”将被明确拒绝，短期开发感受会更受约束。 |

## 验证约束

| 编号 | 约束 | 必须具备的自动化证据 |
|---|---|---|
| **C1** | 插件有且仅有一个合法 control slot 或明确标注为非控制 seam / provider / observer。 | Manifest schema / architecture test 拒绝未知、跨阶段和多主槽位投稿。 |
| **C2** | 控制行为完整可见。 | `dump-profile` 与 `explain-control` 输出每个 slot 的插件、来源、顺序、条件、grant、effects 与聚合器。 |
| **C3** | 配置不可执行。 | Resolve 拒绝 `eval`、表达式字符串、未登记事实路径、环境变量读取与未定义 DSL 操作符。 |
| **C4** | 静态与动态边界分离。 | Resolve 覆盖 DAG / layer / effect / grant / order；Run 测试覆盖同一 ControlPlan 在不同事实快照下的 activation。 |
| **C5** | 拒绝不可被后续策略放宽。 | property test 证明 deny-on-any-deny、stop-on-any-stop 与 scope 收紧的单调性。 |
| **C6** | 所有控制结果有可恢复证据。 | deny、rewrite、ask-human、degrade、stop 与 budget exhaustion 均提交带 `plugin_id` / `control_slot` / `plan_ref` 的已登记 Journal 事件。 |
| **C7** | 组合根不再拥有策略名单。 | `spawn.py`、runtime 与 gateway 的 architecture test 禁止直接实例化控制策略、固定插件 ID 或风险 / 预算业务分支。 |
| **C8** | 观察口无控制旁路。 | observer 仅接收不可变快照；任何 State、Decision、envelope 或 ledger append 写入尝试均失败。 |
| **C9** | 权限不扩大。 | 子代理和 rewrite 后 envelope 的 grant / scope 必为父级子集；违反时 Resolve 或 Run fail-closed。 |

## 实施序列

本 ADR 只定义目标边界；迁移必须分段进行，避免把“声明式化”变成一次大爆炸重写。每个 PR 都应可独立合并、具备架构测试，并在切换前保留一个短期兼容适配层；兼容层本身必须有删除期限。完整的插件群目录、原子插件家族、预留扩展位、契约矩阵与长期治理路线见《[声明式插件宪法 v4.0](../design/2026-08-21-declarative-plugin-constitution-v4.md)》。

| PR | 标题 | 主要结果 | 验证锚点 |
|---|---|---|---|
| **PR-1** | ADR 与术语冻结 | 通过本 ADR，补充 glossary：Control Slot、ControlPlan、Verdict、activation DSL。 | 文档链接与 ADR 索引。 |
| **PR-2** | 扩展现有 Plugin Manifest | 在 `PluginDefinition.meta` 增加可选 `control` 声明、严格 Pydantic schema 和 diagnostics；不新建第二插件 schema。 | C1、C3。 |
| **PR-3** | ControlPlan Resolver | 将已解析 profile 投影为不可变 `ControlPlan`，校验 slot、order、aggregate、effects、grant 与 activation 引用。 | C2、C4、C5、C9。 |
| **PR-4** | Gate 与 Stop 原子化 | 先迁移 loop breaker、step / wall-clock stop、决策约束为 `think.guard` / `stop.decide` 投稿，删除 `working_memory` 旁路。 | C5、C6。 |
| **PR-5** | Execution Control 原子化 | 建立 authorize、budget、constrain、execute 四个受限 registry；迁移工具权限、审批、幂等、文件 / 网络范围。 | C5、C6、C9。 |
| **PR-6** | L4 组合根瘦身 | `spawn_agent()` 改为请求领域 factory 与已编译 plan，移除直接选择 `simple` / `default` 和控制策略实例化。 | C7。 |
| **PR-7** | 观察与解释面 | 生成 `explain-control`、control graph、计划来源追踪与 run verdict 回链。 | C2、C6、C8。 |
| **PR-8** | 基线与场景 Bundle | 形成 `null-baseline`、`safe-tooling`、`coding-agent`、`human-in-the-loop`、`long-running` 等可读 Bundle，并以 golden profile 测试锁定行为。 | C2、C4。 |
| **PR-9** | 删除兼容路径 | 删除 legacy hook、组合根 fallback 与未声明的控制支路；只保留 Manifest + ControlPlan + 群服务入口。 | C1–C9 全量。 |

### 迁移优先级

首先迁移**已经影响安全、成本、恢复或可解释性的硬编码**，而不是先追求目录的视觉整齐。优先序为：执行授权与审批、预算与停止、外部副作用约束、Gate / loop intervention、上下文预算、可观察投影。低风险的格式化、UI 便利功能和纯 provider 可在核心 slot 稳定后再拆分。

### 明确不做

| 不做项 | 原因 |
|---|---|
| 用 YAML / JSON 写任意 Python、JS 或图灵完备流程 | 这会把中心硬编码转移为不可审计的配置硬编码，并破坏 Resolve 的静态验证。 |
| 增加无限制 `before_*` / `after_*` / `prestep` 事件 | 这会重演 hook soup，不能从 profile 推导控制语义。 |
| 让插件直接写 `AgentState`、`working_memory` 或其他 Agent 私有状态 | 保持 Reducer 单写 State 与 Journal-as-Truth。 |
| 让授权 / 预算插件直接执行世界副作用或扣减不可恢复余额 | 保持事实 owner、审计与执行窄门唯一。 |
| 把每个微小函数都拆为单独插件 | 插件边界按独立变化轴和控制语义确定，不按代码行数确定。 |
| 新建独立工作流 / 图引擎来承载控制插件 | 先扩展现有 Profile、Capability DAG、群服务和既有认知闭集。 |
| 以默认 fallback 掩盖缺失策略 | 缺失安全策略必须在 Resolve / Boot fail-fast；安全默认只能由显式 `null` / baseline 声明表达。 |

## 替代方案

| 方案 | 结论 | 原因 |
|---|---|---|
| 保持中心 Composer / Runtime 硬编码，只为工具提供插件 | 否决 | 授权、预算、停止和约束仍不可独立治理，配置不能解释真实逻辑。 |
| 采用 DSH 式自由事件 hook 作为唯一扩展面 | 否决 | 扩展速度快，但控制归属、冲突和状态写入难以静态证明，易形成隐式编排。 |
| 将每个策略升级为新认知原语 / 新循环阶段 | 否决 | 预算、审批与停止是既有群内策略；会膨胀闭集并稀释认知模型。 |
| 仅使用声明式工作流图替代 Agent loop | 否决 | 图适合特定流程 / Team 拓扑，不应替代默认的认知闭集。 |
| 保持大而全的 `safety-plugin` / `prestep-plugin` | 否决 | 多个变化轴被捆绑，无法独立授权、替换、测试与解释。 |
| 本 ADR 的有限 Control Slot + 原子插件 + 群服务 | 采纳 | 在可扩展性、可读性、安全性和可验证性之间维持清晰边界。 |

## 参考

[1]: ../research/deepseek-harness-plugin-analysis.md "仓库内 DeepSeek Harness 插件机制分析"
[2]: ../../lca/harness/plugin_api.py "当前 PluginDefinition、PluginContext 与 Manifest 审计实现"
[3]: 0061-plugin-manifest-resolve-boot.md "ADR-0061：声明式插件 Manifest —— Resolve/Boot 与依赖图"
[4]: 0056-plugin-group-contribution.md "ADR-0056：群服务投稿 —— 签名即依赖，配置即装箱单"
[5]: ../../lca/application/spawn.py "当前 L4 spawn 组合根"
[6]: ../design/2026-08-19-cognitive-primitive-constitution-v3.md "认知原语插件宪法 v3.0"
[7]: 0065-recoverable-evidence-ledger.md "ADR-0065：可恢复的证据保真运行账本"
