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
- ... 共 127 项

**模块清单**:

- `lca/infrastructure/observability/adapters.py`
- `lca/infrastructure/observability/default_pricing.py`
- `lca/infrastructure/observability/diagnostic_emitters.py`
- `lca/infrastructure/observability/diagnostics.py`
- `lca/infrastructure/observability/engine.py`
- `lca/infrastructure/observability/event_catalog.py`
- `lca/infrastructure/observability/event_descriptor_env.py`
- `lca/infrastructure/observability/event_descriptor_registry.py`
- `lca/infrastructure/observability/event_descriptors_data.py`
- `lca/infrastructure/observability/event_doc.py`
- `lca/infrastructure/observability/event_enrichers.py`
- `lca/infrastructure/observability/facade.py`
- `lca/infrastructure/observability/fact_stream.py`
- `lca/infrastructure/observability/filesystem.py`
- `lca/infrastructure/observability/frames.py`
- `lca/infrastructure/observability/genai_mapping.py`
- `lca/infrastructure/observability/handles.py`
- `lca/infrastructure/observability/journal_backend.py`
- `lca/infrastructure/observability/journal_io.py`
- `lca/infrastructure/observability/langfuse_conventions.py`
- `lca/infrastructure/observability/live_tail.py`
- `lca/infrastructure/observability/llm.py`
- `lca/infrastructure/observability/llm_stream_activity.py`
- `lca/infrastructure/observability/mapping.py`
- `lca/infrastructure/observability/memory.py`
- `lca/infrastructure/observability/memory_adapter.py`
- `lca/infrastructure/observability/narrative_sidecar.py`
- `lca/infrastructure/observability/narrative_utils.py`
- `lca/infrastructure/observability/plan_narrative.py`
- `lca/infrastructure/observability/policy.py`
- ... 共 58 个
