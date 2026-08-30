# lca/infrastructure/observability

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
可观测性基础设施层：Journal Store（追加式事实）、projection 引擎、OTel / JSONL / Console 适配器、SSOT tracer 与事实读取器。所有上层 log / metric / trace 调用都通过这一层落到持久化 journal。

## 2. 不负责
业务决策、跨层编排、契约定义、生产代理的认知行为。

## 3. 输入
- 当前包内 `58` 个公开模块 + `466` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：127 个显式 __all__ 条目； 466 个定义符号中，278 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
—

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `ActionDegraded`
- `AgentRunFinished`
- `AgentRunStarted`
- `AttributePolicy`
- `BoundObservability`
- `CastingCompleted`
- `CastingFailed`
- `CastingStarted`
- `DecisionMade`
- `DelegationCacheHit`
- `DelegationCompleted`
- `DelegationIssued`
- `DelegationMechanism`
- `DiagnosticCategory`
- `DiagnosticEvent`
- `DiagnosticStatus`
- `DuplicateEventDescriptorError`
- `EVENT_DESCRIPTOR_REGISTRY`
- `EventAudience`
- `EventDescriptor`
- `EventDurability`
- `EventPlane`
- `EventProjection`
- `EventSensitivity`
- `FRAMEWORK_TAG`
- `InMemoryEventDescriptorRegistry`
- `InMemoryJournalStore`
- `JOURNAL_EVENT_CLASSES`
- `JournalEvent`
- `JournalProjector`
- `JournalSchemaMeta`
- `JournalStoreBackend`
- `LANGFUSE_ENVIRONMENT`
- `LANGFUSE_OBSERVATION_INPUT`
- `LANGFUSE_OBSERVATION_METADATA_AGENT_ROLE`
- `LANGFUSE_OBSERVATION_MODEL_NAME`
- `LANGFUSE_OBSERVATION_OUTPUT`
- `LANGFUSE_OBSERVATION_TYPE`
- `LANGFUSE_OBSERVATION_USAGE_DETAILS`
- `LANGFUSE_TRACE_TAGS`
- `LlmCallCompleted`
- `LlmCallStarted`
- `LlmGenAIMapper`
- `NamedRegistry`
- `OBSERVATION_TYPE_AGENT`
- `OBSERVATION_TYPE_GENERATION`
- `OBSERVATION_TYPE_TOOL`
- `ObservabilitySettings`
- `OperationOutcome`
- `OperationRecorder`
- `OtelProjector`
- `OtelTracer`
- `PluginAuthored`
- `PluginInspected`
- `PluginMountRejected`
- `PluginMounted`
- `PluginUnmounted`
- `PresetPublished`
- `ProjectionRegistry`
- `ReasoningCompleted`
- `ReasoningDelta`
- `RunActivity`
- `RunContext`
- `RunScope`
- `RunState`
- `RunStatus`
- `RunStore`
- `RuntimeKind`
- `RuntimeObserved`
- `SpanContextInfo`
- `SpanView`
- `StampedEvent`
- `StepCompleted`
- `StepTextDelta`
- `SynthesisCompleted`
- `TEAM_CONTAINER_ROLE`
- `TeamRunFinished`
- `TeamRunStarted`
- `TeamTraceProfile`
- `ToolCallStreaming`
- `ToolDenied`
- `ToolGenAIMapper`
- `ToolInvoked`
- `ToolStarted`
- `TraceInspector`
- `TraceReport`
- `TraceTool`
- `UnknownEventDescriptorError`
- `UnregisteredJournalEventError`
- `Verbosity`
- `adopt_run_scope`
- `annotate`
- `bind`
- `bind_backends`
- `bind_descriptors`
- `build_default_genai_registry`
- `build_default_registry`
- `current_bound`
- `current_context`
- `current_descriptors`
- `descriptor_for`
- `detached_span`
- `fold_run_state`
- `get_current_run_scope`
- `get_span_context`
- `langfuse_span_visible`
- `make_explain_failure_tool`
- `make_export_minimal_reproduction_tool`
- `make_find_optimization_tool`
- `make_inspect_trace_tool`
- `make_plugin_interaction_graph_tool`
- `may_export_externally`
- `objective_preview`
- `plan_steps_joined`
- `read_journal`
- `record`
- `record_operation`
- `record_runtime`
- `run_scope`
- `score`
- `set_actor`
- `set_session`
- `span`
- `stamped_to_journal_record`
- `stamped_to_record`
- `team_id_for`
- `traced`
