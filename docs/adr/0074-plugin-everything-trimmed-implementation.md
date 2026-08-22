# ADR-0074：Plugin-Everything 裁剪版实施计划

## 状态

**Proposed — 2026-08-21**

## 关系

- **Refines（核心接受）**：ADR-0066（Control Slot）、ADR-0068（CompiledRunPlan）、ADR-0069（13 原语群 + LogicAddress + 11 关系代数 + 6 contribution verbs + PluginContract 概念）
- **Supersedes（部分）**：ADR-0067 §四（8 状态机 → 4 状态机）、ADR-0067 §七（7 Creator 面 → 4 Creator 面）、ADR-0067 §一–§三（SpacetimeContext 5 子空间 → 仅实现 ExecutionSpace + LifecycleSpace 两个最急子空间，其余进 ADR Draft）
- **Co-evolves with**：
  - ADR-0065（Recoverable Evidence Ledger，已落地）
  - ADR-0063（Run Trace SSOT，已落地）
  - ADR-0070（Reducer-as-Plugin，已落地 — 本计划 §二引用其 Reducer Protocol）
  - ADR-0072（Null-Default Discipline，已落地 — 本计划 §二引用其 Null 实现家族）
  - ADR-0071 / ADR-0073（本地 ADRs，作为并行子计划纳入本计划 §三）

> **核心决策：在 ADR-0066 / 0068 / 0069 的优雅核心之上，裁剪 ADR-0067 的过度工程部分（状态机、Creator 面、Spacetime 子空间），按 13 个 PR 分阶段落地。完整接受 CompiledRunPlan / 9 Control Slot / 13 原语群分类学 / 6 维 LogicAddress（软约束） / 11 关系代数 / 6 contribution verbs / PluginContract 概念 / plan_ref × Journal 绑定 / CommandEnvelope 唯一 effect 入口。**

## 背景

ADR-0066 / 0067 / 0068 / 0069 由同一作者（远程 `smartlijingyang-sudo`）在 2026-08-21 12:34–13:13 UTC 三连 commit 提交（`a1b5496a` / `4f59338b` / `9d913a6c`），与代码对齐架构审计文档（`docs/design/2026-08-21-code-aligned-architecture-audit.md`）同步发布。审计明确指出当前 LCA 已具备 Manifest / Resolve / Cordis Fiber / PerceiveHub / Tool Pipeline / Composer / Creator 等基础设施，但**核心运行语义仍分散在 `spawn.py` / `runtime_loop.py` / `ModularBrain` / `ActionCatalog` / gateway helper 中**——插件存在但控制面由 Python 硬编码。

四篇 ADR 共同给出"plugin-everything"路线的下一阶段答案：

| ADR | 核心洞见 | 过度工程部分 |
|---|---|---|
| 0066 | 9 Control Slot + 单调聚合 deny-on-any-deny | — |
| 0068 | CompiledRunPlan = CapabilityPlan + ControlPlan + ScopePlan | — |
| 0067 | 时空与生命周期 owner 分离 | 5 子空间 SpacetimeContext / 8 状态机 / 7 Creator 面 / 6 道闸 |
| 0069 | 6 contribution verbs（collect/select/transform/veto/execute/project） | 13 原语群 / 6 维 LogicAddress / 11 关系代数 |

本地已落地 ADR-0070（Reducer-as-Plugin）与 ADR-0072（Null-Default），证实 0066 / 0068 的核心洞见可在不破坏 v3 宪法的前提下逐步落地。本计划承接这四篇 ADR 的核心，接受 0066 / 0068、裁剪 0067、推迟 0069，并整合本地 0070–0073。

## 第一性原理判定

### 接受（核心优雅）

1. **CompiledRunPlan 是单一不可变真理**（0068 §一）：plan_hash × plan_version × plan_ref 三元组让任何运行可独立解释，与 v3 宪法 §3.4 Journal-as-Truth 自然叠加
2. **9 个 Control Slot 是认知闭集 + 控制面的最小完备划分**（0066 §二）：覆盖宪法原语边界，少一即漏，多一即回归 hook soup
3. **6 contribution verbs 是封闭动词表**（0069 §四）：任何插件行为都映射到 collect / select / transform / veto / execute / project
4. **plan_ref × Journal 绑定**（0068 §一）：每条事实可解释，每条事实可重放
5. **CommandEnvelope 是 effect 唯一入口**（0068 §五）：Decision 不是 Command，5 道闸单调
6. **Capability 衰减 + 单调聚合**（0066 §四）：安全语义由数学保证
7. **13 原语群分类学**（0069 §一）：G0 Constitution / G1 Identity / G2 Spacetime / G3 Facts / G4 Perception / G5 Cognition / G6 Decision / G7 Execution / G8 Collaboration / G9 Interaction / G10 Composition / G11 Creation / G12 Evidence——13 个分类轴为插件提供归属坐标，**作为分类学而非强制门禁**（PluginManifest 可选 `functional_group` 字段，linter 警告不阻断）
8. **6 维 LogicAddress**（0069 §二）：FunctionalGroup × ControlSlot × Scope × Authority × Evidence × Revision——每个生产逻辑的完整地址。**作为 PluginManifest 可选元数据 + linter 警告**（不是 hard error）
9. **11 关系代数**（0069 §三）：provides / requires / contributes_to / reads_fact / emits_fact / governs / executes / delegates / projects / revises / evaluates。**完整接受**，capability DAG 扩展至覆盖 11 种关系；governs / projects / revises 三种观察关系作为 CapabilityPlan 字段
10. **PluginContract 概念**（0069 §六）：identity / contribution / consumes / produces / authority / scope / lifecycle / evidence / verification 9 段——**不替换 PluginDefinition**，作为可选 typed section 并存

### 裁剪（仅 ADR-0067 部分）

1. **8 状态机 → 4 状态机**（0067 §四）：PARSED / DECLARED 是 VERIFIED 的子步骤（合并到 DRAFT）；QUIESCING 是 ACTIVE 的退出协议（不是独立状态）；ROLLED_BACK 是 RETIRED 的子分支（合并）。最终：`**DRAFT / VERIFIED / ACTIVE / RETIRED**`。Lab HMR 与 Production Promotion 是部署模式而非状态
2. **7 Creator 面 → 4 Creator 面**（0067 §七）：stage 是 promote(target_scope=experiment) 的别名；retire 是 promote(rollback=True)；publish 是 promote(target_scope=release)。最终：**`inspect / author / validate / promote`**
3. **6 道闸 → 3 道关键闸**（0067 §五）：identity / manifest / capability / invariant / evidence / experiment 六道闸中，invariant + experiment 是核心，identity + manifest + capability 是其子条件。合并为 **`identity / invariant / experiment`** 三道闸（identity 含 manifest 校验，invariant 含 capability / effect / scope 单调性，experiment 含 evidence）
4. **5 子空间 SpacetimeContext → 2 子空间**（0067 §一–§三）：仅实现 `ExecutionSpace`（run 局部执行环境） + `LifecycleSpace`（process / profile / agent / run 生命周期）两个最急子空间；`TemporalContext` / `IdentitySpace` / `VisibilitySpace` 进 ADR Draft 待 owner 协调规则明文化后实现

## 决策

### 一、接受 ADR-0066 核心：11 Control Slot + 单调聚合

完整接受 ADR-0066 §二 Control Slot 定义及 ADR-0074 tracker §19 的 `observe.checkpoint` / `act.safe-boundary` 补充、§三（Manifest control 段三件套：identity / authority / effects）、§四（单调聚合 deny-on-any-deny / deny-on-exhausted / stop-on-any-stop / decision-priority / scope-只收紧）、§七（capability / budget / constraint / approval / stop 的策略-事实-强制点三分）。每个 CompiledRunPlan 必须闭合覆盖 11 槽；未被具体 plugin 声明的槽位由类型化 no-op 投稿承接。

标准 profile 以 12 条具体 ControlEntry 覆盖 11 个槽位：`perceive` 提供 `perceive.context`，两个 think gate 提供 `think.guard`，`body.simple` 提供五个 `act.*` 槽位，`lca-memory-provider` 提供 `remember.admit`，`stop_rule.default` 提供 `stop.decide`，`hook_registry.simple` 提供两个 `observe.*` 槽位。多槽插件以稳定的 `contribution_id` 生成唯一 ControlEntry 身份；标准计划不得退化为 `control.default.*` 投稿。

`DefaultControlPolicyEngine` 仅以阶段已物化的 State、Decision、Observation、Reflection 与 checkpoint reason 生成 verdict。`CognitiveRuntime` 通过 `aggregate_control_verdicts` 消费 verdict：deny 或 exhausted 生成失败 Observation 并跳过 Body，stop 在感知、思考或行动边界经 Reducer 立即结束 run，记忆准入拒绝则跳过 MemorySystem.update。`no_aggregate` 槽位保留所有独立 verdict，同时任何 deny、exhausted、ask_human 或 stop verdict 仍阻断所属阶段。

裁剪 §五 Composer 与 §六 ControlPlan 描述——L4 Composer 拆为 4 个 sub-composer plugin 移交给本地 ADR-0071（Composer-per-Cluster）。

**实施映射**：PR-1 / PR-2 / PR-3 直接对应该 ADR 的 PR-2 / PR-3 / PR-4。

### 二、接受 ADR-0068 核心：CompiledRunPlan = CapabilityPlan + ControlPlan + ScopePlan

完整接受 ADR-0068 §一（三子 plan 架构）、§二（PluginContract 概念但**不替换 PluginDefinition**，仅在 §六中合并）、§五（CommandEnvelope 是 effect 唯一入口）。

裁剪 §六（Boot 双轨消除）—— Boot 双轨由 [ADR-0062 PR-3/PR-4](0062-plugin-runtime-cleanup.md)（commit `e0eb2484`）落地，本计划不重复此工作。**注：ADR-0070（Reducer-as-Plugin，`eca3966b`）仅收口 `_loop` 内的中间产物（`_emit` / `middleware_bag` / `SEAM_TO_HOOK` / `HOOK_SEAMS`），未触及 Boot 双轨；上文 2026-08-21 初稿的转述不实，以此补丁为准。**

裁剪 §七（ArtifactController）—— 见本计划 §四。

**实施映射**：PR-4 / PR-5 / PR-6 / PR-7 直接对应该 ADR 的 PR-3 / PR-7 / PR-2 / PR-5。

### 三、裁剪 ADR-0067：4 状态机 + 4 Creator 面 + 双子空间

| 0067 原文 | 本计划裁剪 | 理由 |
|---|---|---|
| 8 状态机（DRAFT/PARSED/DECLARED/VERIFIED/STAGED/ACTIVE/QUIESCING/RETIRED + ROLLED_BACK） | **4 状态机：DRAFT / VERIFIED / ACTIVE / RETIRED** | 真实状态迁移只有"未就绪/已校验/已激活/已退役"四态；中间步骤是校验子流程 |
| 6 道闸（identity/manifest/capability/invariant/evidence/experiment） | **3 道闸：identity / invariant / experiment** | manifest ⊂ identity；capability + effect + scope ⊂ invariant；evidence ⊂ experiment |
| 7 Creator 面（inspect/author/validate/stage/promote/retire/publish） | **4 Creator 面：inspect / author / validate / promote** | stage = promote(experiment)；retire = promote(rollback)；publish = promote(release) |
| 5 子空间 SpacetimeContext | **2 子空间：ExecutionSpace + LifecycleSpace** | TemporalContext / IdentitySpace / VisibilitySpace 推迟为 ADR Draft；先实现最急的"在哪执行"与"活多久" |
| 7 scope（experiment/invocation/turn/run/agent/profile/release） | **5 scope（保留全部但合并 invocation → turn）** | invocation 与 turn 在执行面无实质区分；scope 闭集压缩到 5 |

**实施映射**：PR-8 / PR-9 直接对应。

### 四、接受 ADR-0069 全文：13 群分类学 + 6 维 LogicAddress + 11 关系代数 + PlanTemplate

完整接受 ADR-0069 全文作为**分类学层**（不是强制门禁层）：

- **13 原语群**（0069 §一）：G0 Constitution / G1 Identity / G2 Spacetime / G3 Facts / G4 Perception / G5 Cognition / G6 Decision / G7 Execution / G8 Collaboration / G9 Interaction / G10 Composition / G11 Creation / G12 Evidence
  - 实现：`lca/contracts/atoms/functional_group.py` 枚举
  - PluginManifest 新增 `functional_group: FunctionalGroup | None` 字段
  - `lca plugin check` 输出该 plugin 的原语群归属（warning 而非 error）

- **6 维 LogicAddress**（0069 §二）：FunctionalGroup × ControlSlot × Scope × Authority × Evidence × Revision
  - 实现：`lca/contracts/protocols/logic_address.py` dataclass（6 维全 optional）
  - PluginManifest 新增 `logic_address: LogicAddress | None` 字段
  - `lca plugin check` 输出 LogicAddress 完整度评分；缺失字段 warning，**不阻断**
  - Profile 级可覆盖 LogicAddress 字段（patch 机制延伸）

- **11 关系代数**（0069 §三）：provides / requires / contributes_to / reads_fact / emits_fact / governs / executes / delegates / projects / revises / evaluates
  - 实现：`lca/contracts/atoms/relation.py` 枚举（11 项）
  - CapabilityPlan 关系字段扩展至 11 种；当前 ADR-0061 已覆盖 5 种（provides / requires / contributes_to / reads / emits），新增 6 种：governs / executes / delegates / projects / revises / evaluates
  - 关系在 Manifest 中显式声明；Resolve 期验证

- **PlanTemplate = Agent 模式**（0069 §五）：RAG / prompt chain / routing / parallel / orchestrator-workers / evaluator-optimizer / tool-using loop / HITL / team / scheduled / realtime / self-evolving 都是 13 群与 11 关系的组合模板
  - 通过 Profile Bundle + Patch 表达（不引入新概念）
  - ADR-0042 角色库机制即 PlanTemplate 实例
  - `lca-ops plan list-templates` 输出当前可用的 PlanTemplate 列表

- **PluginContract 概念**（0069 §六）：identity / contribution / consumes / produces / authority / scope / lifecycle / evidence / verification 9 段
  - **不替换 PluginDefinition**，作为可选 typed section 并存
  - PR-2 中 `PluginManifest` 增加可选 `contract: PluginContract | None` 字段

**实施映射**：PR-2 扩展（接受 FunctionalGroup + LogicAddress + PluginContract 可选段）；新增 PR-11（11 关系代数扩展 CapabilityPlan）；PR-12（PlanTemplate 列表工具）。

### 五、整合本地 ADR-0070–0073

| 本地 ADR | 状态 | 与本计划关系 |
|---|---|---|
| 0070 Reducer-as-Plugin | ✅ 已落地（`eca3966b`） | 本计划 RuntimeKernel / `_loop`（新 PR-3 + PR-7）通过 `_loop` 直接消费其 Reducer Protocol；C4 由 PR-0 audit state-writers + PR-7 收口 effect 守护 |
| 0071 Composer-per-Cluster | ⏳ Proposed | 与本计划并行：4 sub-composer plugin（perceive_composer / think_composer / act_composer / compose_composer）作为 PR-5 的前置依赖 |
| 0072 Null-Default Discipline | ✅ 已落地（`26bf0aaf`） | 本计划 PR-2 引用其 Null 实现家族（NullCritic / NullSynthesizer / NullRetrievalPolicy） |
| 0073 Session Path Convergence | ⏳ Proposed | 与本计划并行：SessionService Protocol 统一 `/runs` 与 `/v1/sessions`；PR-7 集成 |

**实施映射**：PR-5（spawn.bind_plan）依赖 ADR-0071；PR-7（CommandEnvelope 收口）依赖 ADR-0073。

## 实施序列（14 PR）

> **修订说明（2026-08-21 review）：**
> 1. **PR-3 ↔ PR-4 互换**：原 PR-3（think.guard / stop.decide 原子化）依赖 ControlPlan，但原 PR-4（CompiledRunPlan + PlanCompiler）才是 ControlPlan 的编译入口。把 PR-3 放到 PR-4 之后可避免把 ControlPlan 字符串写死在 gate 代码里。
> 2. **PR-11 前移为 PR-2.5**：11 关系代数是 CapabilityPlan 的数据面扩展，与 PR-2 (PluginDefinition.control) 同属"声明能力"层。把它前置让 PR-3 (CompiledRunPlan) 直接基于 11 关系表达 governance，避免后期返工。
> 3. **PR-0.5 新增**：22 个 pre-existing 测试失败原计划置于外部风险，但实际是本计划的硬阻塞（PR-1 起步即会被这 22 个失败拖累 CI）；并入计划。

### PR-0 测量网

| 项 | 内容 |
|---|---|
| 目标 | 让 reviewer 一行命令看清当前 hardcode 在哪 |
| 新增 | `lca-ops audit control-surface` / `audit state-writers` / `audit direct-commands` / `audit hook-attach` |
| 文件 | `lca/harness/diagnostics/audit_*.py`（新增 4 个）、`scripts/lca-ops`（新增子命令） |
| 验证 | `uv run pytest tests/harness/test_audit_*.py` |
| 删除 | 无 |

### PR-0.5 清 22 个 pre-existing 测试失败（硬阻塞前置）

| 项 | 内容 |
|---|---|
| 目标 | 在 PR-1 起步前清空历史测试债（journal v2 envelope 错配 / DSH 删除遗留 / plugin context boot 三类） |
| 范围 | 仅修复，不重构；与本计划无直接耦合的失败另起 ADR |
| 验证 | `uv run pytest --no-cov` 零失败（已知 flaky test 除外） |
| 删除 | 无（仅修测试 fixture / env / 注释漂移） |

### PR-1 ControlSlot + ControlPlan 数据面

| 项 | 内容 |
|---|---|
| 目标 | 9 个槽位有限枚举 + ControlPlan dataclass + Resolver 投影（不动运行时） |
| 新增 | `lca/contracts/atoms/control_slot.py`（9 项枚举）、`lca/contracts/protocols/control_plan.py`（ControlEntry / ControlPlan）、`lca/harness/profile/control_plan_resolver.py` |
| 验证 | 现有 profile 都能产出 ControlPlan（golden test） |
| 删除 | 无 |

### PR-2 PluginDefinition.control 可选段

| 项 | 内容 |
|---|---|
| 目标 | plugin 作者能声明自己投到哪个 slot（完全可选，不填则行为不变） |
| 新增 | `PluginDefinition.control: list[ControlEntry] \| None = None`、`lca-ops lint plugin <id>` |
| 迁移 | `repeat_tool_call` / `stop_rule` / `decision_gate` 立即填 control，其余 plugin 渐进 |
| 删除 | 无 |

### PR-2.5 11 关系代数扩展 CapabilityPlan

| 项 | 内容 |
|---|---|
| 目标 | CapabilityPlan 关系字段扩展至 11 种（ADR-0069 §三），让后续 PR-3 CompiledRunPlan 直接基于 11 关系表达 governance |
| 新增 | `lca/contracts/atoms/relation.py`（11 项枚举）、`lca/contracts/protocols/relation.py`（Relation dataclass 含 source / target / kind / evidence） |
| 修改 | `lca/harness/profile/resolve.py` 解析 11 种关系；`CapabilityPlan` 增加 `relations: list[Relation]` 字段 |
| 验证 | 现有所有 profile 关系字段通过解析；新关系（governs / executes / delegates / projects / revises / evaluates）通过 Resolve 验证 |
| 删除 | 无 |
| 注 | 关系图谱可视化（`lca-ops plan relations`）保留到 PR-12，本 PR 只交付数据面 |

### PR-3 CompiledRunPlan + PlanCompiler（中央产物立起来）

| 项 | 内容 |
|---|---|
| 目标 | 实现 `CompiledRunPlan = CapabilityPlan + ControlPlan + ScopePlan`，profile 编译为不可变对象；含 11 关系代数（PR-2.5）支持 |
| 新增 | `lca/contracts/protocols/plan.py`（CompiledRunPlan frozen dataclass + plan_ref hash）、`capability_plan.py`（扩展 11 relations）、`scope_plan.py`（最小版：lifecycle + visibility + ACL + budget ceiling，无 SpacetimeContext 5 子空间）、`lca/harness/profile/plan_compiler.py` |
| 修改 | `lca/harness/profile/resolve.py` 增加 `compile_plan()`；默认走新路径，保留 `LCA_PLAN_COMPAT=1` 兼容开关 |
| 验证 | plan_hash 确定性（同一输入 → 同一 hash）；所有现有 profile 可编译；`lca-ops plan inspect <profile>` |
| 删除 | 无（老路径保留 3 个 PR 后删除） |

### PR-4 think.guard / stop.decide 原子化（首次迁移）

| 项 | 内容 |
|---|---|
| 目标 | 已有 gate 链改为向 ControlPlan 的 Control Slot 投稿（PR-3 后 ControlPlan 已编译，可静态表达） |
| 修改 | `lca/layer1_cognitive/brain/modular_brain.py`（去内嵌 gate 引用，调用 `think.guard` registry）、`lca/layer2_runtime/stop_rule.py`（改为向 `stop.decide` 投稿） |
| 验证 | e2e agent run 决策 / stop 行为字节级一致 |
| 删除 | `ModularBrain._gate_chain` 字段；`repeat_tool_call` 特殊路径 |

### PR-5 spawn.bind_plan（L4 失忆）

| 项 | 内容 |
|---|---|
| 目标 | `spawn_agent` 不再自己造对象图，只绑定 plan + 上下文 |
| 修改 | `lca/layer4_app/spawn.py` 拆为 `bind_plan(ctx, plan)` + `_legacy_spawn_objects()`（deprecated）；`RuntimeDeps` 用 `compiled_plan` 替换散落的 factory 字段；L4 不再 import 具体插件 ID |
| 前置依赖 | ADR-0071（Composer-per-Cluster）先落地，提供 4 个 sub-composer plugin；BrainFactory 入参改为 keyword-only 或 `BrainInputs` dataclass（避免 sub-composer 接口漂移） |
| 验证 | `grep "control.authorize\|simple_body\|default_factory" lca/layer4_app/` 为 0 hit；e2e 跑通 1 个标准 agent（golden profile） |
| 删除 | `spawn.py` 中所有 `default_factory.*` 字符串引用 |

### PR-6 plan_ref × Journal 绑定

| 项 | 内容 |
|---|---|
| 目标 | 每个 Journal fact 携带 plan_ref |
| 新增 | `EventMeta.plan_ref: str` 字段；emit 时从 RunContext 注入 |
| 修改 | `lca/contracts/models/observability/event_descriptor.py` —— descriptor 必须声明 plan_ref 字段 |
| 验证 | replay test：任意 run 重放可重建 plan |
| 删除 | 无 plan_ref 的旧 event descriptor（如有） |

### PR-7 RunFact / CommandEnvelope 收口

| 项 | 内容 |
|---|---|
| 目标 | 外部世界 effect 必经 `command.plan → authorize → budget → constrain → execute` 5 道闸 |
| 新增 | `lca/contracts/protocols/command.py`（CommandEnvelope frozen dataclass）、`lca/contracts/protocols/run_fact.py`（RunFact / RunDelta / Verdict / Decision union）、`lca/layer1_cognitive/body/command_envelope.py`（mint_envelope 工厂） |
| 修改 | `lca/layer1_cognitive/body/pipeline_safe_executor.py` —— 每次执行先 mint CommandEnvelope；删除 Body 内部临时 envelope mint |
| 前置依赖 | ADR-0073（Session Path Convergence）提供 SessionService Protocol 统一面 |
| 验证 | 任何 Body.execute 在 stack trace 看到 `command_envelope.mint`；architecture test 拒绝无 envelope 的 tool call |
| 删除 | 直接调用 sandbox 的 bypass |

### PR-8 ArtifactController（4 状态机）

| 项 | 内容 |
|---|---|
| 目标 | 8 状态压成 4 状态：`DRAFT / VERIFIED / ACTIVE / RETIRED` |
| 新增 | `lca/contracts/atoms/artifact_state.py`（4 项枚举）、`lca/contracts/protocols/artifact.py`（CapabilityArtifact 含 logical_id / revision_digest / state / scope / grants）、`lca/layer4_app/composition/artifact_controller.py`（状态迁移 API） |
| 修改 | `lca/plugins/tools/cordis_control/` —— mount/unmount 改为 ArtifactController 调用 |
| 验证 | 状态机 property test：合法迁移 / 非法迁移覆盖；lab HMR 与 production promotion 用同一状态机、不同路径 |
| 删除 | STAGED / QUIESCING / PARSED / DECLARED 状态；旧 8 状态机代码路径 |

### PR-9 Creator 4 面化

| 项 | 内容 |
|---|---|
| 目标 | 7 Creator 面压成 4 面：`inspect / author / validate / promote` |
| 新增 | `lca/plugins/creator/faces/{inspect,author,validate,promote}.py` |
| 修改 | `lca/plugins/tools/cordis_control/tool.py` —— CordisControlTool 委托到 4 面；retire 合并到 promote(rollback=True)；publish 合并到 promote(target_scope=release)；stage 是 promote(target_scope=experiment) 的别名 |
| 验证 | 现有 Creator 工具测试逐个迁移到 4 面 |
| 删除 | stage / retire / publish 3 个独立面 |

### PR-10 Golden profile + 文档更新

| 项 | 内容 |
|---|---|
| 目标 | "配置可阅读、运行可证明"落到 golden 文件 + 宪法 v3.1 引用 |
| 新增 | `tests/golden/profiles/*.yaml`（标准 agent / team / coding agent 各 1 个）、`tests/golden/control_plans/*.json`、`tests/golden/plans/*.json` |
| 修改 | ADR-0067 状态：Proposed → Superseded (part)（由 0074 转 Accepted 时同步生效）；`docs/adr/README.md` 更新；引用 [`v3.1 宪法补丁`](../design/2026-08-21-cognitive-primitive-constitution-v3-1.md) §1 / §2 收口 |
| 验证 | golden 测试覆盖 plan hash 跨运行一致；回归测试全过 |
| 删除 | 过期中间设计稿 |

### PR-12 PlanTemplate 列表工具 + 关系图谱可视化

| 项 | 内容 |
|---|---|
| 目标 | 把 Agent 模式（12 种 PlanTemplate）的可发现性 + 11 关系图谱可视化落到 CLI |
| 新增 | `lca-ops plan list-templates`（列出当前可用的 PlanTemplate ）、`lca-ops plan relations <plugin_id>`（输出某 plugin 的关系图谱，使用 PR-2.5 的 11 关系数据）；`tests/golden/plan_templates/*.yaml`（标准 PlanTemplate：rag / prompt_chain / routing / parallel / orchestrator_workers / evaluator_optimizer / tool_using_loop / hitl / team / scheduled / realtime / self_evolving 各 1 个） |
| 验证 | 12 个 PlanTemplate golden 测试；关系图谱可视化与 Manifest 一致 |
| 删除 | 无 |

## 验证约束

| 编号 | 约束 | 自动化证据 |
|---|---|---|
| **V1** | 控制面单一入口 | `lca-ops explain control <slot>` 列出该 slot 的所有 entry、来源 bundle/patch、order、activation 表达式；运行循环仅经统一聚合器评估 11 槽的激活投稿与 typed verdict |
| **V2** | CompiledRunPlan 确定性 | 同 profile × TaskContract × Environment → 同 plan_hash；回归测试守护 |
| **V3** | Reducer 唯一写 State | `lca-ops audit state-writers` 输出空集（除 reducer）；22 个 pre-existing failure 全部清零 |
| **V4** | CommandEnvelope 必经 5 闸 | architecture test 拒绝无 envelope 的 tool call；Body.execute stack trace 必含 `command_envelope.mint` |
| **V5** | plan_ref 全覆盖 | replay test 取任意 run，重放其 journal 即可重建 plan |
| **V6** | 4 状态机封闭 | state migration property test：合法迁移覆盖；非法迁移抛 InvalidStateTransition |
| **V7** | Creator 4 面化 | `lca-ops creator --help` 输出 4 个 subcommand；stage / retire / publish 通过 promote flags 实现 |
| **V8** | capability 单调 | 子代理 / 子 scope / 子 artifact grant ⊆ 父；违反时 Resolve / Run fail-closed |
| **V9** | LogicAddress 完整度 | `lca plugin check` 输出 LogicAddress 6 维完整度评分（定义见下）；缺字段 warning 不阻断 |

**V9 LogicAddress 完整度评分定义：**

| 评分维度 | 满分 | 评分条件 | 备注 |
|---|:-:|---|---|
| FunctionalGroup 命中已知群 | 25 | LogicAddress.functional_group ∈ v3 8/9 群 ∪ ADR-0069 13 群并通过 `lca plugin check` 映射 | 缺 = 0；映射失败 = 0 |
| ControlSlot 命中已知槽 | 25 | LogicAddress.control_slot ∈ ADR-0066 §二 9 槽位 | 缺或未命中 = 0 |
| Scope 在合法 ScopeGraph | 25 | LogicAddress.scope ∈ {release, profile, agent, run, turn, invocation, experiment, device}（8 个合法 scope） | 缺或越界 = 0 |
| Evidence descriptor 已登记 | 25 | LogicAddress.evidence 对应 EventDescriptor 已存在于 Journal catalog | 缺 = 0 |

- **总分 ≥ 75**：warning（LogicAddress 良好）
- **总分 50–74**：warning（LogicAddress 部分完整）
- **总分 < 50**：warning（LogicAddress 缺失严重）
- **缺字段不阻断 PR 合并**；`lca plugin check --strict` 才报错退出码 1
| **V10** | 13 原语群覆盖 | `lca plugin check` 输出每个 plugin 的 functional_group 归属；缺失 warning |
| **V11** | 11 关系代数 | CapabilityPlan.relations 解析通过；6 种新关系（governs/executes/delegates/projects/revises/evaluates）覆盖；`lca-ops plan relations` 图谱输出 |
| **V12** | PlanTemplate 可发现性 | `lca-ops plan list-templates` 输出 12 个标准 PlanTemplate；golden 测试覆盖 |

## 与 v3 / v3.1 宪法的兼容性

| 宪法条款 | 本计划触碰 | 说明 |
|---|---|---|
| C1 六步闭集 | 否 | PR-3 (CompiledRunPlan) 引用 v3.1 §2 C1.1 闭集内部细化；PR-4 think.guard / stop.decide 在已有阶段内投稿 |
| C2 双平面 | 否 | ADR-0070 已落地；本计划 §二直接引用 |
| C3 Journal 唯一事实 | 加强 | PR-6 加 plan_ref 字段 |
| C4 Reducer 唯一写 | 加强 | `audit_state_writers` 仅识别类型化 `AgentState` 的真实变更；局部同名字典与只读调用不计入违规，所有检索上下文经显式返回值而非直接状态写入 |
| C5 Capability 衰减 | 否 | PR-5 / PR-8 维持；V8 守护 |
| C6 改闭集必 ADR | 本计划本身就是新 ADR | 0066 / 0067 / 0068 / 0069 接受/裁剪流程由本计划 §一/§二/§三/§四 显式记录 |
| C7 原语默认 no-op | 间接加强 | ADR-0072 已落地 Null 实现家族；本计划 §二引用 |
| **v3.1 §1 双层分类** | 显式引用 | ADR-0069 13 群由本计划 §四收口为扩展分类学；8/9 群保持宪法原语基础集地位 |
| **v3.1 §2 C1 闭集细化** | 显式引用 | ADR-0068 §三运行时序图由 v3.1 §2 C1.1 接受为 C1 内部细化 |

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 22 个 pre-existing 测试失败 | **已并入 PR-0.5**（独立 PR、1 周、与本计划主路径并行可启动） |
| PR-3 CompiledRunPlan 大改 | 老路径保留 `LCA_PLAN_COMPAT=1` 开关 3 个 PR 后删除 |
| PR-5 spawn 重写 breakage | 仅在 dev profile 启用；golden test 守护 |
| PR-8 状态机收敛期 cordis_control 用户受损 | 8→4 状态通过迁移映射 6 个月兼容 |
| PR-9 Creator 4 面化对老调用方 | `lca-ops creator stage/retire/publish` 通过 promote subcommand 软链接 6 个月 |
| 本地 ADR-0071 / 0073 阻塞 PR-5 / PR-7 | 在 PR-5 之前完成 0071（4 sub-composer）；在 PR-7 之前完成 0073（SessionService Protocol） |
| **PR-4 think.guard 迁移前置依赖** | **PR-3 (CompiledRunPlan) 必须先于 PR-4 完成**，否则 ControlPlan 字符串写死在 gate 代码里；本计划已重排顺序 |
| **PR-2.5 11 关系前移** | 让 PR-3 CompiledRunPlan 直接基于 11 关系表达 governance；可视化保留到 PR-12 |

## 时间线（1 人 + 1 reviewer，16 周）

```
W1    PR-0 测量网
W2    PR-0.5 清 22 个 pre-existing 测试失败（与 PR-0 完成后并行可启动）
W3-4  PR-1 ControlSlot + ControlPlan 数据面
W5    PR-2 PluginDefinition.control 可选段
W5.5  PR-2.5 11 关系代数扩展 CapabilityPlan（PR-2 末尾插入）
W6-7  PR-3 CompiledRunPlan + PlanCompiler（前置：PR-2.5 已完成）
W8    PR-4 think.guard / stop.decide 原子化（前置：PR-3 已完成）
W9    PR-5 spawn.bind_plan（前置：ADR-0071 已落地）
W10   PR-6 plan_ref × Journal 绑定
W11   PR-7 RunFact / CommandEnvelope 收口（前置：ADR-0073 已落地）
W12   PR-8 ArtifactController（4 状态）
W13   PR-9 Creator 4 面化
W14   PR-10 golden + 文档 + ADR 状态更新
W15-16 PR-12 PlanTemplate 列表工具 + 关系图谱可视化
```

## 放弃的方案

| 方案 | 否决理由 |
|---|---|
| 全量接受 0066–0069 全文（含 ADR-0067 8 状态机） | ADR-0067 8 状态机 + 7 Creator 面 + 5 Spacetime 子空间过度工程；落地周期翻倍；cog load 超限 |
| 只做 ADR-0070 / 0072 已落地部分就停 | 核心洞见（CompiledRunPlan / ControlPlan）未兑现；6 步循环 + 控制面分离的目标未达成 |
| 用 PluginContract 一次性替换 PluginDefinition | breaking change 涉及所有 profile + bundle + patch；blast radius 不可控 |
| 强制 LogicAddress 6 维为 lint 阻断 | 小工具插件作者挫败感强；6 维表格是过度摩擦。本计划改为"完整度评分 + warning"，尊重 0069 的分类学意图 |
| 保留 5 子空间 SpacetimeContext | owner 间协调规则未明文化；过早引入会形成第二处隐式编排 |
| 推迟 ADR-0069 全文为 ADR Draft | 13 群分类学与 6 维 LogicAddress 作为软约束（warning 而非 error）即可落地；不应放弃 ADR-0069 的概念语法层 |

## 相关

- **Refines**: [ADR-0066](0066-declarative-atomic-control-plugins.md)、[ADR-0068](0068-compiled-plugin-kernel-and-unified-run-plan.md)、[ADR-0069](0069-agent-primitive-system-and-declarative-grammar.md)
- **Supersedes (partially)**: [ADR-0067](0067-spacetime-runtime-and-governed-creation.md)
- **Co-evolves**: [ADR-0065](0065-recoverable-evidence-ledger.md)、[ADR-0063](0063-run-trace-ssot.md)、[ADR-0070](0070-reducer-as-plugin.md)、[ADR-0072](0072-null-default-discipline.md)
- **并行**: [ADR-0071](0071-composer-per-cluster.md)、[ADR-0073](0073-runsession-sole-session-path.md)
- **Keeps**: ADR-0001 / ADR-0002 (Superseded by v3 constitution) / ADR-0004 / ADR-0005 / ADR-0015 / ADR-0033 / ADR-0034 / ADR-0037 / ADR-0056 / ADR-0061 / ADR-0062
- **依赖宪法补丁**: [v3.1 双层分类 + C1 闭集细化](../design/2026-08-21-cognitive-primitive-constitution-v3-1.md)
- **背景**: [代码对齐架构审计](../design/2026-08-21-code-aligned-architecture-audit.md)、[认知原语宪法 v3](../design/2026-08-19-cognitive-primitive-constitution-v3.md)