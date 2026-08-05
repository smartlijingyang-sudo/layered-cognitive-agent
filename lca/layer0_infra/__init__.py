"""L0 基础设施层。

协议 → 子包 → 内置实现映射：

| 协议 | 子包 | 内置实现 |
|------|------|----------|
| LLMAdapter | llm_adapter/ | OpenAICompatAdapter, MockLLMAdapter |
| Tool | tools/ | CalculatorTool, WeatherTool |
| StateStore | state_store/ | InMemoryStateStore |
| AgentTransport | transport/ | InternalTransport, A2ATransport, MCPTransport |
| Telemetry (facade) | observability/ | ObservabilityHub + console/jsonl/memory/langfuse 导出器 |
| NamedRegistryProtocol | component_registry.py | NamedRegistry, ComponentRegistry |
"""
