# ADR-0067：时空运行时与受治理的动态创造

## 状态

**Proposed — 2026-08-21**

Amends: [ADR-0066](0066-declarative-atomic-control-plugins.md)

Keeps: [ADR-0001](0001-five-layer-separation.md)、[ADR-0004](0004-protocol-first-pluggability.md)、[ADR-0005](0005-composition-root-l4.md)、[ADR-0037](0037-journal-as-truth.md)、[ADR-0056](0056-plugin-group-contribution.md)、[ADR-0061](0061-plugin-manifest-resolve-boot.md)、[ADR-0065](0065-recoverable-evidence-ledger.md)

> **核心决策：LCA 将“时间”和“空间”提升为显式、可溯源的运行时事实与资源边界，并采纳受治理的动态创造模式。动态代码只能先成为可检查的候选工件，在隔离实验空间中经历解析、验证、试运行和审查；只有经过显式提升，才可进入 run、agent、profile 或发布 scope。动态能力永远不能绕过认知闭集、Control Slot、Capability 衰减、执行窄门或 Journal 账本。**

## 背景

DeepSeek Harness（DSH）提供了值得吸收的三类能力。第一，Cordis 以稳定配置条目、依赖驱动装载、Fiber 生命周期、effect 自动清理和 HMR 支持运行时插件组合与替换。[1] [2] 第二，DSH 以 opt-in 的 durable time context 将当前带时区时间、请求来源时区与模型可见消息间隔写入模型上下文；其设计强调浏览器时区来源、混合来源时要求澄清，以及时间信息只是自然语言解释而不替代工具参数的显式时区。[3] 第三，Creator 动态工具把 `inspect`、`define`、`run`、`stop`、`undefine` 分离，使 Agent 能够检查 live runtime、在内存中试验候选包，并在明确生命周期内撤销它们。[4] [5]

这些能力与 LCA 的目标高度一致：系统不应只有静态 Profile，也应能感知其所在世界、在受控边界内创建新能力、观察新能力的效果并把成熟成果沉淀为可复用插件。然而，DSH 的动态包模型是为实验速度优化的：动态包可以使用动态 `ctx` façade，定义和活动状态仅在进程内存中存在，VM 隔离不是安全边界，异步 host-half 可超出同步 VM 超时，带 browser half 的 run 在没有页面响应时会挂起且没有独立超时。[4] [5] DSH 的 HMR 还允许缺 provider 的插件合法保持 `PENDING`，使“为何没有生效”需要额外诊断。[1] [2]

LCA 已有比自由动态装载更严格的基础：插件 Manifest / Resolve / Boot 依赖图、受审计 capability interaction、Control Slot、Journal 证据账本、grant 衰减，以及现成的 `Composer.mount/unmount/inspect` 契约。现有 Composition 契约已经要求挂载前校验 Manifest、grant 子集和 invariant，并对成功和拒绝均记录事实。[6] 因此本 ADR 不引入第二套动态 runtime；它把现有 Creator 能力演进为可恢复、可验证、对开发者更友好的**动态能力交付管线**。

| 决策驱动 | 本 ADR 的回应 |
|---|---|
| 时间解释正确性 | 让时间、时区、采样时刻、有效期、单调序列与不确定性成为类型化事实。 |
| 空间边界正确性 | 让工作区、执行环境、会话、租户、Agent、设备、浏览器、插件 realm 与资源 scope 成为显式边界。 |
| 创造模式 | 将“写代码后直接 mount”替换为候选工件的验证、实验、提升和可回滚发布。 |
| 开发体验 | 以 typed manifest、scaffold、诊断、diff、模拟、golden trace 和稳定 logical ID 取代自由 `ctx` / 路径 / 静默 PENDING。 |
| 安全与恢复 | 实验不自动进入生产能力图；副作用、权限、证据、发布与 rollback 均经过固定 gate。 |

## 决策

### 一、时间与空间是运行时的一等事实，不是 Prompt 字符串或全局变量

LCA 定义 `SpacetimeContext` 为某次运行、某个 Agent、某个 turn 和某个操作可合法使用的**时空事实快照**。它由多个有明确 owner 的子对象组成，且每个子对象可被 Journal 引用。`SpacetimeContext` 不直接等同于 `AgentState`，不允许任意插件修改；它是 Perceive / ExecutionControl 所消费的不可变 view。

```text
SpacetimeContext
├── TemporalContext       # 何时：事实时间、来源、时区、单调顺序、有效性
├── ExecutionSpace        # 在哪执行：环境、workspace、设备、网络与能力
├── IdentitySpace         # 为谁执行：tenant、principal、role、agent、session
├── VisibilitySpace       # 谁可见：audience、classification、ACL、memory scope
└── LifecycleSpace        # 活多久：process/profile/agent/run/turn/invocation/experiment
```

| 子空间 | 唯一 owner | 关键字段 | 可被谁读取 | 不可被谁伪造 |
|---|---|---|---|---|
| `TemporalContext` | G2 Perceive + G8 Journal | `observed_at`、`source_time_zone`、`offset`、`elapsed`、`uncertainty`、`valid_until`、`run_seq` | Perceive、Think、Gate、Stop、ExecutionControl | Reasoner、Tool、observer。 |
| `ExecutionSpace` | G11 provider / G5 execution | `space_id`、backend、workspace、outputs、device、network policy、capabilities | Act、受限 Perceive | Think 直接读机器、动态插件自报权限。 |
| `IdentitySpace` | authenticated principal / TaskContract | tenant、user、role、agent、session、delegation chain | 所有 enforcement point | 子代理、普通插件。 |
| `VisibilitySpace` | G8 policy / G7 ACL | audience、classification、retention、memory visibility | Perceive、Memory、Observe | renderer、projector 越权外送。 |
| `LifecycleSpace` | G10 Composition | scope、parent scope、lease、expiry、disposal owner | Compose、Journal、inspect | 业务插件延长自身生存期。 |

### 二、时间原语只经 Perceive 与 Journal 进入模型和控制面

时间是 Agent 在现实中行动的必要背景，但不应成为 Reasoner 私自调用 `datetime.now()` 的旁路。`perceive.sensor.temporal-context` 是唯一负责将时钟、来源时区、消息 / 观察间隔和有效期转换为 `TemporalFact` 的原子插件；`perceive.policy.temporal-provenance` 负责来源验证、混合时区和过期处理；`stop.decide.deadline` 与 `act.budget.wall-clock` 只消费该事实及受控 monotonic clock。

| TemporalFact | 语义 | 来源规则 | 不确定时的行为 |
|---|---|---|---|
| `observed_at` | 对外部世界采样的时刻 | 使用可配置可信 clock，并记录 clock source。 | 以 `uncertain` 标记，不伪造精度。 |
| `source_time_zone` | 用户请求所归属的时区 | 必须有 host 验证的 request provenance。 | `mixed` / `unavailable` 时要求澄清。 |
| `elapsed_since_visible` | 模型上一次可见事实到本次准备的间隔 | 基于有序 Journal ref 或 monotonic clock。 | 缺基线时写 `unavailable`。 |
| `valid_until` | 本条时间 / 时间敏感 context 的有效范围 | 由事实 owner 显式给出。 | 到期后不进入 Manifest。 |
| `deadline` | TaskContract 的终止时刻 | 用户 / 系统契约，附时区与来源。 | 无法解析时拒绝 TaskContract。 |
| `logical_time` | run 内确定性因果顺序 | `run_seq` / turn / step，而非 wall clock。 | 永远存在；与 wall time 分离。 |

DSH time context 的“来源时区只能指导自然语言理解、不代替工具显式时区参数”的边界被保留。[3] LCA 的改进是：时间信息不通过 `agent/pre-step` hook 附加，而是作为 PerceiveHub 产生的已登记 `ContextItem` 进入 ContextManifest；其采样、过滤、预算、可见性和模型输入均可由 Journal 重建。

### 三、空间原语以 ExecutionSpace 和 ScopeGraph 明确资源所有权

“空间”不是一条 workspace 路径，也不是把 `ctx` 传得更远。它是操作可被允许、可见、可归因、可撤销的边界。现有 `ExecutionContext` 已给出真实 workspace、backend、outputs、capabilities 与操作后 `env_state` 的正确基础；Agent、前端、工具和附件应共享同一实际 workspace，而每个操作必须显式回传环境状态，避免 `cd` 一类隐式漂移。[7]

`ScopeGraph` 定义动态能力可被放入的有限空间。每一个 scope 都有稳定 ID、父 scope、生命周期、grant 上限、可写资源、可见事实与 disposer owner。不存在“全局动态插件”这一默认选项。

| Scope | 用途 | 默认允许 | 默认禁止 | 最大生命周期 |
|---|---|---|---|---|
| `experiment` | 候选插件的模拟、测试与诊断 | 纯计算、fake provider、fixture evidence | 真工具、真网络、真实记忆写入、其他 session 可见 | 单次实验 lease。 |
| `invocation` | 一次工具调用的临时适配 | envelope 局部转换、收窄约束 | 注册长期 service、跨调用缓存 | Observation 终态。 |
| `turn` | 一轮认知的短暂 contribution | context / prompt / diagnostic | 真实副作用、跨 turn 状态 | turn 结束。 |
| `run` | 当前任务的临时能力 | 已授权 tools、run ledger、approval | 跨 run 可见、自动发布 | terminal + grace disposal。 |
| `agent` | 角色绑定能力 | Brain、Memory、Role renderer | 修改其他 Agent 私有状态 | agent dispose。 |
| `profile` | 已解析场景能力 | immutable plan template、base service | 保存 run 私有事实 | profile dispose。 |
| `release` | 经审查的可复用插件 / bundle | 注册到 catalog、版本化发布 | 自动高权限启用 | 显式 deprecated / retired。 |

空间隔离可借鉴 Cordis group / isolate 的价值：不同实验或 Agent 可有不同 provider 实例与配置，而不互相污染。[1] LCA 对此增加两条硬规则：隔离不是权限提升；任何跨 scope 的引用必须使用稳定 capability handle 或 EvidenceRef，不能携带 live Python object、裸路径或闭包。

### 四、动态能力走“候选工件—实验—提升”状态机，而不是直接 mount

动态代码、配置 Patch 或可组合 preset 首先是 `CapabilityArtifact`，不是 runtime plugin。工件可由人或 Agent 创建，但在尚未通过全部检查前，没有任何能力、effect 或控制贡献。动态生命周期使用以下不可跳跃状态；每一次迁移都追加 Journal 事实，且携带 artifact digest、actor、scope、plan ref 与原因。

```text
DRAFT
  → PARSED
  → DECLARED
  → VERIFIED
  → STAGED
  → ACTIVE
  → QUIESCING
  → RETIRED

任一前置失败：REJECTED
ACTIVE 的逻辑替换：ACTIVE(rev n) → QUIESCING(n) → ACTIVE(n+1)
                              │
                              └──────────────→ ROLLED_BACK
```

| 状态 | 可以做什么 | 必须证明 | 不可做 |
|---|---|---|---|
| `DRAFT` | 保存内容与作者意图。 | 内容摘要与来源。 | import、执行、注册。 |
| `PARSED` | 解析 source / declarative artifact。 | 语法、格式、无未支持语言特性。 | 使用 live `ctx`。 |
| `DECLARED` | 提取 / 生成严格 Manifest。 | group、slot、capability、effect、config、test suite。 | 读取环境秘密、猜测 grant。 |
| `VERIFIED` | 静态检查与 policy evaluation。 | DAG、层级、slot、effects、grant、DSL、descriptor、签名。 | 真实副作用。 |
| `STAGED` | 在 experiment scope 运行。 | isolated tests、golden trace、resource ceiling、disposer。 | 修改真实 run / profile、外发数据。 |
| `ACTIVE` | 在被批准 scope 的已解析 plan 中贡献能力。 | promotion decision、lease、rollback target、evidence policy。 | 越过 scope、自动 durable publish。 |
| `QUIESCING` | 拒绝新调用，等待 / 取消已开始操作。 | drain policy、timeout、inflight list。 | 接受新 work。 |
| `RETIRED` / `ROLLED_BACK` | 保留审计与可重现工件。 | 清理 receipt、替换或撤回因果。 | 继续提供 capability。 |

### 五、动态装载的六道闸

`Composer.mount` 现有的 Manifest、grant 子集和 invariant 三道闸保留。[6] 任何从 `VERIFIED` 晋升 `STAGED` 或从 `STAGED` 晋升 `ACTIVE` 的操作还必须通过下列六道闸；它们是固定 Control Slot，不允许动态插件自定义绕过路径。

| Gate | 负责问题 | 关键输入 | 失败结果 |
|---|---|---|---|
| `creation.identity` | 工件是谁写的、内容是否固定？ | digest、actor、provenance、signature | `REJECTED(identity)`。 |
| `creation.manifest` | 是否属于已知插件群和 slot？ | Manifest、schema、contract version | `REJECTED(manifest)`。 |
| `creation.capability` | 请求能力是否为调用者 grant 的子集？ | caller grant、requested capabilities、effects | `REJECTED(grant)`。 |
| `creation.invariant` | 是否破坏闭集、owner、单调性、层级？ | ControlPlan diff、invariant suite | `REJECTED(invariant)`。 |
| `creation.evidence` | 能否记录全部控制 / effect 事实？ | event descriptor、evidence policy、privacy | `REJECTED(evidence)`。 |
| `creation.experiment` | 是否在隔离 scope 达到预期并能清理？ | fixture、golden trace、leak / disposer report | `REJECTED(experiment)`。 |

只有 `ACTIVE` scope 的运行时调用才经过常规 `act.authorize`、`act.budget`、`act.constrain` 和 `act.execute`；创造 gate 不替代执行 gate。也就是说，成功提升一个网络工具插件不等于每次网络调用自动获准。

### 六、动态替换必须是版本化双轨切换，不是 HMR 覆盖

HMR 是很好的开发反馈工具：稳定 ID、卸载旧 effect、重新执行新实例能极大缩短实验循环。[1] [2] 但生产 Agent 的动态替换必须不丢失因果或半途改变不可重放行为。因此 LCA 区分 **Lab HMR** 和 **Production Promotion**。

| 维度 | Lab HMR | Production Promotion |
|---|---|---|
| 目标 | 开发者快速编辑、重载、调试。 | 在真实 scope 安全替换一个已验证能力。 |
| 空间 | `experiment` scope。 | 指定 run / agent / profile scope。 |
| 输入 | source revision + fixture。 | immutable artifact digest + promotion plan。 |
| 旧版本 | 可立即 dispose。 | 先 `QUIESCING`，drain / cancel inflight，再切换。 |
| 状态迁移 | 默认不迁移；fixture 重建。 | 仅允许显式 `StateMigration` contract；否则新版本从下一安全边界生效。 |
| 副作用 | fake provider / dry-run。 | 常规 ExecutionControl。 |
| 回滚 | 重新 stage 前一 digest。 | 切换回已验证 revision；保留 incident / causal links。 |
| 成功标准 | tests + leak-free disposal。 | gates + trace diff + approval + drain receipt。 |

动态替换以 `logical_id` 与不可变 `revision_digest` 区分身份和版本。没有稳定 logical ID 的编辑不可被当作“更新”；只能被视为新的候选工件，避免 DSH 中无 ID 配置项被识别为 remove-plus-add 所产生的非预期重挂载。[1]

### 七、Creator 是受限的开发平面，而不是 Agent 的全局管理权限

Creator 由一组插件提供，且自身受 Profile 与 TaskContract 约束。它拥有四个面：**inspect、author、validate、promote**。任何界面或工具都只能调用这四个领域服务，而不能拿到裸 `Context`、动态 import 或进程全局 service locator。

| Creator 面 | 用户 / Agent 能做什么 | 输入 | 输出 | 权限下限 |
|---|---|---|---|---|
| `inspect` | 了解 live graph、slot、grant、scope、版本、等待与原因。 | read-only query | `RuntimeTopologyReport` | `creator.inspect`。 |
| `author` | scaffold 原子插件 / bundle / profile patch。 | intent、template、target group | `CapabilityArtifact(DRAFT)` | `creator.author` + workspace write。 |
| `validate` | parse、lint、模拟、运行 fixture、查看 diff。 | artifact digest、test plan | `ValidationReport` | `creator.validate`。 |
| `stage` | 在 experiment space 激活 / reload / stop 工件。 | verified artifact、lease、fixture | `ExperimentReceipt` | `creator.stage`。 |
| `promote` | 将 staged revision 提升至明确 scope。 | artifact、target scope、rollback rev | `PromotionReceipt` | `creator.promote` + target scope grant。 |
| `retire` | quiesce、rollback、deprecate、删除可见性。 | logical id、scope、reason | `RetirementReceipt` | `creator.retire`。 |
| `publish` | 将审批后的 artifact 写为版本化 release bundle。 | approved promotion、release metadata | `ReleaseReceipt` | `creator.publish` + human / CI approval。 |

现有 `mount` 成功后自动 publish preset 的路径应被拆开：`stage` 或 run-scope `activate` 绝不自动发布；`publish` 是单独的、可审计、可 review 的 release 动作。现有流程中 mount 成功即可将 source 写入 preset 目录，虽然已经记录事件和失败信息，但不能区分“临时实验成功”与“适合作为长期依赖”的治理层次。[8]

### 八、面向开发者的体验优先于自由 `ctx`

DSH 的最小 `apply(ctx)` 让第一插件非常容易写，却把能力、依赖、effect、控制归属和运行时安全大多推迟到开发者自己理解。[2] LCA 的开发体验应追求“声明多一点，排障少十倍”。

| 开发体验能力 | LCA 设计 | 解决的问题 |
|---|---|---|
| `lca plugin new` | 按 group / role / slot 生成 typed scaffold、Manifest、Config、fixture、golden trace 和 README。 | 不再从空白 `apply(ctx)` 猜架构。 |
| `lca plugin check` | 本地运行 Manifest、DAG、effects、grant、slot、descriptor 和 ownership 检查。 | 提前发现不合法的动态能力。 |
| `lca plugin doctor` | 显示 `PENDING` / blocked 的依赖链、缺失 capability、scope 不匹配、被拒原因与修复建议。 | 不再静默等待 provider。 |
| `lca creator diff` | 显示 artifact 对 ControlPlan、capability、effect、slot、prompt、trace 的影响。 | 知道编辑到底改变了什么。 |
| `lca creator stage` | 在 fixture 或 shadow run 中运行并显示 lifecycle / leak / evidence 报告。 | HMR 不再直接污染真实任务。 |
| `lca creator promote` | 选择明确 target scope、lease、rollback revision、审批方式。 | 动态变更可控制、可撤销。 |
| `lca trace explain` | 从某个 verdict / effect 回链到 plugin、revision、plan、artifact 和测试证据。 | 运行后的行为可理解。 |

所有诊断使用稳定错误码与结构化输出。缺依赖不是永久 `PENDING` 的沉默状态：在 `VERIFIED` 前即为 Resolve error；仅在明确声明的动态等待策略下允许 `BLOCKED`，且必须携带等待对象、deadline、唤醒条件和可见诊断。

## 后果

| 维度 | 正面后果 | 代价与约束 |
|---|---|---|
| 时空理解 | Agent 能解释“何时、在哪、对谁、以什么权限”行动，时间和空间不再是 prompt / global 隐变量。 | 要维护 source provenance、clock policy、scope graph 与事实 schema。 |
| 创造能力 | 运行期可产生、测试、替换和撤回新能力，并将成熟成果转化为 release artifact。 | 创造路径比直接 `importlib` / `ctx.plugin` 多出验证和审查阶段。 |
| 安全与恢复 | 动态能力的 effect、grant、证据、scope、版本和 rollback 都可被强制与重放。 | 实验与发布要维护 artifact store、lease 和 lifecycle controller。 |
| 开发体验 | typed scaffold、doctor、diff 与 shadow test 减少理解自由 ctx 的认知负担。 | 需要投入 CLI、schema、模板、fixture 和诊断产品。 |
| 运行可靠性 | 版本化 quiesce / drain 避免 HMR 覆盖产生的半途行为漂移。 | 生产替换不是瞬时的；需要定义 safe boundary 和超时策略。 |

## 验证约束

| 编号 | 约束 | 自动化证据 |
|---|---|---|
| **ST1** | 模型可见的时间 / 空间事实均有来源、有效期与 Journal ref。 | ContextManifest 重建测试；禁用 Reasoner 直接时钟 / workspace 读取。 |
| **ST2** | 时区混合、来源缺失或 deadline 解析歧义时不猜测。 | property / scenario tests 输出 clarify 或 explicit reject。 |
| **ST3** | 动态 artifact 在 `ACTIVE` 前不持有 live capability 或世界 effect。 | experiment isolation test；真实 provider / ledger append 被拒绝。 |
| **ST4** | artifact revision、logical ID、scope、actor、grant、gate 决定和 evidence 均可追溯。 | lifecycle Journal replay 与 topology inspect test。 |
| **ST5** | promotion 不扩大 grant，且 effect class 与 target scope policy 相容。 | grant subset / effect policy property tests。 |
| **ST6** | 替换不残留旧注册，不对已有 invocation 半途换实现。 | quiesce / drain / disposer / inflight tests。 |
| **ST7** | `BLOCKED` 只能是显式契约；任何缺依赖均给出因果链与 deadline。 | `plugin doctor` golden output；Resolver test。 |
| **ST8** | 实验成功不等于发布；发布必须有独立 approval / CI receipt。 | stage-to-release negative test。 |
| **ST9** | Creator 不获得裸 global context、秘密、跨 session 事实或不可控 host 代码执行。 | facade allowlist、scope isolation、secret / ACL tests。 |

## 实施序列

| PR | 标题 | 关键产物 | 验收锚点 |
|---|---|---|---|
| **PR-1** | ADR-0067 + Spacetime schema | `SpacetimeContext`、TemporalFact、ExecutionSpace、ScopeGraph 的 contracts 与 glossary。 | ST1、ST2。 |
| **PR-2** | Perceive 时间 / 空间传感器 | `temporal-context`、workspace / device context、provenance policy、ContextManifest 映射。 | ST1、ST2。 |
| **PR-3** | Dynamic Artifact Registry | content-addressed artifact、logical ID、revision、state machine、Journal descriptors。 | ST3、ST4。 |
| **PR-4** | Creation Gate Pipeline | identity / manifest / capability / invariant / evidence / experiment 六道闸。 | ST3、ST5。 |
| **PR-5** | Experiment Space + Lab HMR | isolated fake providers、lease、reloader、disposer / leak report、golden trace runner。 | ST3、ST6。 |
| **PR-6** | Production Promotion Controller | target scope、quiesce / drain、rollback、optional state migration、approval flow。 | ST4、ST5、ST6、ST8。 |
| **PR-7** | Creator DX 工具链 | scaffold、check、doctor、diff、stage、promote、trace explain。 | ST7、ST9。 |
| **PR-8** | 拆分 mount 与 publish | 现有 CordisControl 从立即 publish 改为 stage / explicit publish，保留迁移适配后删除。 | ST8。 |
| **PR-9** | 文档、CI 与清理 | architecture tests、schema docs、examples、legacy dynamic source-path / fallback 收口。 | ST1–ST9。 |

## 替代方案

| 方案 | 结论 | 原因 |
|---|---|---|
| 直接复刻 DSH `define/run/stop` 动态包 | 否决 | 实验速度高，但进程内存、VM 信任、无自动 durable evidence、无 ControlPlan promotion 不能满足 LCA 的恢复与安全边界。 |
| 仅允许静态插件，不提供 Creator | 否决 | 会失去运行期创造、局部试验和快速能力扩展，迫使用户回到修改框架源码。 |
| 让 Agent 动态执行任意 Python / YAML | 否决 | 将创造变成不可审计的通用代码执行，无法证明 slot、grant、effect 和状态 owner。 |
| 把时间 / 空间加入 PromptReasoner 便利字段 | 否决 | 缺少来源、可见性、有效期、审计与工具参数边界，且会形成认知旁路。 |
| 以 scoped artifact pipeline 实现动态创造 | 采纳 | 保留 DSH 的可组合与热反馈优势，同时将能力生命周期纳入 LCA 宪法。 |

## 参考

[1]: https://deepseek-harness.github.io/deepseek-harness/en/develop/cordis-tutorial/06-composition-and-hmr "DeepSeek Harness: Composition and HMR"
[2]: https://deepseek-harness.github.io/deepseek-harness/en/develop/framework/ "DeepSeek Harness: Plugins and lifecycle"
[3]: https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/context/time-context "DSH durable time-context package"
[4]: https://deepseek.com/harness/en/ "DeepSeek Harness developer preview"
[5]: https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/extensions/tool-cordis "DSH tool-cordis dynamic package toolset"
[6]: ../../lca/contracts/mechanisms/composition.py "LCA 当前 Composition 契约"
[7]: ../design/2026-08-14-execution-context-design.md "LCA ExecutionContext 设计"
[8]: ../../lca/plugins/tools/cordis_control/actions_mount.py "LCA 当前 Creator mount / auto-publish 路径"
