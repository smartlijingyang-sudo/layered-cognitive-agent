# lca/contracts/protocols

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `52` 个公开模块 + `401` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：194 个显式 __all__ 条目； 401 个定义符号中，395 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.contracts.protocols].forbidden_dependencies`**:

- `lca.agent`
- `lca.application`
- `lca.cognition`
- `lca.harness`
- `lca.infrastructure`
- `lca.plugins`
- `lca.runtime`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `ActionAuthorityPlan`
- `ActionHandler`
- `ActionHandlerRegistry`
- `ActionScopeAuthority`
- `AgentTransport`
- `AgentUnit`
- `ApprovalResumeDecision`
- `ApprovalResumeDisposition`
- `ArtifactClosure`
- `AttachmentIdentity`
- `Body`
- `Brain`
- `BrainFactory`
- `BrainPromptCatalog`
- `BrainPromptCatalogFactory`
- `BudgetCeiling`
- `BudgetPolicy`
- `BudgetReservation`
- `COMPILED_RUN_PLAN_VERSION`
- `CapabilityBinding`
- `CapabilityDeclaration`
- `CapabilityGrant`
- `CapabilityPlan`
- `CheckpointStateResolver`
- `CheckpointStateResolverFactory`
- `CognitivePhaseGraphPlan`
- `CognitiveReflectionPipeline`
- `CognitiveThinkPipeline`
- `CommandEnvelope`
- `CompiledRunPlan`
- `ComponentRegistryProtocol`
- `ContributionRole`
- `ControlVerdict`
- `ControlVerdictKind`
- `Critic`
- `DECLARATIVE_PLAN_VERSION`
- `DecisionGate`
- `DecisionGateAssembler`
- `DecisionRef`
- `DeclarativeControlEntry`
- `DeclarativeInterpreter`
- `DeclarativeInterpreterFactory`
- `DeclarativeValidationError`
- `DeltaReducer`
- `DeltaReducerFactory`
- `DshRuntime`
- `EffectCapabilities`
- `EffectDispatcher`
- `EffectDispatcherFactory`
- `EffectHandler`
- `EffectHandlerRegistry`
- `EffectPolicyPlan`
- `EnvelopeVerdict`
- `EventBus`
- `GateChainComposer`
- `GraphNodeExecutionContext`
- `GraphNodeExecutor`
- `GraphNodeExecutorRegistryProtocol`
- `HasHooks`
- `Hook`
- `HookRegistry`
- `IdempotencyClaim`
- `IdempotencyStore`
- `JournalCommitter`
- `JournalProjector`
- `LLMAdapter`
- `LeadBudgetPolicyResolver`
- `LogicAddress`
- `LogicAddressScore`
- `LoopGuardEvaluator`
- `LoopGuardVerdict`
- `MemberInvoker`
- `MemorySystem`
- `ModeAdapter`
- `NamedRegistryProtocol`
- `ObservabilityBackend`
- `OrchestrationRegistryProtocol`
- `PLUGIN_SPEC_VERSION`
- `PerceiveHub`
- `PerceiveHubAssembler`
- `PhaseBinding`
- `PhaseBudgetSnapshot`
- `PhaseContext`
- `PhaseContribution`
- `PhaseEdge`
- `PhaseExecutor`
- `PhaseInput`
- `PhaseNode`
- `PhaseObserver`
- `PhaseObserverContribution`
- `PhaseObserverRegistry`
- `PhaseResult`
- `PhaseStateSnapshot`
- `PlanProvenance`
- `PluginConfiguration`
- `PluginImplementation`
- `PluginRelation`
- `PluginSpec`
- `PluginSpecKind`
- `ProviderBinding`
- `Reasoner`
- `Reducer`
- `RegisteredMode`
- `RelationType`
- `ReplacementDecision`
- `ResultFinalizer`
- `ResultFinalizerFactory`
- `RetrievalPolicy`
- `RoleLibrary`
- `RunDelta`
- `RunFact`
- `RunModeRegistryProtocol`
- `Runtime`
- `RuntimeBudgetSnapshot`
- `RuntimeFactory`
- `RuntimeJournal`
- `RuntimeJournalFactory`
- `RuntimeLifecycleEvent`
- `RuntimeLifecycleEventType`
- `RuntimeLifecyclePublisher`
- `RuntimeLifecycleSubscriber`
- `RuntimeLifecycleSubscriberContribution`
- `RuntimeLifecycleSubscriberRegistry`
- `SANDBOX_SKILL_MOUNT_PREFIX`
- `SafeExecutor`
- `Sandbox`
- `SandboxRuntime`
- `ScopePlan`
- `SemanticPhase`
- `Sensor`
- `SensorDisabledError`
- `SessionCommandLedger`
- `SessionPersistence`
- `SessionPersistenceFactory`
- `SessionTurnController`
- `SessionTurnControllerFactory`
- `SharedMemoryStore`
- `SkillImportError`
- `SkillImporter`
- `SkillIndexEntry`
- `SkillNotFoundError`
- `SkillPackage`
- `SkillPackageInstaller`
- `SkillPackageStore`
- `SkillRouter`
- `SkillSearchResult`
- `StateStore`
- `StopPolicy`
- `SupportsShortcut`
- `Synthesizer`
- `TeamAssembly`
- `TeamCaster`
- `TeamSeamFactoryProtocol`
- `TeamStage`
- `TeamStrategy`
- `TeamUnit`
- `Telemetry`
- `TemporalMemoryStore`
- `Tool`
- `ToolDefinition`
- `ToolExecutionContext`
- `ToolExecutionPipeline`
- `ToolExecutionResult`
- `ToolPostDecision`
- `ToolPreDecision`
- `ToolProvider`
- `ToolRegistry`
- `ToolRenderer`
- `TransportRegistryProtocol`
- `TurnAlreadyRunningError`
- `TypedRelation`
- `ValidationIssue`
- `ValidationReport`
- `Verdict`
- `canonical_scope_of`
- `capability_plan_hash`
- `capability_plan_to_dict`
- `command_envelope_to_dict`
- `declared_dim_count`
- `envelope_aggregate_verdict`
- `envelope_is_authorized`
- `is_complete_address`
- `mint_envelope`
- `relations_from_plugin`
- `relations_of_kind`
- `relations_to_plugin`
- `scope_plan_from_iter`
- `scope_plan_hash`
- `scope_plan_to_dict`
- `score_logic_address`
- `typed_relation_to_dict`
- `typed_relations_from_iter`
- `warn_deprecated_envelope_constructor`
