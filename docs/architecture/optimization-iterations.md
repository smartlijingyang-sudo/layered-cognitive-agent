# 架构深化迭代记录

本记录以 **模块、接口、深度、接缝、适配器、杠杆、局部性** 为统一词汇。每轮只增加一个可回归的公开测试表面，避免把复杂度转移到测试内部。

| 轮次 | 深化目标 | 验证方式 |
|---:|---|---|
| 01 | 收拢运行状态契约，固定 AgentState 作为唯一测试入口（`lca.contracts.models.core.state.AgentState`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 02 | 强化预算模型的深度，固定 BudgetLimits 的可发现接口（`lca.contracts.models.core.budget.BudgetLimits`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 03 | 隔离决策模型，固定 Decision 作为认知到执行的接缝（`lca.contracts.models.core.decision.Decision`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 04 | 稳定执行信封，固定 ExecutionEnvelope 的装配入口（`lca.contracts.models.core.execution.ExecutionEnvelope`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 05 | 统一生命周期枚举，减少跨模块状态字符串泄漏（`lca.contracts.models.core.lifecycle.TaskStatus`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 06 | 稳定模型响应契约，提升适配器替换时的局部性（`lca.contracts.models.core.llm.LLMResponse`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 07 | 集中消息表示，减少调用方重复解析文本（`lca.contracts.models.core.message.AgentMessage`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 08 | 固定感知清单模型，收拢上下文构建复杂度（`lca.contracts.models.core.perception.ContextManifest`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 09 | 固定双平面绑定模型，保护装配层接缝（`lca.contracts.models.core.plane.PlaneBindings`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 10 | 稳定结果模型，收拢终态判断的测试表面（`lca.contracts.models.core.result.Result`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 11 | 稳定沙箱会话信息模型，隔离基础设施细节（`lca.contracts.models.core.sandbox.SessionInfo`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 12 | 固定激活技能模型，减少技能路由的隐式字段（`lca.contracts.models.core.activation.ActivatedSkill`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 13 | 固定审批请求模型，收拢副作用授权语义（`lca.contracts.models.core.approval.ApprovalRequest`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 14 | 固定附件身份模型，避免跨层重复推断（`lca.contracts.models.core.attachment.AttachmentRecord`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 15 | 固定会话轮次模型，提升回放与测试局部性（`lca.contracts.models.core.conversation.ConversationTurn`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 16 | 固定记忆记录模型，收拢来源和证据字段（`lca.contracts.models.core.memory.MemoryRecord`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 17 | 固定预装包导入函数，隔离命名转换规则（`lca.contracts.models.core.preinstall.python_import_name`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 18 | 固定策略事实模型，提升门控判定可测试性（`lca.contracts.models.core.gate_policy.PolicyFact`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 19 | 固定访客布局模型，隔离路径拼接规则（`lca.contracts.models.core.guest_layout.GuestLayout`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 20 | 固定子代理规格模型，收拢委托装配复杂度（`lca.contracts.harness.subagent.SubagentSpec`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 21 | 固定任务步骤模型，保护计划执行接缝（`lca.contracts.harness.task.TaskStep`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 22 | 固定超时恢复策略，隔离重试决策（`lca.contracts.harness.timeout_recovery.TimeoutRecoveryPolicy`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 23 | 固定工具治理模型，提升效果网关前的可验证性（`lca.contracts.harness.tool_governance.ToolGovernance`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 24 | 固定追踪上下文模型，减少观测字段漂移（`lca.contracts.harness.trace_context.AgentTraceContext`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 25 | 固定工作流进度模型，收拢阶段推进状态（`lca.contracts.harness.workflow.WorkflowProgress`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 26 | 固定机制事件总线协议，保护发布者与订阅者接缝（`lca.contracts.mechanisms.EventBus`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 27 | 固定能力键模型，提升授权查询的局部性（`lca.contracts.mechanisms.capability.CapabilityKey`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 28 | 固定插件工厂，收拢组合装配复杂度（`lca.contracts.mechanisms.composition.PluginFactory`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 29 | 固定内容寻址存储协议，便于替换持久化实现（`lca.contracts.mechanisms.content_addressable.ContentAddressableStore`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 30 | 固定工厂注册表，集中实例发现逻辑（`lca.contracts.mechanisms.factory_registry.FactoryRegistry`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 31 | 固定插件配置模型，避免配置字段跨层泄漏（`lca.contracts.mechanisms.plugin.PluginConfig`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 32 | 固定注册表集合，保护组合根的装配接口（`lca.contracts.mechanisms.registries.Registries`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 33 | 固定 seam.consume 接缝函数，明确适配器接入方式（`lca.contracts.mechanisms.seam.consume`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 34 | 固定技能契约，统一技能提供方测试表面（`lca.contracts.harness.skill.LoadedSkill`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 35 | 固定运行技能协议，隔离操作技能生命周期（`lca.contracts.protocols.operational_skills.SkillPackage`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 36 | 固定技能投影，收拢展示模型转换（`lca.harness.skills.projection.SkillsProjection`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 37 | 固定技能服务，集中技能读取与编排入口（`lca.harness.skills.service.SkillCatalogService`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 38 | 固定能力技能模型，隔离基础设施能力声明（`lca.infrastructure.capability.skills.SkillsService`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 39 | 固定检索技能策略，保护搜索决策的局部性（`lca.infrastructure.search.skill_policy.filter_skill_search_result`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 40 | 固定激活范围模型，收拢作用域判断（`lca.infrastructure.skills.activation_scope.get_activated_skills`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 41 | 固定内置技能模型，隔离默认资源装配（`lca.infrastructure.skills.bundled.ensure_bundled_skills`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 42 | 固定技能磁盘存储，保护文件持久化接缝（`lca.infrastructure.skills.disk_store.DiskSkillPackageStore`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 43 | 固定技能工厂，集中实例化和默认值（`lca.infrastructure.skills.factory.resolve_skill_store`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 44 | 固定格式路由，隔离输入格式判断（`lca.infrastructure.skills.format_routing.skills_for_filename`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 45 | 固定 frontmatter 模型，收拢元数据解析结果（`lca.infrastructure.skills.frontmatter.split_frontmatter`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 46 | 固定 HTTP 导入器，隔离外部来源适配（`lca.infrastructure.skills.http_importer.HttpSkillImporter`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 47 | 固定市场认证模型，集中凭据决策接缝（`lca.infrastructure.skills.market_auth.market_auth_setup_hint`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 48 | 固定技能市场模型，隔离目录发现逻辑（`lca.infrastructure.skills.marketplace.LobeHubMarketClient`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 49 | 固定技能设置模型，保护配置读取局部性（`lca.infrastructure.skills.settings.SkillSettings`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 50 | 固定 URL 来源模型，收拢远程来源表示（`lca.infrastructure.skills.url_sources.ParsedSkillUrl`） | `pytest tests/test_architecture_iteration_contracts.py` |
| 51 | 固定插件依赖读取接缝，移除 `ctx.inject` 兼容别名并统一到 `PluginContext.require` | `pytest tests/architecture/test_plugin_context_single_require.py` |
| 52 | 固定技能安装接缝，收拢导入与读取的同一存储装配（`lca.contracts.protocols.operational_skills.SkillPackageInstaller`） | `pytest tests/test_architecture_iteration_contracts.py tests/test_operational_skills.py` |
| 53 | 收窄声明式控制投影输入接缝，移除未参与编译行为的伪配置 | `pytest tests/plan/test_plan_compiler.py` |
| 54 | 闭合技能安装接缝：让 `SkillsService`、插件声明与磁盘适配器统一以 `SkillPackageInstaller` 为接口，避免写入能力在组合时泄漏 | `pytest tests/test_operational_skills.py tests/test_plugin_alignment.py` |
| 55 | 固定组件发现注册表，拒绝类别内隐式覆盖并集中独立贡献者的替换性测试表面（`lca.infrastructure.component_registry.ComponentRegistry`） | `pytest tests/architecture/test_component_registry_seam.py` |
| 56 | 收紧传输发现注册表的协议所有权，禁止依赖 provider 注册顺序覆盖实现（`lca.infrastructure.transport.transport_registry.TransportRegistry`） | `pytest tests/test_transport_registry.py` |
| 57 | 修正 Protocol 实现门禁的继承链识别，避免将通过子 Protocol 显式实现的存储接缝误报为隐式实现（`scripts/check_protocol_impl.py`） | `python scripts/check_protocol_impl.py` |
| 58 | 统一 Action、Effect、Delta 处理器注册表：拒绝 operation 内隐式覆盖，并提供领域专属发现快照以集中启动诊断与覆盖校验（`lca.infrastructure.handler_registry.UniqueOperationRegistry`） | `pytest tests/architecture/test_handler_substitutability.py tests/contracts/test_new_protocols.py` |
| 59 | 固定 Lead 预算策略解析接缝，收拢组件发现、工厂调用与协议校验，使计划绑定代理仅依赖 `LeadBudgetPolicyResolver` | `pytest tests/architecture/test_component_registry_seam.py tests/test_lead_composition.py` |
| 60 | 移除 Lead 决策门在 `ComponentRegistry` 与 `GateService` 间的重复发现路径，统一由门服务按领域枚举解析，避免组合模块泄漏组件分类 | `pytest tests/architecture/test_component_registry_seam.py tests/test_lead_composition.py` |
| 61 | 收拢能力快照所有权接缝，使诊断树直接复用生产 profile 解析结果，并移除“首个 owner + contributor”这一宽松的平行语义 | `pytest tests/architecture/test_capability_snapshot.py` |
| 62 | 固定计划能力解析适配器，集中 provider binding 的注册表回退并保持 composer 完整键读取的局部性（`lca.plugins.composer.capability_resolution.ScopeCapabilityResolver`） | `pytest tests/composer/test_capability_resolution.py tests/composer/test_plan_binding_validation.py tests/layer4_app/test_spawn_bind_plan.py` |
| 63 | 固定提供方解析键模型，使统一能力解析适配器直接消费编译计划中的精确接缝，移除计划绑定对注册表与命名空间字符串的隐式回退（`lca.contracts.protocols.capability_plan.ProviderBinding.resolution_key`） | `pytest tests/composer/test_capability_resolution.py tests/composer/test_plan_binding_validation.py tests/plan/test_11_relations.py` |
| 64 | 拆除跨群 `plan_composition_support` 聚合模块；将 Think、Perceive 与 Collaboration 的内部装配逻辑归位到具名 `internal/` 模块，并使 L4 仅保留必要兼容导出 | `pytest tests/composer/test_brain_factory_contract.py tests/composer/test_composer_consumes_compiled_capability.py tests/architecture/test_component_registry_seam.py tests/layer4_app/test_spawn_bind_plan.py tests/test_cordis_creator_skills.py tests/test_plugin_tree_single_owner.py` |
| 65 | 退役未被执行器消费的 `ControlPlan` 平行投影；运行计划、诊断和散列统一以 `PluginSpec.contributes` 编译出的 `control_entries` 为事实源 | `pytest tests/plan/test_plan_compiler.py tests/architecture/test_harness_control_contract.py tests/harness/test_audit_control_surface.py` |
| 66 | 收拢 Profile 已解析入口与程序化入口的启动生命周期；两类输入统一经 `_boot_context` 执行 Manifest 审计、Fiber 装配、检查视图投影、失败清理和观测安装，避免兼容适配器漂移 | `pytest tests/test_profile_resolve_boot.py tests/test_plugin_alignment.py tests/test_plugin_tree_single_owner.py` |
| 67 | 将 solo/member/lead 的动作授权收敛为 `ActionAuthorityPlan` 的编译期范围投影；组合器只选择声明授权，缺失范围即失败 | `pytest tests/plan/test_action_authority_plan.py tests/layer4_app/test_spawn_bind_plan.py` |
| 68 | 固定 Profile 启动产物接缝，使解析 Profile 与编译运行计划作为同一不可变事实对供组合与诊断读取，移除对 `Context` 隐式属性的跨模块推断 | `pytest tests/test_profile_resolve_boot.py tests/layer4_app/test_spawn_bind_plan.py` |
| 69 | 退役未被声明式运行时消费的 `LoopTopology` production closure、插件与平行阶段模型；`SemanticPhase` 与 `PhaseGraphValidator` 成为阶段闭集和顺序的唯一事实源 | `pytest tests/declarative/test_phase_graph.py tests/test_boot_binding_completeness.py tests/test_architecture_conformance.py tests/architecture/test_capability_snapshot.py` |
| 70 | 将 Profile 启动检查视图投影下沉为 `lca.harness.profile.boot_projection`，使 `boot.py` 仅保留输入适配、Fiber 生命周期与启动失败清理编排 | `pytest tests/test_profile_resolve_boot.py tests/test_code_conventions.py` |
| 71 | 收拢 Agent 的 Profile 启动产物消费：由 `bind_agent_from_scope` 独占“冻结计划 → 动作授权范围 → 组合请求 → 完整图”的绑定序列，使 Agent 与 Team 同样只能读取 scope 上的单一计划事实 | `pytest tests/layer4_app/test_spawn_bind_plan.py tests/composer/test_plan_binding_validation.py tests/composer/test_capability_resolution.py tests/plan/test_action_authority_plan.py` |
| 72 | 收拢程序化 Profile 输入：以输入适配器接入唯一 Resolve 模块，删除测试入口重复的 Manifest、配置、provider 所有权和 DAG 语义，保留运行时闭合夹具的能力读取验证 | `pytest tests/test_profile_resolve_boot.py tests/test_plugin_alignment.py tests/test_plugin_tree_single_owner.py` |
| 73 | 下沉可编辑 Profile 条目输入适配，使兼容调用方直接消费 Bundle 展开与 Patch 合并后的声明，避免“Resolve → 反序列化条目 → Resolve”往返；插件导入和 Manifest 语义仍唯一归属 Resolve 接缝（`lca.harness.profile.source.load_profile_entries`） | `pytest tests/test_profile_resolve_boot.py tests/test_plugin_alignment.py tests/test_plugin_tree_single_owner.py` |
| 74 | 将插件 Manifest 公开接口收敛为薄门面：不可变声明、装饰器输入适配、类型化规格投影与启动期交互审计分别归于具名模块，调用方仍只依赖 `lca.harness.plugin_api` | `pytest tests/architecture/test_plugin_manifest_facade.py tests/test_profile_resolve_boot.py tests/test_plugin_alignment.py` |
| 75 | 将 Profile 启动产物编译及运行闭合预检前移到 Fiber 生命周期之前，使无效解析 Profile 在任何插件 setup 前失败，保护启动接缝的原子性、局部性与失败关闭杠杆 | `pytest tests/test_profile_resolve_boot.py` |
| 76 | 将检查视图并入 Profile 启动产物接缝：程序化与生产入口都附加不可变产物，诊断与生命周期只读 `resolved_profile`，删除平行的 `Context.entries` | `pytest tests/architecture/test_profile_boot_inspection_seam.py tests/test_profile_resolve_boot.py` |
| 77 | 退役无调用方的 `boot_report` 平行诊断模块；其 `Any` 形状探测、可选 entries 输入和遗留属性适配既不属于 Profile 启动接缝，也不提供可达能力，保留的 `inspect-tree` 与 `debug tree` 分别读取冻结 Profile 事实和真实 Cordis 树 | `pytest tests/architecture/test_profile_boot_inspection_seam.py tests/test_inspect_capability_graph.py tests/test_diagnose_cli.py` |
| 78 | 将生产运行闭合目录从 `contracts` 下沉至 Profile 编译接缝；`ProviderBinding` 仅保留不可变事实，回退策略、provider 提示与闭合判定统一由 `lca.harness.profile.runtime_closure` 拥有，删除跨层装配策略的平行入口 | `pytest tests/test_contracts_purity.py tests/test_boot_binding_completeness.py tests/harness/test_runtime_binding_validator.py tests/harness/test_profile_source.py tests/architecture/test_substitution_gates.py` |
| 79 | 删除 `ResolvedProfile` 反向编译计划的无类型便利入口与未消费的 `FieldSource` 导出；解析产物只承载不可变 Profile 事实，计划编译统一从显式 `plan_compiler` 接缝进入，降低 Profile 解析模块的接口复杂度与依赖泄漏 | `pytest tests/test_profile_resolve_boot.py` |
| 80 | 收拢普通 Session 命令的恢复、未知会话拒绝与回执序列投影：由 `LiveCommandExecutor` 独占 `entry_or_recover → 执行 LiveAgent 操作 → CommandReceipt` 序列；命令路由器仅保留创建、持久幂等和审批协调等具有不同语义的接缝，提升命令扩展的局部性与测试杠杆 | `pytest tests/harness/test_live_command_executor.py tests/harness/test_phase_b_spine.py tests/harness/test_session_command_ledger.py` |
| 81 | 收拢模型发出的工具批次执行职责：由 `ToolBatchExecutor` 独占工具预解析、调度计划校验、分段派发与结果封装；`UseToolOperation` 仅保留动作校验和 wire gate，使批次策略替换与世界副作用接缝具有更强局部性 | `pytest tests/layer1_cognitive/body/test_tool_batch_execution.py` |
| 82 | 将 LoopGuard evaluator 下沉至 DeclarativeInterpreterFactory 构造接缝，移除其在 RuntimeCapabilityClosure、ProductionRuntimeDeps 与 DeclarativeRuntimeBindings 中的重复顶层字段，保持 loop-edge traversal 策略局部性 | `pytest tests/declarative/test_loop_guard.py tests/layer2_runtime/test_declarative_execution_journal.py tests/composer/test_agent_assembly_runtime_bindings.py tests/test_runtime_factory_strict_bindings.py` |
| 83 | 收拢阶段能力投影所有权：由 `RuntimePhaseCapabilities` 独占 canonical graph facts 的合并与冲突校验，`ProductionRuntimeDeps` 仅负责组合事实到运行时绑定的委托，避免 L4 组合层重复解释 L2 运行时语义 | `pytest tests/composer/test_agent_assembly_runtime_bindings.py` |
| 84 | 收拢 `CognitiveRuntime` 的 fresh/resume driver 生命周期投影：由单一 `_run_driver` 接缝统一取消、失败与终态发布，入口仅保留状态创建/恢复，提升生命周期语义的局部性与测试杠杆 | `uv run pytest --no-cov tests/layer2_runtime/test_runtime_lifecycle_plugins.py tests/declarative/test_cutover_characterization.py tests/declarative/test_runtime_driver.py tests/composer/test_agent_assembly_runtime_bindings.py -q` |
| 85 | 让 `lca.contracts.protocols` barrel 单一来源：每条 `from X import Y` 是公开 re-export，`__all__` 在模块加载时从 import 派生（剔除模块副作用与 `__future__` 注入），新增/删除 re-export 不再需要双写；顺带消除 2 个失效幻影条目（`PhaseGraphValidator`/`PluginSpecValidator`），用 `# ruff: noqa: F401` 声明 barrel 语义 | `uv run pytest --no-cov tests/contracts/test_protocols_package_contract.py` |
| 86 | 收拢 `RunStore.append` 与 `RunStore.seal` 的提交序列：抽出 `_validate_event_shape` + `_commit_unlocked`，两条路径共享验证/盖章/持久化/`LedgerDurabilityError` 翻译；消除原代码注释里 "Inline the commit path" 的显式复制；顺手修复 `seal` 在 backend 失败时漏抛 `LedgerDurabilityError` 的漂移 | `uv run pytest --no-cov tests/test_run_ledger_seal_durability.py tests/test_run_ledger_seal.py tests/test_run_ledger_concurrency.py` |
| 87 | 删除 `SimpleBody._maybe_record_action_degraded`：一个空实现方法，docstring 仅指明真正发射点在 `event_emission._derive_action_degraded`（POST_ACT hook）；删除方法本体、把"真发射点"这一信息搬到还活着的 `_propagate_degradation` 与 `act` 的 docstring；测试断言 no-op 不再存在、`_propagate_degradation` 仍负责 marker 传播 | `uv run pytest --no-cov tests/test_simple_body_no_op_removed.py` |
| 88 | 让 `lca.contracts.capabilities` 单一来源：每个 `Capability[object]("key", cardinality=...)` 常量在模块加载时被 `_build_capability_index()` 索引为 `CAPABILITIES_BY_KEY`，新增能力仍是单行 edit；顺手删除无调用方的 `RUN_LOOP_DRIVER_REGISTRY = DRIVERS` 死别名 | `uv run pytest --no-cov tests/contracts/test_capabilities_index.py` |
| 89 | `DelegateOperation` 的两条路径 (`_execute_one` / `_execute_many`) 内联了同一份 cache-check → invoke → record-return 序列；抽出 `_resolve_observation` 为单一接缝，单路径直接调用，多路径通过 `asyncio.gather` 并发；聚合逻辑独立为 `_aggregate_observations` | `uv run pytest --no-cov tests/test_delegate_resolve_observation.py` |
| 90 | 让 `lca.contracts` barrel 同样单一来源（沿用 R85 模式）：`__all__` 从 import 派生，新增/删除 re-export 单行 edit；文件 134 → 87 行 | `uv run pytest --no-cov tests/contracts/test_lca_contracts_barrel.py` |

总计：90 轮架构深化记录。
