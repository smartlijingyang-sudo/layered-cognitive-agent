# ADR-0066–ADR-0076 全面落地实施计划

## 1. 计划目标与基线

本计划以远程 `main` 分支提交 `74f71e10` 为基线，覆盖 ADR-0066、ADR-0067、ADR-0068、ADR-0069、ADR-0074、ADR-0075 和 ADR-0076 的代码、测试、运行时接线、替换性门禁和文档一致性。目标不是增加另一套架构，而是把当前已存在的声明式计划链收敛为**单一生产路径、单一事实源、单一能力绑定和可验证替换**。

本轮只生成实施计划，不直接实施计划中的代码。所有阶段完成后才能宣称相关 ADR 达到 sign-off；局部测试通过不得替代全量验证。

> **当前结论：核心数据面已经落地，但整体尚未完成。** 当前远程代码已经具备 `CompiledRunPlan → GraphAssembler → GenericPlanInterpreter → RuntimeEffectGateway` 主链，并已落地 ADR-0076 的六平面、team seam、run mode registry、boot binding validator 和 action authority plan-data 迁移。仍有运行时结果传播、默认回退、证据持久化、协议继承、类型安全、全量回归和文档状态不一致等缺口。

### 1.1 当前可复现基线

| 检查项 | 当前结果 | 判定 |
|---|---:|---|
| 全量 `uv run pytest --no-cov -q` | 2783 passed，31 failed，18 skipped，16 deselected，10 subtests passed | 未通过 |
| ADR-0076 结构/替换/Composer/boot 专项 | 98 passed | 局部通过 |
| ADR-0066–0069/0074/0075 核心专项 | 522 passed，2 failed | 有运行时回归 |
| `scripts/check_adr_supervision.py` | 通过 | tracker 一致 |
| `scripts/route_legacy_patterns.py --json` | `total=0` | 历史迁移基线已清零 |
| `scripts/check_plugin_typing.py` | 通过 | 插件入口标注通过 |
| `scripts/check_protocol_impl.py` | 19 处失败 | 必须修复 |
| `scripts/check_no_any.py` | 244 处命中 | 必须按影响范围清理 |
| `uv run mypy lca` | 166 errors / 46 files | 必须分层收敛 |
| `uv run ruff check .` | 需按基线重新复核 | 作为最终门禁 |
| `uv run lint-imports` | 需按基线重新复核 | 作为最终门禁 |
| `scripts/verify_md_links.py` | 通过 | 文档链接可解析 |
| `scripts/verify_doc_budgets.py` | `AGENTS.md` 超 368 词，`docs/adr/README.md` 超 6 词 | 既存文档门禁失败 |

### 1.2 已关闭的事项

上一轮审计中的以下问题已经由后续提交部分或全部关闭，后续不得重复实现：

| 已关闭事项 | 当前证据 |
|---|---|
| ADR-0076 action authority 进入 plan-data | `plan.action_authority`、`AgentCompositionRequest.allowed_actions/forbidden_actions`、`test_action_authority_plan.py` |
| BodyComposer 不再依赖静态 `_SCOPE_ACTIONS` 选择生产 action | `plan_composers.py` 的 `_build_action_registry_from_authority` 与 Composer 测试 |
| PerceiveComposer stop-rule 选择进入 request/plan | `request.spec.stop_rule` |
| TeamComposer 使用 `team_seam` | `tests/composer/test_composer_consumes_compiled_capability.py` |
| Gateway mode registry | `run_mode_registry`、mode adapters、`test_run_mode_registry.py` |
| 生产 binding closure | `RuntimeBindingValidator`、`MissingBindingError`、`test_boot_binding_completeness.py` |
| L2 默认实现 plugin 注册 | `DefaultReducer`、`ClosedSetTopology`、`DefaultStopRule` 的 `@plugin` |
| 11 个 DeltaHandler 数据面 | `delta_handlers.py` 与对应 registry |

## 2. ADR 条款到实现的完整差距矩阵

### 2.1 ADR-0066：Declarative Atomic Control Plugins

| 条款 | 当前状态 | 未完成工作 | 验收证据 |
|---|---|---|---|
| 9 个 Control Slot 及扩展槽位闭集 | 已落地 | 维护枚举闭集，新增槽位必须先 ADR | `tests/harness/test_control_slot.py` |
| `PluginDefinition.control` 三件套 | 已落地 | 检查生产 plugin manifest 完整性 | `tests/harness/test_plugin_optional_fields.py` |
| deny-on-any-deny、stop-on-any-stop、scope 收紧 | 已落地 | 增加运行时拒绝/停止/重写组合的动态 property test | `tests/harness/test_control_plan_resolver.py`、control contribution tests |
| Composer / ControlPlan 描述 | 已落地 | 清理遗留 direct control map 和隐式默认 | `tests/plan/test_plan_compiler.py` |
| 策略、事实、强制三类决策点 | 核心已落地 | 将旧测试从 `_loop` 直接调用迁移到声明式 control contribution 证据 | `tests/harness/test_c1_phase_substeps_guard.py` |
| Reducer 唯一写 State | 静态基线已清零 | 全量运行、trace、HIL 路径仍需证明无旁路 | `route_legacy_patterns.py`、全量测试 |

### 2.2 ADR-0067：Spacetime Runtime and Governed Creation

ADR-0067 的原始五子空间、八状态、七 Creator 面和六道闸已经由 ADR-0074 的裁剪决策部分取代。当前目标不是恢复原始全集，而是保持裁剪后的闭集：

| 裁剪目标 | 当前状态 | 未完成工作 | 验收证据 |
|---|---|---|---|
| ExecutionSpace + LifecycleSpace | 已落地 | 统一 profile、scope、artifact、runtime binding 的 provenance | `tests/artifact/`、binding validator |
| Artifact 四状态 `DRAFT/VERIFIED/ACTIVE/RETIRED` | 已落地 | 修复声明式 stop/final output 传播后复跑全量 | `tests/artifact/test_state_machine_property.py` |
| Creator 四面 `inspect/author/validate/promote` | 已落地 | 修复 handoff/HIL/Creator 相关回归，确保四面是唯一公开动作 | `tests/creator/test_4_faces.py` |
| 三道闸裁剪 | 核心已落地 | 补充 control verdict 和 artifact lifecycle 的组合 property test | control/creator tests |
| 原始八状态/七面/六闸 | 不属于当前目标 | 不得重新引入旧枚举或兼容映射 | legacy scan |

### 2.3 ADR-0068：Compiled Plugin Kernel and Unified Run Plan

| 条款 | 当前状态 | 未完成工作 | 验收证据 |
|---|---|---|---|
| `CompiledRunPlan = CapabilityPlan + ControlPlan + ScopePlan` | 已落地 | 继续保证所有运行时行为从 plan/provenance 可重建 | `tests/plan/test_plan_compiler.py` |
| plan hash 确定性 | 已落地 | 将替换性测试纳入 hash 变化断言 | `tests/plan/test_plan_hash_determinism.py` |
| plan_ref × Journal | 基本落地 | 验证 phase、effect、observation、resume 事件均有 plan/node/scope provenance | `tests/journal/test_plan_ref_replay.py` |
| CommandEnvelope 唯一效果入口 | 已落地 | 检查所有真实效果、TeamMessage 和 mode adapter 路径 | `tests/harness/test_command_envelope.py`、architecture tests |
| ArtifactController | 已落地 | 与 runtime result closure、recovery 和 replay 联合验证 | artifact/recovery tests |
| Boot 双轨消除 | 核心已落地 | 清理旧文档、旧测试和直接构造路径的生产可达性 | `tests/architecture/test_declarative_production_closure.py` |
| Stop/final output 结果传播 | **未完成** | stop delta 必须经 DeltaHandler/Reducer 写入 `TaskStatus` 和 `final_output`，最终 `Result.from_state()` 不得误判 FAILED | `tests/declarative/test_runtime_driver.py` |

### 2.4 ADR-0069：Agent Primitive System and Declarative Grammar

| 条款 | 当前状态 | 未完成工作 | 验收证据 |
|---|---|---|---|
| 13 个 functional group | 已落地 | 检查所有激活 PluginSpec 的 group 映射和六平面正交性 | `tests/harness/test_functional_group.py`、`test_six_plane_taxonomy.py` |
| LogicAddress 六维 | 已落地 | 保证 capability、authority、scope、evidence、revision 与 group 不互相替代 | `tests/harness/test_logic_address.py` |
| 11 种关系代数 | 已落地 | 继续验证关系解析、排序、冲突和 substitution fixture | `tests/plan/test_11_relations.py` |
| 6 个 contribution verbs | 已落地 | 将所有 contribution role 的运行时效果和 provenance 纳入动态测试 | control contribution tests |
| PluginContract 九段 | 已落地 | 补齐激活生产插件 manifest 的完整性检查 | `tests/harness/test_plugin_contract.py` |
| PlanTemplate 十二模板 | 已落地 | 保持 CLI、golden 文件和 profile 发现结果一致 | `tests/golden/test_12_plan_templates.py` |
| 关系图谱可解释性 | 部分落地 | 增加 `graph`/`explain plan` 的真实输出断言，不只验证数据结构 | CLI/graph tests |

### 2.5 ADR-0074：Plugin-Everything Trimmed Implementation

| 条款 | 当前状态 | 未完成工作 | 验收证据 |
|---|---|---|---|
| PR-0 至 PR-12 的数据面和编译链 | tracker 标记完成 | 重新按最新代码跑验收，不以 tracker 状态代替测试 | [`plugin-tracker.md`](plugin-tracker.md) |
| 0066/0068/0069 核心接受链 | 已落地 | 修复 runtime、HIL、team 和 trace 回归 | 对应专项测试 |
| 0067 裁剪方案 | 已落地 | 禁止恢复原始全集和 legacy API | legacy scan |
| 统一 acceptance sign-off | **未成立** | 修正文档中的过时全绿结论，并在所有 required gate 通过后重新签署 | `tests/test_adr_acceptance.py` + full suite |
| tracker/代码一致性 | 通过 | 每个后续实现提交同步 tracker 与验收矩阵 | `check_adr_supervision.py` |

### 2.6 ADR-0075：Declarative Phase Graph and Minimal Trusted Kernel

| # | 当前状态 | 未完成项 | 主要文件 |
|---:|---|---|---|
| 1 | 部分实现 | `DecisionClassifier` provider 已存在，但 `llm_result.py` 旧函数和默认 classifier fallback 仍保留；生产路径必须只通过 typed seam | `lca/layer1_cognitive/brain/llm_result.py`、`modular_brain.py` |
| 2 | 部分实现 | `RuntimeEffectGateway` 已使用 registry，但仍保留 deprecated facade 和直接默认 registry 构造；生产 binding 必须唯一 | `lca/layer2_runtime/declarative_runtime.py` |
| 3 | 部分实现 | 11 个 handler 已存在，但未知 operation 仍返回原 state；必须改为明确 `DeclarativeValidationError` 或 `UnknownDeltaOperation` 并记录失败事实 | `declarative_runtime.py`、`delta_handlers.py` |
| 4 | 基本落地，仍有兼容路径 | action authority 已进入 plan-data；`action_catalog.py` 的 `_operation_for`、`_SCOPE_ACTIONS`、SimpleBody 默认构造仍需限定为 test/legacy adapter 或删除 | `action_catalog.py`、`simple_body.py` |
| 5 | 已落地 | 保持 Reducer、Topology、StopRule 的显式 plugin 和生产 binding；删除生产可达 fallback | `reducer.py`、`loop_topology.py`、`default_stop_rule.py` |
| 6 | 部分实现 | `DeclarativeRuntimeDriver` 仍直接调用 `synthesize_artifact_closure()`；必须通过 `ArtifactClosure` seam 注入并具备 profile replacement test | `declarative_runtime.py`、`completion/artifact_closure.py` |
| 7 | 部分实现 | `GateChainComposer` provider 已存在；旧 `build_workspace_agent_gate()` 兼容入口和固定 fallback 仍需隔离或移除 | `decision_gates/__init__.py`、provider |
| 8 | 部分实现 | `SimpleBrainFactory` 已 lookup seam，但仍回退固定 gate builder、Null critic/synthesizer；生产路径应明确 require 或声明式 Null plugin | `default_factory.py` |
| 9 | 基本落地 | `RuntimePhaseCapabilities` 已使用 Protocol；同一 facade、phase executor 和 provider 周边仍有宽泛类型 | `declarative_runtime.py`、`phase_executors/` |
| 10 | 基本落地 | `ReducerDeltaAdapter` 核心参数已类型化；handler registry、解释器和外围 metadata 仍需严格类型 | `declarative_runtime.py`、`delta_handlers.py` |
| 11 | 未完全实现 | `DeclarativeRuntimeDriver.run(state: Any)`、phase context、provider 和 runtime factory 仍有宽泛 `Any`；必须分层清理并让 mypy/check_no_any 通过 | `declarative_runtime.py`、`harness/declarative/`、providers |
| 12 | 已完成（本次） | Recovery edge 已升级为原生 typed `PluginSpec` provider；配置显式声明 `reflect → think` predicate、`maxIterations`、budget 与 terminal predicate，并在真实 recovery profile 编译测试中验证进入 `CompiledRunPlan` | `lca/plugins/phase_edges/recovery.py`、`tests/declarative/test_recovery_edge.py` |
| 13 | 已完成 | `idempotency_store` capability 提供跨进程原子 claim、跨重启 completed receipt 与 `in_progress` fail-closed 语义 | `lca/contracts/protocols/idempotency.py`、`lca/layer0_infra/idempotency_store.py`、`lca/plugins/seam_definitions/idempotency_store.py` |

### 2.7 ADR-0076：Six-Plane Capability Layout and Substitution Test

| 条款 | 当前状态 | 未完成工作 | 主要证据 |
|---|---|---|---|
| 六平面分类 | 已落地 | 确保每个激活 manifest 恰好一个 plane，Evidence & Evolution 保持横切属性 | `tests/architecture/test_six_plane_taxonomy.py` |
| 替换 control/phase/effect/delta/team/mode | 静态门禁已落地 | 增加真实动态 fixture，证明只替换 profile/plugin entry 即改变 plan hash 和行为 | `tests/architecture/test_substitution_gates.py`、`test_handler_substitutability.py` |
| 生产 boot binding 硬失败 | 基本落地 | `stop_rule` 也纳入生产 binding 语义；禁止 runtime factory 静默 fallback | `runtime_binding_validator.py`、`runtime_factory.py` |
| Composer 只消费 compiled capability | 基本落地 | 清理 SimpleBody、legacy action catalog、Team transport 辅助路径的生产可达直接构造 | `plan_composers.py`、`simple_body.py`、`team_transport.py` |
| action authority 进入 plan | 已落地 | 补齐 profile patch 替换 action 集合的端到端动态测试 | `tests/plan/test_action_authority_plan.py` |
| run mode registry | 基本落地 | 验证新增 mode adapter 无需修改 gateway，并覆盖真实 profile boot、role/evidence/tool policy | `run_mode_registry.py`、`gateway/modes.py` |
| 四必填 Manifest 维度 | 部分实现 | 对所有激活 provider 做 capability/authority/lifecycle/evidence 强制校验 | PluginSpec/compiler tests |
| 生产闭合不可依赖 fallback | 部分实现 | 修复 stop_rule fallback，区分 test fixture 与 production context，并对 live path 做 closure assertion | runtime factory/closure tests |
| 全量替换验收 | 未完成 | 31 项全量测试失败；需按功能域清零后重跑全部 gates | full pytest |

## 3. 分阶段实施顺序

### Phase 0：冻结基线、统一事实和验收入口

**目标**是让后续每个修复都有唯一可比较的基线。保存当前 `pytest`、Ruff、Mypy、Protocol、Any、import-linter、vulture、文档门禁输出；更新实施计划和审计报告，不修改 ADR 决策本身。同步修正 `FINAL_EXECUTION_SUMMARY.md` 中“11 项全部完成”和“全量 pytest 通过”的过时陈述，并将 [`acceptance-criteria.md`](acceptance-criteria.md) 的验收路径与当前测试文件保持一致。

**完成条件**是 `git diff --check`、Markdown 链接检查和验收引用测试通过；基线失败列表被保存为可重跑命令，而不是只写概括数字。

### Phase 1：修复声明式结果与旧测试契约

第一步修复 `StandardPhaseExecutor` → `GenericPlanInterpreter` → `DeltaHandler` → `DefaultReducer` → `Result.from_state()` 的 stop/final output 链路。stop 阶段产生的 `StopDecision.status`、`final_output` 必须经已声明 delta 写入最终 state；`Result` 不得把合法完成误判为零输出失败。为终端、暂停、失败、handoff 和恢复分别增加测试。

第二步处理仍要求 `CognitiveRuntime._loop` 直接调用 `self.stop_rule.decide` 的旧测试。不得恢复被 ADR-0075 删除的 `_loop`，应将测试改为验证 `PhaseExecutor` 和 `GenericPlanInterpreter` 经 compiled binding 调用 stop rule，并验证 control verdict/Journal evidence。

**依赖**：无。**完成条件**：`tests/declarative/`、`tests/harness/test_c1_phase_substeps_guard.py`、`tests/harness/test_think_guard_consumer.py` 相关测试通过。

### Phase 2：收紧生产 binding，消除隐式默认与兼容双轨

修改 `runtime_factory.py`、`runtime_binding_validator.py`、`agent_assembly.py` 和 profile/bundle：生产 context 缺少 `reducer`、`loop_topology`、`stop_rule`、`effect_handler_registry`、`delta_handler_registry`、`artifact_closure`、`journal/evidence` 等闭包能力时，在 boot/compile 阶段抛出带来源的 `MissingBindingError`。测试 fixture 可以保留显式 test-only factory，但必须不能被生产 profile 到达。

清理或隔离 `RuntimeEffectGateway` 的 deprecated facade、`DefaultEffectHandlerRegistry` 默认构造、`synthesize_artifact_closure()` 自由函数、`build_workspace_agent_gate()` 固定 builder、`SimpleBrainFactory` 的固定 fallback，以及 `SimpleBody` 的旧 action catalog 入口。每一个兼容入口都必须有明确 owner、禁止生产可达测试和删除条件。

**依赖**：Phase 1。**完成条件**：缺失 binding 动态测试通过；生产源码不存在隐式 fallback；`test_declarative_production_closure.py` 通过。

### Phase 3：完成 Execution 三段式和 fail-closed 语义

统一 `ActionHandler`、`EffectHandler`、`DeltaHandler` 的 Protocol、registry、PluginSpec、receipt、error fact 和 substitution contract。未知 effect/delta operation 不得静默返回原 state；必须产生明确错误码、Journal 事实和终止/暂停结果。验证所有 11 个 delta operation，包括 `step`、`perception`、`turn`、`skill_route`、`activation`、`memory`、`stop`、`error`、`resume`、`artifact_closure`、`paused`。

将 action authority 的 profile 数据继续贯穿 `PlanCompiler → AgentCompositionRequest → BodyComposer → ActionRegistry`，并删除生产可达的 `_SCOPE_ACTIONS` / `_operation_for` 双轨。新增自定义 action handler fixture，只添加 profile/plugin entry 即能改变 plan hash 和可执行 action，不修改 composer/interpreter/gateway。

**依赖**：Phase 2。**完成条件**：`test_handler_substitutability.py`、`test_action_authority_plan.py`、所有 handler contract tests 和 CommandEnvelope tests 通过。

### Phase 4：完成 Organization、Team 和 Gateway mode 替换

继续收紧 `team_seam`：Team shared memory、transport、member invoker、subagent provider 和 session service 必须从 compiled scope capability 注入。保留 seam definition 中的默认 provider 工厂，但不得让 Composer 直接构造 backend。对 `run_mode_registry` 增加真实替换 fixture：新增 mode adapter 只能添加 plugin/profile entry，必须改变 role、tool policy、composer selection、evidence policy 和 plan provenance，不修改 gateway 分支。

同步修复 team scripted、lead composition、handoff、trace 和 cancellation 回归。TeamMessage、delegation 和 mode adapter 的效果必须拥有 envelope、grant、idempotency key 和 Journal receipt。

**依赖**：Phase 3。**完成条件**：`tests/test_team_modes_scripted.py`、`tests/test_lead_composition.py`、`tests/test_handoff_strategy.py`、gateway cancel/trace tests 通过，动态 substitution fixture 通过。

### Phase 5：完成 Evidence、Journal、Replay、Idempotency 和 Recovery

将 `RuntimeJournalCommitter` 接入正式 Journal/evidence backend，确保 phase result、control verdict、effect receipt、observation、TeamMessage、model-visible context 和 resume 都带 `plan_ref`、node/scope、grant、revision 和 causation provenance。禁止仅依赖解释器内存列表作为生产事实源。

Recovery profile 已不再停留在 YAML edge：bounded recovery plugin 以原生 `PluginSpec` 声明 `reflect → think` 边的 predicate、最大次数、预算、terminal predicate 和 evidence，并由真实 profile 编译测试验证；完整 run replay、Journal receipt 与 recovery E2E 仍属于本阶段的后续验收。durable `IdempotencyStore` 已由远程基线完成，继续遵守不确定 effect 的 fail-closed 语义。

**依赖**：Phase 2、Phase 3。**完成条件**：完整 run replay、resume、不确定 effect、recovery edge、Journal receipt 和跨重启 fixture 通过。

### Phase 6：完成 Protocol 继承、类型安全和静态门禁

为 `check_protocol_impl.py` 当前 19 个命中逐项补充显式 Protocol 继承或调整类职责，特别是 `DeclarativeRuntimeDriver`、所有 DeltaHandler、EffectHandler、Registry 和 `RunModeRegistry` 的错误/隐式继承关系。不得通过扩大 allowlist 隐藏真实实现。

按层清理 `check_no_any.py` 当前 244 个命中：先清理 ADR-0075/0076 生产路径中的 `declarative_runtime.py`、phase executors、runtime factory、mode/loop driver 和 provider，再处理外围 plugin 工具。以 Protocol、TypedDict、泛型、`object` 及窄化辅助函数替代无约束 Any。同步解决当前 mypy 166 errors/46 files，禁止用 `type: ignore` 覆盖架构错误。

**依赖**：Phase 3、Phase 4。**完成条件**：`check_protocol_impl.py`、`check_no_any.py`、`mypy lca`、Ruff 和 import-linter 通过。

### Phase 7：全量回归、文档治理和最终 sign-off

按功能域清理当前 31 项失败，至少覆盖声明式 cutover/runtime、spawn binding、loop-order 旧契约、checkpoint/HIL、team scripted/trace、plugin alignment、contracts purity、ADR index 和 code convention。对每个失败先判断是生产 bug、测试契约滞后还是既存文档/夹具错误，不得删除测试或降低门禁制造绿色结果。

修正文档中互相冲突的完成声明：`FINAL_EXECUTION_SUMMARY.md`、ADR-0075 实施审计、ADR-0074 acceptance criteria 和本计划必须与代码、测试和命令输出一致。处理 `AGENTS.md` 超预算 368 词与 `docs/adr/README.md` 超预算 6 词的问题；若保留内容确有必要，必须在独立提交中说明预算调整理由。最后运行完整命令序列：

```sh
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
uv run python scripts/check_adr_supervision.py
uv run python scripts/route_legacy_patterns.py --json
uv run python scripts/verify_md_links.py
uv run python scripts/verify_doc_budgets.py
```

**依赖**：Phase 1–6 全部完成。**完成条件**：全量 pytest、静态门禁、文档门禁和 ADR tracker 均通过，且动态替换测试覆盖 control、phase、effect、delta、team backend、run mode 六类轴。

## 4. 风险与禁止事项

实现期间不得恢复旧的固定 `_loop`、新增第七个认知阶段、把安全不变量下放为普通 plugin、让 runtime 依赖 plugin ID/类名/factory key 分支、保留静默未知 operation、把 `Any` 门禁加入 allowlist、删除失败测试或将 test fixture fallback 暴露给生产 profile。

最高风险是 Phase 1 的结果状态传播和 Phase 5 的 durable evidence/idempotency，它们会影响 Runtime、Reducer、Journal、Gateway 和 HIL。所有跨层公共签名变更必须同步 Protocol、直接调用方、测试和 ADR 事实；所有 production path 修改必须附带可替换性 fixture。

## 5. 提交拆分建议

| 提交顺序 | Conventional Commit | 内容 |
|---:|---|---|
| 1 | `docs(adr-plan): refresh implementation gap matrix` | 本计划、基线和验收入口 |
| 2 | `fix(runtime): propagate declarative stop outcome` | stop/final output、旧测试契约迁移 |
| 3 | `fix(runtime): enforce production capability closure` | stop/effect/delta/artifact/evidence binding 与 fallback 清理 |
| 4 | `refactor(execution): close handler registries fail closed` | handler Protocol、registry、unknown operation、action authority |
| 5 | `refactor(organization): complete team and mode substitution` | team seam、mode adapter、动态替换 fixture |
| 6 | `feat(evidence): add durable runtime receipts and recovery` | Journal provenance、durable idempotency、Recovery plugin |
| 7 | `refactor(types): remove implicit protocol implementations` | 显式继承、Any 清理、mypy |
| 8 | `test(adr): close full regression matrix` | 全量回归、架构/文档门禁和最终 sign-off |

每个提交必须单一职责、包含对应测试和命令输出；完成后同步 ADR-0074 tracker 的交付信息和验收矩阵，但不得把未通过的阶段标成 Done。

## 6. References

[1]: ../adr/0066-declarative-atomic-control-plugins.md "ADR-0066: Declarative Atomic Control Plugins"
[2]: ../adr/0067-spacetime-runtime-and-governed-creation.md "ADR-0067: Spacetime Runtime and Governed Creation"
[3]: ../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md "ADR-0068: Compiled Plugin Kernel and Unified Run Plan"
[4]: ../adr/0069-agent-primitive-system-and-declarative-grammar.md "ADR-0069: Agent Primitive System and Declarative Grammar"
[5]: ../adr/0074-plugin-everything-trimmed-implementation.md "ADR-0074: Plugin-Everything Trimmed Implementation"
[6]: ../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md "ADR-0075: Declarative Phase Graph and Minimal Trusted Kernel"
[7]: ../adr/0076-six-plane-capability-layout-and-substitution-test.md "ADR-0076: Six-Plane Capability Layout and Substitution Test"
[8]: ../adr/0081-audit-implementation.md "ADR-0075 Implementation Audit"
[9]: ../architecture-reviews/implementation-audit.md "Current ADR-0066–0076 Implementation Audit"
