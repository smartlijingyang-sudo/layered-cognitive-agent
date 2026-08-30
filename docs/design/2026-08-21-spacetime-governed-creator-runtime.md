# 时空与受治理创造运行时设计

**将 DSH 的动态组合能力编译为 LCA 的可证明创造平面**

| 字段 | 值 |
|---|---|
| 日期 | 2026-08-21 |
| 状态 | Draft for ADR-0067 Implementation |
| 决策锚点 | [ADR-0067：时空运行时与受治理的动态创造](../adr/0067-spacetime-runtime-and-governed-creation.md) |
| 宪法锚点 | [声明式插件宪法 v4.0](2026-08-21-declarative-plugin-constitution-v4.md) |
| 既有基础 | `PluginDefinition`、ResolvedProfile、ControlPlan、Composer、Journal / Evidence、ExecutionContext |
| 非目标 | 不构建第二个认知 loop、不开放任意 host 代码执行、不将 YAML 变成通用编程语言。 |

> **设计目标：让 Agent 可以在运行时认识“此刻、此地、此身份、此可见性、此生命周期”，在隔离实验空间里创造能力，拿到可解释证据后才提升它；但系统的认知闭集、授权边界、状态所有权和账本语义永远不随动态代码变得模糊。**

## 1. 架构意图

DSH 的最大启发不是某一个 API，而是它把 Agent 运行时从“静态工具清单”推进为“可检查、可组合、可重载的能力树”。Cordis 的稳定 entry ID、group / isolate、Fiber 生命周期和 HMR 给出了快速实验的优秀反馈回路；DSH Creator 又把 inspect、define、run、stop、undefine 做成模型可操作的领域动作。[1] [2]

LCA 的差异化目标不是比 DSH 更自由地运行动态代码，而是把动态性编译为一个**受宪法约束的能力交付流程**。此流程将时空事实、工件身份、静态契约、隔离实验、ControlPlan diff、授权、证据、提升、排空与回滚连接成同一因果链。它需要同时让 Agent、开发者、审计者和运行平台各自看见正确抽象，而不暴露全局 `ctx`、进程状态或隐式文件路径。

```text
             ┌──────────────────────── Profile / TaskContract ───────────────────────┐
             │ 用户目标 · grant · 预算 · 风险 · 审批规则 · role                     │
             └─────────────────────────────┬─────────────────────────────────────────┘
                                           Resolve
                                             │
          ┌──────────── SpacetimeContext ───┴─────┐
          │ 时间事实 · 执行空间 · 身份 / 可见性 · scope graph │
          └──────────────┬────────────────────────┘
                         │                         │
                  Perceive / Act             Creator plane
                         │                         │
                         ▼                         ▼
                  ContextManifest      Draft → Verify → Stage → Promote → Retire
                         │                         │
                         └─────────────┬───────────┘
                                       │
                                  ControlPlan
                                       │
                                       ▼
                  Brain → Gate → ExecutionControl → Observation
                                       │
                                       ▼
                              Journal + Evidence Ledger
```

## 2. 时空模型：五个正交事实面

### 2.1 TemporalContext：时间不是 `now()`

时间的设计必须同时满足人类语义和确定性重放。wall clock 可以回答“现在是何时”，但会漂移、回跳和受时区影响；logical clock 才能稳定回答“在该 run 的因果顺序中发生在何处”。因此时间模型永远同时持有两者，并明确来源与不确定性。

```python
@dataclass(frozen=True)
class TemporalContext:
    observed_at: datetime                 # 带 offset 的 wall-clock 采样
    clock_source: ClockSource             # trusted_host | browser_verified | external | replay
    source_time_zone: TimeZoneResolution  # unique | mixed | unavailable + IANA zone
    logical_time: LogicalTime              # run_id, run_seq, turn, step
    elapsed_since_visible: timedelta | None
    uncertainty: TemporalUncertainty       # exact | rounded | drift_detected | unavailable
    valid_until: datetime | None
    evidence_ref: EvidenceRef
```

| 机制 | 设计 | 原因 |
|---|---|---|
| 真实时间 | `observed_at` 从声明的可信 Clock provider 采样。 | 减少 Reasoner 私自访问系统时间。 |
| 用户时区 | 必须来自 host 验证的请求 provenance；混合来源不猜测。 | 保留 DSH 的正确来源边界。[3] |
| 逻辑时间 | 使用 `run_seq`、turn、step；它是重放与因果排序主键。 | 避免 wall-clock 在并发 / 回放中混淆顺序。 |
| 经过时间 | 使用 monotonic 基线；wall clock 回跳则标为 drift，不伪造负值。 | 使 deadline、retry、budget 可诊断。 |
| 有效期 | 每个时间敏感事实必须给出 TTL / `valid_until`。 | 防止陈旧“现在”一直进入模型。 |
| 工具参数 | 工具仍要求显式时区 / offset 参数。 | 时间上下文仅帮助理解自然语言，不能填补工具语义。 |

TemporalContext 作为 `perceive.sensor.temporal-context` 的输出进入 ContextManifest；它不能通过 Hook 或全局 prompt 模板绕过 Perceive。`act.budget.wall-clock` 和 `stop.decide.deadline` 只接收该 context 与 `TaskContract` 的 deadline，而不重新读取系统时钟。

### 2.2 ExecutionSpace：空间不是字符串路径

ExecutionSpace 表达 Agent 实际能触达的计算环境。它以 `space_id` 标识，并使 workspace、backend、设备、网络、文件边界与能力集合显式化。既有 `ExecutionContext` 的“真实 workspace、显式 capabilities、操作回传 env_state、viewport 截断”被采纳为基础语义。[4]

```python
@dataclass(frozen=True)
class ExecutionSpace:
    space_id: str
    backend: BackendKind
    workspace: ResourceRoot
    outputs: ResourceRoot
    device_ref: DeviceRef | None
    network_zone: NetworkZone
    capabilities: frozenset[ExecutionCapability]
    filesystem_policy_ref: PolicyRef
    egress_policy_ref: PolicyRef
    env_baseline_ref: EvidenceRef
    parent_space_id: str | None
```

| 空间形态 | 用途 | 常见能力 | 禁止默认假设 |
|---|---|---|---|
| `local-sandbox` | 本地 / 容器开发。 | filesystem、shell、code-exec。 | 不假设有浏览器、GPU、网络或持久进程。 |
| `remote-sandbox` | 隔离远端执行。 | 受限 shell、files、job。 | 不泄露 host 路径或凭据。 |
| `device-space` | 浏览器、手机、桌面设备。 | screenshot、input、UI slots。 | 不等同于 filesystem access。 |
| `team-shared-space` | 明确共享的工件 / 证据区域。 | allowed artifact read / write。 | 不等同于共享 AgentState / memory。 |
| `experiment-space` | 动态能力试验。 | fake provider、fixture、trace runner。 | 不得默认网络、真实工具、真实账本。 |

任何空间转换都必须在 `act.authorize` 和 `act.constrain` 中被解释：从 host 转向 remote sandbox、从 private workspace 输出到 shared space、从普通文件访问转向秘密读取均是不同的 effect，不是路径前缀变化。

### 2.3 IdentitySpace、VisibilitySpace 与 LifecycleSpace

时空设计若忽略“谁”与“谁能看见”，只会得到更漂亮的路径模型。IdentitySpace 绑定 authenticated principal、tenant、role、Agent、session 和 delegation chain；VisibilitySpace 绑定 audience、classification、retention、ACL 与 memory scope；LifecycleSpace 绑定资源的创建者、父 scope、lease、expiry 与 disposer。

```text
IdentitySpace  回答：谁请求 / 谁负责 / grant 从谁衰减？
VisibilitySpace 回答：谁可读 / 可外送 / 可写入哪层记忆？
LifecycleSpace 回答：何时释放 / 谁排空 / 能否提升到更长生命周期？
```

它们共同让“动态插件可以影响什么”变成一个可计算的问题：`effect ⊆ caller_grant ∩ target_scope_policy ∩ visibility_policy ∩ lifecycle_policy`。

## 3. ScopeGraph：空间的运行时拓扑

### 3.1 Scope 节点与能力传播

ScopeGraph 是一棵以 Profile / Agent / Run 为主干、以 Experiment 与 Invocation 为叶子的有向无环图。它与 Capability DAG 不同：Capability DAG 回答“谁依赖谁”，ScopeGraph 回答“这个实例在哪个边界内存活、可看见什么、何时释放”。两图由 `scope_id`、`logical_id` 与 capability handle 交叉关联，但不能互相替代。

```text
release
  └── profile:research-code
        ├── agent:lead
        │     └── run:run_01
        │           ├── turn:7
        │           │     └── invocation:tool_42
        │           └── experiment:exp_09 (child; fake providers)
        └── agent:researcher
              └── run:run_02
```

| 关系 | 允许传播 | 禁止传播 |
|---|---|---|
| 父 → 子 | capability grant 的子集、可读 baseline、明确导出的 immutable config。 | 父的秘密、未授权 effect、可变 private state。 |
| 子 → 父 | Observation、Journal fact、EvidenceRef、经过验证的 artifact promotion request。 | live object、closure、直接 service binding、扩大 grant。 |
| 同级 → 同级 | 受 ACL 的 TeamMessage、shared artifact ref。 | 私有 memory、run-local Context、未提交 state。 |
| experiment → release | 经 human / CI 审批的 immutable artifact digest。 | 运行时 source path、未固定依赖、无测试的 live fiber。 |

### 3.2 生命周期与释放语义

每个 Scope 都持有 `Lease`。Lease 明确 `created_at`、`valid_until`、`owner`、`renewal_policy`、`quiesce_policy` 和 `disposal_deadline`。scope 关闭时，所有 child scope 必须先 `QUIESCING`，拒绝新调用，按照依赖反序 drain，再释放 effect。若 drain 超时，由预先声明的 cancellation policy 处理，并记录 `ScopeForcedDispose`；不允许默默遗留线程、timer、工具注册或外部连接。

DSH Fiber 的自动 effect cleanup 和 child context 生命周期可以成为此实现的底座。[2] LCA 额外要求**串行可证明的 disposer 计划**：凡存在顺序依赖的资源必须由一个显式 `DisposalPlan` 声明步骤，不依赖多个异步 disposer 的偶然完成次序。

## 4. 动态能力工件：从代码文本到可提升能力

### 4.1 Artifact 是不可变、可寻址、可审计的

动态能力的事实单位是 `CapabilityArtifact`，不是 `source_path`、Python module name 或一个在内存中活着的对象。其内容由摘要标识，逻辑身份与版本摘要分开，依赖与生成环境也一并固定。

```python
@dataclass(frozen=True)
class CapabilityArtifact:
    logical_id: str                     # e.g. act.constraint.network-egress
    revision_digest: str                # sha256 over canonical source + manifest + lock metadata
    kind: ArtifactKind                  # plugin | bundle | profile_patch | bridge
    source_ref: EvidenceRef
    manifest: ArtifactManifest
    dependency_lock: DependencyLock
    provenance: ArtifactProvenance
    contract_version: str
```

| 字段 | 必须表达 | 为什么不能省略 |
|---|---|---|
| `logical_id` | 所替换 / 提供的稳定概念地址。 | 让 diff 和 rollback 知道“这是同一个能力”。 |
| `revision_digest` | 源、Manifest、依赖 lock 的不可变版本。 | 排除“相同路径，内容不同”的幽灵重载。 |
| `source_ref` | 原始文本 / 生成记录的证据引用。 | 审计与复现不能依赖工作区仍存在。 |
| `manifest` | group、slot、type、effect、grant、tests、lifecycle。 | 防止动态源码绕过插件宪法。 |
| `dependency_lock` | 模块 / provider / schema 版本。 | 避免实验与提升期间依赖漂移。 |
| `provenance` | 人 / Agent / 模板 / 工具 / prompt / parent artifact。 | 让自进化保持可追溯。 |

### 4.2 Artifact Manifest 的附加字段

现有 `PluginDefinition` 和 ADR-0066 的 `architecture` 区段保持为唯一插件声明表面。动态 artifact 只在其上添加 delivery 信息，不能复制一份独立 schema。

```yaml
id: act.constraint.network-egress
architecture:
  group: act
  role: constraint
  primary_slot: act.constrain
  ownership:
    reads: [execution.envelope, task.contract]
    emits: [policy.egress.checked, policy.egress.denied]
  authority:
    requires: [network.policy.read]
  control:
    aggregate: narrow_only
    failure_mode: deny
  lifecycle:
    scope: run
    concurrency: serialized-per-run
artifact:
  logical_id: act.constraint.network-egress
  revision_digest: sha256:...
  target_scopes: [experiment, run]
  promotion_policy: approval-required
  state_migration: none
  dependency_lock_ref: sha256:...
```

`target_scopes` 是上限而不是自授予：实际提升仍受 TaskContract、caller grant、target ScopeGraph 和 environment policy 约束。任何 `state_migration` 不是任意回调；它只能实现受版本化 schema 约束的 pure transformation，并在 shadow replay 中证明等价或明确声明语义变化。

## 5. 创造管线：Define 不等于 Run，Run 不等于 Release

### 5.1 正式状态机与事件词表

```text
                    ┌────────────────────────────────┐
                    │  ArtifactDrafted                │
                    ▼                                │
DRAFT → PARSED → DECLARED → VERIFIED → STAGED → ACTIVE ──→ QUIESCING → RETIRED
  │        │          │          │          │            │
  │        │          │          │          │            └──→ ROLLED_BACK
  └────────┴──────────┴──────────┴──────────┴──────────────→ REJECTED
```

| 转移 | 发射事件 | 条件 | 可逆性 |
|---|---|---|---|
| Draft → Parsed | `ArtifactParsed` | syntax / format 正确。 | 可丢弃。 |
| Parsed → Declared | `ArtifactDeclared` | Manifest 完整、ID / contract version 有效。 | 重新声明新 revision。 |
| Declared → Verified | `ArtifactVerified` | static gates、grant / effect / slot / descriptor 全部通过。 | 依赖变更后需重新验证。 |
| Verified → Staged | `ArtifactStaged` | experiment lease + fixture + fake providers 可用。 | stop stage。 |
| Staged → Active | `ArtifactPromoted` | promotion approval、scope policy、rollback target、drain plan。 | rollback。 |
| Active → Quiescing | `ArtifactQuiescing` | retire / replace / lease expiry。 | 可 cancel（仅无新版本激活前）。 |
| Quiescing → Retired | `ArtifactRetired` | inflight 归零 / 取消、effects disposed、receipt 写入。 | 需重新 promote。 |
| any → Rejected | `ArtifactRejected` | 失败 gate / policy / test。 | 新 digest 重试。 |

每个事件使用 Journal descriptor，payload 至少包含 `logical_id`、`revision_digest`、`scope_id`、`actor_ref`、`plan_ref`、`grant_ref`、`reason_code` 与必要的 `evidence_refs`。未触发事件的状态变迁应被视为数据损坏。

### 5.2 六道 Gate 的实现位置

```text
CreationRequest
    │
    ├─ creation.identity   ── artifact registry
    ├─ creation.manifest   ── manifest resolver
    ├─ creation.capability ── grant / effect analyzer
    ├─ creation.invariant  ── architecture invariant suite
    ├─ creation.evidence   ── descriptor / evidence policy
    └─ creation.experiment ── isolated trace runner
                                      │
                                      ▼
                                  PromotionPlan
```

**Creation Gate 不属于 Think / Act 的普通业务 slot。** 它是 G10 Composition 的生命周期治理面；它可以拒绝能力进入图，但不能在业务运行时批准某次工具调用。后者仍由 `act.authorize`、`act.budget`、`act.constrain`、`act.execute` 负责。

### 5.3 实验空间的默认安全形态

| 资源类别 | experiment 默认 | 启用真实资源的例外 |
|---|---|---|
| LLM | deterministic fake / recorded response。 | 需要预算隔离、数据分类与显式 approval。 |
| Tool / network | fake executor、deny egress。 | 仅专门的 integration environment，不能用普通 stage。 |
| Filesystem | temp workspace、fixture-only mounts。 | 受限 clone / readonly checkout。 |
| Journal | isolated test ledger、可删除 evidence。 | shadow append 不可影响 production run。 |
| Memory | ephemeral store。 | 不能写真实 semantic / procedural layer。 |
| Clock | injected frozen / controlled clock。 | 测试 temporal policy 时使用可记录的 fake clock。 |
| Browser / UI | mocked client slots、snapshot rendering。 | 人工批准的 preview session。 |

## 6. 动态更新：Lab HMR 与 Production Promotion

### 6.1 Lab HMR：开发反馈循环

Lab HMR 仅在 experiment space 生效。文件变更或 artifact revision 变更会使当前 staged fiber 进入 `QUIESCING`，执行 DisposalPlan，启动相同 fixture 的新 revision，并输出三份 diff：Manifest diff、ControlPlan diff、Golden Trace diff。开发者不用猜“重载是否成功”，也不用仅看日志。

```text
edit source
  → canonicalize + digest
  → parse + declared manifest
  → fast static check
  → quiesce staged revision
  → recreate fixture scope
  → run new revision
  → show {topology, verdict, effects, evidence, leak} diff
```

稳定 logical ID 是 HMR 的前提；revision digest 不同并不意味着新逻辑实体。无 logical ID 的内容只能 `stage-as-new`，不得自动替换其他能力。

### 6.2 Production Promotion：版本化交接

生产提升在 turn / invocation 安全边界生效：执行中的 invocation 必须继续使用开始时绑定的 revision，下一次 invocation 才可使用新 revision。必须替换的长时服务先进入 `QUIESCING`，停止接受新 work，drain 或按 policy cancel 旧 work；新 revision 只有在旧 revision 的 disposal receipt 和 PromotionPlan 条件满足后激活。

| 情况 | 允许行为 | 禁止行为 |
|---|---|---|
| 纯 observe exporter 替换 | 在下一 committed record 之前切换。 | 修改已投影历史。 |
| prompt / sensor 改动 | 下一 turn 的 Perceive / Think 才生效。 | 修改正在构造的 ContextManifest。 |
| tool executor 改动 | 下一 invocation 生效。 | 半途接管已有 process / request。 |
| memory policy 改动 | 下一 memory admission 生效。 | 改写已提交记忆。 |
| state schema 改动 | 必须新 ADR / migration contract。 | HMR 直接替换 Reducer。 |
| loop driver 改动 | 只允许新 run / 受审查 fork。 | 当前 run 中间换 loop。 |

## 7. Creator 开发体验：比自由 ctx 更友好

### 7.1 意图驱动 scaffold

开发者或 Agent 应先说“我要一个什么原子能力”，而不是从一个 `apply(ctx)` 空函数开始。`lca plugin new` 根据 `group + role + slot` 生成类型化骨架、Config、tests、fixture、descriptor TODO、文档和最小 Bundle。

```text
$ lca plugin new \
    --group act --role constraint --slot act.constrain \
    --id act.constraint.network-egress

created:
  lca/plugins/act/constraint_network_egress.py
  tests/plugins/act/test_constraint_network_egress.py
  fixtures/golden_profiles/network_egress.yaml
  docs/plugins/act.constraint.network-egress.md
```

生成器不允许 `utils.py`、自由 `ctx`、未知 `effect` 或未指定 `test_suite`。它以契约先于实现的方式降低开发者不确定性。

### 7.2 Doctor、Diff 与 Explain

| 命令 | 核心问题 | 必须输出 |
|---|---|---|
| `lca plugin check <artifact>` | 这个东西合法吗？ | schema、DAG、slot、grant、effect、descriptor、ownership 结果。 |
| `lca plugin doctor <scope>` | 为什么没加载 / 没生效？ | dependency chain、BLOCKED reason、deadline、scope mismatch、suggested fix。 |
| `lca creator diff <a> <b>` | 编辑改变了什么？ | Manifest、ControlPlan、capability、effect、prompt / tool schema、trace diff。 |
| `lca creator stage <artifact>` | 在隔离空间工作吗？ | fixture result、verdicts、evidence、resource / disposer / leak receipt。 |
| `lca trace explain <event>` | 为什么出现这条行为？ | run event → plan entry → plugin revision → artifact provenance → test evidence。 |

所有命令返回结构化 JSON 和人类可读摘要；错误必须是稳定 `reason_code`，而不是仅给 exception 文本。`BLOCKED` 必须描述“等待什么、哪个 scope 可能提供它、等到何时、何时转 reject”。

### 7.3 Inspect 的双视图

Creator inspect 需要同时展示**编译期可做什么**和**运行期正在做什么**，但两者不可混淆。

| 视图 | 数据来源 | 展示 | 不能推断 |
|---|---|---|---|
| `catalog` | Manifest / generated contract catalog | API、slots、effects、tests、allowed scopes。 | 某 capability 当前一定 active。 |
| `topology` | ScopeGraph + active registry | active revision、fiber state、waiting dependency、lease、inflight count。 | 其 API 一定安全或有权限。 |
| `control-plan` | ResolvedProfile | 每个 slot 的排序、条件、聚合、grant。 | 当前某条件已经为 true。 |
| `evidence` | Journal / Evidence | 实际 activation、verdict、effect、rollback。 | 未提交的 runtime local state。 |

这吸收 DSH `inspect` 对 live service 与 compile-time catalog 分别报告的思想，同时给 LCA 加上 ControlPlan、scope 和 grant 视图。[5]

## 8. 安全、可恢复性与发布

### 8.1 威胁模型

动态创造最危险的误区是把“能写 plugin”误解为“拥有系统管理员权限”。DSH 也明确其 VM sandbox 是对诚实代码的隔离而非安全边界，动态包应按 bash 等级信任。[5] LCA 的策略是把任何可执行动态 artifact 视为高风险能力，默认仅允许在无真实 provider 的 experiment space 运行；要进入真实 run，必须拥有目标 scope grant 和明确的 effect policy。

| 威胁 | LCA 控制 |
|---|---|
| 动态代码读秘密 / 逃逸 sandbox | experiment 无 secret provider；facade allowlist；真实 scope 需 effect + grant + human approval。 |
| 新插件绕过状态 owner | Manifest / AST / runtime ownership gate；只能经 Delta、Verdict、Observation 或 Journal fact 输出。 |
| 新插件绕过执行窄门 | effect analyzer 拒绝非 `act.execute` 的 world effect；provider façade 不暴露裸客户端。 |
| 新插件污染其他 run | ScopeGraph / tenant / session ACL；默认 run-local；跨 scope 只引用 immutable artifact。 |
| 发布不成熟实验 | stage 和 publish 分离；release gate 要求 CI / approval receipt。 |
| 回滚后证据丢失 | artifact、promotion、retirement 与 rollback 只追加 Journal；revisions 不覆盖。 |
| HMR 泄漏资源 | DisposalPlan、leak check、scope forced-dispose event、inflight drain。 |

### 8.2 发布物与供应链

Release artifact 必须有版本、摘要、签名（或可信 provenance）、dependency lock、SBOM / dependency metadata、测试结果、兼容范围和弃用策略。Release catalog 中不存在“当前工作区某路径”的隐式引用。发布的 Bundle 只引用 release digest / logical version，Profile 使用受到 policy 约束的版本范围。

```text
artifact source + manifest + lock + test evidence
                 │
                 ▼
             release digest
                 │
          approval / CI receipt
                 │
                 ▼
      signed catalog entry + versioned bundle
                 │
                 ▼
       Profile Resolve → immutable ControlPlan
```

## 9. 与现有 LCA 模块的衔接

| 现有资产 | 继续保留 | 本设计新增 / 调整 |
|---|---|---|
| `PluginDefinition` / `@plugin` | ID、Config、requires / provides、layer、kind、effects、tests。 | `architecture` 与 `artifact` delivery metadata 的严格 schema。 |
| Resolve / Boot | capability DAG、fail-fast、dispose。 | 生成 ScopeGraph template 与 ControlPlan；动态 artifact 只能通过 resolver 注入。 |
| `Composer` | mount / unmount / inspect、grant 子集、invariant、Journal audit。 | 拆为 ArtifactRegistry、ExperimentController、PromotionController；不再 mount 后自动 durable publish。 |
| `ExecutionContext` | workspace、backend、capabilities、env_state。 | 升格为 ExecutionSpace，加入 policy / identity / scope refs。 |
| PerceiveHub / sensors | ContextManifest 与 Journal 准入。 | temporal-context、space-context 与 provenance policy。 |
| Journal / Evidence | 事实、证据、投影可恢复。 | artifact lifecycle descriptors、promotion / rollback receipt、plan / revision links。 |
| `cordis_control` | inspect / author / mount 入口。 | 转为 inspect / author / validate / stage / promote / retire / publish 领域操作。 |
| PresetAuthoring | durable release 文件写入。 | 只消费 approved release artifact，取消 mount success 自动 publish。 |

## 10. 实施质量门与验收样例

### 10.1 最小垂直切片

第一个可用切片不应该实现“Agent 自己写任意工具”。它应选择无世界副作用的 `observe.projector.creator-diagnostic`：Creator author 一个只读 projector，在 experiment scope replay fixture Journal，生成诊断，比较 golden output，通过后 promotion 到 run-local observe scope，最后明确 publish。该切片覆盖全部生命周期但不暴露真实工具风险。

### 10.2 关键 golden scenarios

| 场景 | 应证明的结果 |
|---|---|
| 混合浏览器时区的同一 turn | `TemporalContext.source_time_zone=mixed`，模型被要求澄清，工具没有收到伪造时区。 |
| 动态 artifact 请求超出 caller grant | 在 `creation.capability` 被拒，尚未创建 live fiber。 |
| staged 网络 executor 尝试真实 egress | experiment provider 拒绝，并留下 policy evidence。 |
| 替换 active tool plugin 且有 in-flight 调用 | 旧 revision drain；旧调用完成或被记录取消；新 revision 只处理新 invocation。 |
| staged plugin 忘记释放资源 | leak check 失败，不能 promote。 |
| 成功 stage 后未通过 publish approval | artifact 保持 verified / staged，release catalog 未变化。 |
| run 发生 `PolicyDenied` | `trace explain` 反向给出 slot、artifact revision、promotion receipt、TaskContract / grant 与原始 evidence。 |
| 依赖 provider 未满足 | `doctor` 输出受阻链、deadline 与可行修复；不会无解释 PENDING。 |

## 参考

[1]: https://deepseek-harness.github.io/deepseek-harness/en/develop/cordis-tutorial/06-composition-and-hmr "DeepSeek Harness: Composition and HMR"
[2]: https://deepseek-harness.github.io/deepseek-harness/en/develop/framework/ "DeepSeek Harness: Plugins and lifecycle"
[3]: https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/context/time-context "DSH durable time-context"
[4]: 2026-08-14-execution-context-design.md "LCA ExecutionContext 设计"
[5]: https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/extensions/tool-cordis "DSH dynamic Creator toolset"
[6]: ../adr/0067-spacetime-runtime-and-governed-creation.md "ADR-0067"
[7]: 2026-08-21-declarative-plugin-constitution-v4.md "声明式插件宪法 v4.0"
