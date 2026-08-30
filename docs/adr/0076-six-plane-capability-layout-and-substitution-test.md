# ADR-0076: Six-Plane Capability Layout and Substitution Test

## 状态

**Accepted — 2026-08-23**

Refines: [ADR-0061](0061-plugin-manifest-resolve-boot.md)、[ADR-0068](0068-compiled-plugin-kernel-and-unified-run-plan.md)、[ADR-0069](0069-agent-primitive-system-and-declarative-grammar.md)、[ADR-0074](0074-plugin-everything-trimmed-implementation.md)、[ADR-0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md)。

> **核心决策：以六平面能力布局作为插件分类的唯一正交轴；以「替换测试」作为可插件化的验收标准；生产 profile 必须通过 `CompiledRunPlan` 提供完整 binding，boot 期缺失即失败，不允许运行时 fallback。**

## 背景

ADR-0074/0075 已建立「声明式计划 → 通用解释器 → 受控效果网关」的可验证路径。但当前代码仍存在四类结构性缺口，使替换某项能力时仍可能要求修改相邻解释器、组合器或 gateway 分支：

**Runtime fallback。** `CognitiveRuntime.__init__` 仍对 `reducer`、`topology`、`effect_handler_registry`、`delta_handler_registry` 提供具体 fallback（`DefaultReducer`、`ClosedSetTopology`、`DefaultEffectHandlerRegistry`、`DefaultDeltaHandlerRegistry`）。测试便利性保留可以理解，但生产 profile 路径不应依赖这些 fallback——缺失 binding 应在 boot/compile 期失败，而非在 turn 中静默降级。

**Composer 直接构造。** `BodyComposer` 调用 `build_default_action_registry()`，后者通过硬编码的 `_SCOPE_ACTIONS` 表（`ActionScope → frozenset[str]`）选择可用 action；`PerceiveComposer` 以隐式字符串 `"default"` 选择 stop rule；`TeamComposer` 直接 `new` `TeamSharedMemoryStore`、`build_team_transport()` 和 `TransportMemberInvoker`，而非消费已编译的 capability binding。

**Action catalog 未进入 plan 数据。** `_SCOPE_ACTIONS` 仍是代码内的静态表，未参与 `CompiledRunPlan` 的 authority/plan 编译。替换 action 集合需要修改 `action_catalog.py`，而非仅修改 bundle/profile entry。

**Gateway mode 固定分支。** `gateway/modes.py:resolve_lca_mode()` 仍以字符串 `if/elif` 分派 solo/team/cordis-creator，未进入 `run_mode_registry` 或 profile-owned adapter 选择。新增产品模式需要修改 gateway 源码。

这些缺口共同指向一个未形式化的分类问题：哪些能力属于哪个运行平面，以及「可替换」的验收标准是什么。

## 决策

### 一、六平面能力布局

插件分类不再按「代码在哪里」组织，而按「能力处于哪个运行平面」组织。六个平面与 LCA 现有 L0–L4 五层正交：层决定依赖方向，平面决定替换轴。

| 平面 | 对应 LCA 层 | 主要可替换能力 | 不可被插件改写的边界 |
|---|---|---|---|
| Constitution Kernel | L0 / L2 内核 | Protocol、typed atoms、invariant registry、plan validation | 六阶段闭集、Reducer 单写、CommandEnvelope、幂等与 grant 校验 |
| Infrastructure | L0 | LLM adapter、memory backend、state store、journal、tracer、file、sandbox、search、transport | 凭据泄漏、越权文件/网络、绕过 effect boundary |
| Cognitive | L1 | Sensor、PerceiveHub、Brain、Reasoner、Critic、RetrievalPolicy、Memory policy | 直接修改 AgentState；未经 grounding 的任意 prompt 注入 |
| Governance | L2 | 11 个 control slot（`perceive.context`、`think.guard`、`act.*`、`remember.admit`、`stop.decide`、`observe.*`） | deny 不能被后续普通插件放宽；控制结果须单调聚合并可重放 |
| Execution | L1 / L2 | Body、ActionHandler、Tool、SafeExecutor、EffectHandler、DeltaHandler | 真实世界效果必须经 CommandEnvelope、grant、scope、effect class、receipt |
| Organization & Interaction | L3 / L4 | Team strategy、role、invoker、shared memory、subagent、session、mode adapter、A2A/MCP | 子 Agent 权限只能收缩；mode 不得绕过 profile 和 plan |

**Evidence & Evolution** 作为横切平面（Journal backend、TraceInspector、FactReader、Scorer、Replay、ArtifactController），不与上述平面竞争，而是为其提供可重放证据。

### 二、替换测试

> **替换某项能力时，只增加或替换一个 bundle / profile / plugin entry，不修改相邻解释器、组合器、gateway 分支或状态写入逻辑。**

替换测试是「可插件化」的唯一验收标准。未通过替换测试的能力视为尚未完成插件化。具体门禁：

- 替换一个 control slot contribution → 只增加 plugin entry，不改 interpreter / composer / gateway
- 替换一个 phase executor → 只修改 profile binding，不改 `DeclarativeRuntimeDriver`
- 替换一个 effect / delta handler → 只注册新 handler，不改 `RuntimeEffectGateway`
- 替换一个 team backend（invoker / transport / shared memory） → 只增加 capability binding，不改 `TeamComposer`
- 替换一个 run mode → 只增加 mode adapter plugin，不改 gateway 字符串分派

### 三、Manifest 四必填维度

插件 Manifest 元数据按四个必填维度收紧，不再增加自由字段：

| 维度 | 要回答的问题 | 示例 |
|---|---|---|
| Capability | 我提供什么、依赖什么、是唯一 owner 还是 contributor？ | `provides: action_handler_registry`，`requires: tools, sandbox` |
| Authority | 我能读取、写入、触发什么？ | `reads: facts.workspace`，`effects: filesystem`，`grants: tool_bash` |
| Lifecycle | 我活多久、在哪个 scope 可见、如何卸载？ | `scope: run`，`activation: profile`，`disposal: required` |
| Evidence | 我产生哪些事实，能否从 Journal 重建，如何验证？ | `emits: EffectReceipt`，`replay: required`，`test_suite: ...` |

`provides/requires` 负责可执行的 capability DAG；`FunctionalGroup × ControlSlot × Scope × Authority × Evidence × Revision` 逻辑地址负责语义定位、权限审计和 provenance。两者不能互相替代。

### 四、生产路径 boot 期硬失败

- 声明式 profile 缺少 `effect_handler_registry` / `delta_handler_registry` / `reducer` / `loop_topology` binding 时，boot 或 compile 阶段必须失败
- `CognitiveRuntime` 保留默认构造以支持测试 fixture，但生产 `boot_profile()` 路径必须在 `agent_assembly.py` 中验证 binding 完整性
- 验证失败抛 `MissingBindingError`，包含缺失 capability key 和期望来源（profile / bundle / plugin）

### 五、Composer 只消费 compiled capability

- `BodyComposer` 不得调用 `build_default_action_registry()`；action catalog 必须由 `CompiledRunPlan` 的 authority 数据提供
- `_SCOPE_ACTIONS` 静态表迁移为 compiled plan 数据：`ActionScope` 枚举保留为 metadata，实际 allowed actions 由 plan compiler 从 `TaskContract` + `RoleProfile` + `CapabilityGrant` 推导
- `PerceiveComposer` 的 stop rule 选择必须来自 plan binding，不再使用隐式字符串 `"default"`
- `TeamComposer` 的 `TeamSharedMemoryStore`、`TeamTransport`、`MemberInvoker` 必须从 scope capability 注入，不再直接 `new`

### 六、Gateway mode 注册表化

- 新增 `run_mode_registry` capability seam，每个 mode（solo / team / cordis-creator / 未来 creator / research / code）注册为 mode adapter plugin
- `gateway/modes.py:resolve_lca_mode()` 改为查询 `run_mode_registry`，不再字符串 if/elif
- mode adapter plugin 声明工具白名单、persona、role policy、composer set 和 evidence policy，但不能直接改变 kernel invariants

### 七、模式策略与工具物化的补充收口

- 内建 mode adapter 必须按 mode entry 分别注册；不得以一个聚合 defaults plugin 同时装载 Solo、Team 与 Creator。替换任何一个 mode 只能变更对应 bundle entry。
- Creator mode 不得直接 import persona builder、硬编码工具名集合、Composer factory 或 caller grant。角色与工具权限来自 ``role.cordis_creator``，Composer-bound ``cordis_control`` 工具来自 ``cordis_control_tool_factory``。
- ``build_from_casting_plan`` 是纯计划投影，不得调用 ``build_default_tools``。所有 Team member 工具必须由上游 run-assembly 从 profile 的 ``tools`` capability 物化后显式传入。

### 八、内容与策略的末端默认清理

- ``LLMTeamCaster`` 不得加载内建提示词；它必须消费 ``team_casting_prompt_renderer``。内建模板仅可由该能力的默认插件读取，因此替换选角提示内容不改变解析、白名单或 gateway mode。
- ``SimpleBrainFactory`` 不得加载 React、层级或路由提示词；它必须消费 profile 提供的 ``reasoner_template_catalog``。模板完整性在插件配置期校验，缺失任一标准模板即 boot 失败。
- 生产 ``MemoryService`` 物化 ``SimpleMemorySystem`` 时，写入、压缩和检索策略必须分别来自 ``memory.write_policy``、``memory.compaction_policy`` 和 ``memory.retrieval_policy``；调用期不得以参数覆盖。直接构造 ``SimpleMemorySystem`` 的本地默认仅限 fixture 与独立单元测试。
- ``composition.compose_factory`` 必须消费 ``composition.invariant_checker``；``CordisComposer`` 的本地便利默认不构成 profile 生产路径。替换 mount 治理策略不得修改 Composer provider 或 Creator 工具。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| 可解释性 | 每个插件属于且仅属于一个平面；替换轴正交，不互相干扰 | 现有插件目录结构需要重新标注平面归属（一次性） |
| 可验证性 | 替换测试可自动化：CI 跑「替换 X 只增加 entry」门禁 | 需要为每个平面写替换性测试 fixture |
| 可组合性 | bundle/profile 成为唯一装配入口；gateway / composer 不再选择具体实现 | 现有 `TeamComposer` / `BodyComposer` 需要拆分 seam |
| 可重放性 | 四必填维度中 Evidence 维度强制 journal 重建能力 | 插件 manifest 字段增加，编写成本略升 |
| 安全性 | boot 期硬失败阻止生产环境静默降级 | 测试 fixture 需要显式提供完整 binding |

**验证约束：**

- `tests/architecture/test_six_plane_taxonomy.py`：每个插件 manifest 可映射到恰好一个平面
- `tests/architecture/test_substitution_gates.py`：替换 control slot / phase executor / effect handler / team backend / run mode 只增加 entry
- `tests/test_boot_binding_completeness.py`：生产 profile boot 时缺少 binding 抛 `MissingBindingError`
- `tests/composer/test_composer_consumes_compiled_capability.py`：composer 不直接构造具体实现
- `tests/architecture/test_casting_prompt_renderer_capability.py`、`test_reasoner_template_catalog_capability.py`、`test_memory_policy_capabilities.py`、`test_composition_invariant_capability.py`：内容与策略实现均由 profile capability 注入

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 保留现有五层 + 按功能群分类 | 功能群与替换轴不正交；Team strategy 和 Team transport 属于不同替换轴但同一功能群 |
| 把所有代码平铺为插件（DeepSeek Harness 式） | 违反宪法 C6（改闭集必 ADR）；六阶段闭集和 Reducer 单写不应被插件改写 |
| 只新增 ADR 不落地代码 | 四类结构性缺口已通过源码验证存在；不落地则替换测试无法自动门禁 |
| 保留 `_SCOPE_ACTIONS` 作为 metadata + 同时支持 compiled plan | 双轨违反 ADR-0075 的最小可信内核原则；compiler 必须拥有唯一事实源 |
| Gateway mode 继续字符串分派，只加注释 | 新增产品模式（research / code / creator 变体）需要修改 gateway 源码，违反替换测试 |

## 落地顺序

| 阶段 | 目标 | 验收标准 |
|---:|---|---|
| P0 | 收紧生产 runtime 注入 | 声明式 profile 缺少 effect/delta/reducer/topology binding 时在 boot/compile 阶段失败，而不是 turn 中 fallback |
| P1 | 清理 Composer 直接构造 | BodyComposer、PerceiveComposer、TeamComposer、gateway mode 只消费 compiled capability，不直接选择具体实现 |
| P2 | 统一 Execution 三段式 | ActionHandler、EffectHandler、DeltaHandler 各有独立 Protocol、registry、receipt 和替换性测试 |
| P3 | 完成 Organization seam | Team invoker、transport、shared memory、subagent provider、run mode adapter 可单独替换 |
| P4 | 统一 Evidence vocabulary | 每个模型可见输入和外部效果都能从 append-only Journal 依据 `plan_ref`、scope、grant 和 idempotency key 重建 |
| P5 | 建立替换性门禁 | CI 测试证明「替换一个 control slot / phase / effect / team backend / mode，只增加 plugin 或 patch，不改 interpreter / composer / gateway」 |
