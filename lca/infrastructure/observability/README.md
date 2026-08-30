# lca.infrastructure.observability

> 状态：稳定 | 草稿 | 弃用
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
lca/infrastructure/observability. 外部世界：文件、LLM、网络、进程、存储、观测、插件内核。具体职责见各包 docstring；本 README 由脚手架生成，待包负责人补充。

## 2. 不负责
认知决策、阶段编排、组合根

## 3. 输入
{{inputs}}

## 4. 输出
{{outputs}}

## 5. 允许依赖
lca.contracts,lca.infrastructure

## 6. 禁止依赖
lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins,gateway

## 7. 副作用
file:read,file:write,network:openai,log:emit,subprocess:spawn

## 8. 失败语义
{{failure_semantics}}

## 9. 公共入口
`EVENT_DESCRIPTOR_REGISTRY`, `FRAMEWORK_TAG`, `JOURNAL_EVENT_CLASSES`, `LANGFUSE_ENVIRONMENT`, `LANGFUSE_OBSERVATION_INPUT`, `LANGFUSE_OBSERVATION_METADATA_AGENT_ROLE`, `LANGFUSE_OBSERVATION_MODEL_NAME`, `LANGFUSE_OBSERVATION_OUTPUT`, `LANGFUSE_OBSERVATION_TYPE`, `LANGFUSE_OBSERVATION_USAGE_DETAILS`, `LANGFUSE_TRACE_TAGS`, `OBSERVATION_TYPE_AGENT`, `OBSERVATION_TYPE_GENERATION`, `OBSERVATION_TYPE_TOOL`, `TEAM_CONTAINER_ROLE`, `ActionDegraded`, `AgentRunFinished`, `AgentRunStarted`, `AttributePolicy`, `BoundObservability`, `CastingCompleted`, `CastingFailed`, `CastingStarted`, `DecisionMade`, `DelegationCacheHit`, `DelegationCompleted`, `DelegationIssued`, `DelegationMechanism`, `DiagnosticCategory`, `DiagnosticEvent`, `DiagnosticStatus`, `DuplicateEventDescriptorError`, `EventAudience`, `EventDescriptor`, `EventDurability`, `EventPlane`, `EventProjection`, `EventSensitivity`, `InMemoryEventDescriptorRegistry`, `InMemoryJournalStore`, `JournalEvent`, `JournalProjector`, `JournalSchemaMeta`, `JournalStoreBackend`, `LlmCallCompleted`, `LlmCallStarted`, `LlmGenAIMapper`, `NamedRegistry`, `ObservabilitySettings`, `OperationOutcome`, `OperationRecorder`, `OtelProjector`, `OtelTracer`, `PluginAuthored`, `PluginInspected`, `PluginMountRejected`, `PluginMounted`, `PluginUnmounted`, `PresetPublished`, `ProjectionRegistry`, `ReasoningCompleted`, `ReasoningDelta`, `RunActivity`, `RunContext`, `RunScope`, `RunState`, `RunStatus`, `RunStore`, `RuntimeKind`, `RuntimeObserved`, `SpanContextInfo`, `SpanView`, `StampedEvent`, `StepCompleted`, `StepTextDelta`, `SynthesisCompleted`, `TeamRunFinished`, `TeamRunStarted`, `TeamTraceProfile`, `ToolCallStreaming`, `ToolDenied`, `ToolGenAIMapper`, `ToolInvoked`, `ToolStarted`, `TraceInspector`, `TraceReport`, `TraceTool`, `UnknownEventDescriptorError`, `UnregisteredJournalEventError`, `Verbosity`, `adopt_run_scope`, `annotate`, `bind`, `bind_backends`, `bind_descriptors`, `build_default_genai_registry`, `build_default_registry`, `current_bound`, `current_context`, `current_descriptors`, `descriptor_for`, `detached_span`, `fold_run_state`, `get_current_run_scope`, `get_span_context`, `langfuse_span_visible`, `make_explain_failure_tool`, `make_export_minimal_reproduction_tool`, `make_find_optimization_tool`, `make_inspect_trace_tool`, `make_plugin_interaction_graph_tool`, `may_export_externally`, `objective_preview`, `plan_steps_joined`, `read_journal`, `record`, `record_operation`, `record_runtime`, `run_scope`, `score`, `set_actor`, `set_session`, `span`, `stamped_to_journal_record`, `stamped_to_record`, `team_id_for`, `traced`

