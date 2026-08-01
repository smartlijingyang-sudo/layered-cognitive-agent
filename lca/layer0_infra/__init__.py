"""L0 基础设施层。

协议 → 子包 → 内置实现映射（ADR-0016）：

| 协议 | 子包 | 内置实现 |
|------|------|----------|
| LLMAdapter | llm_adapter/ | OpenAICompatAdapter, MockLLMAdapter |
| Tool | tools/ | CalculatorTool, WeatherTool |
| StateStore | state_store/ | InMemoryStateStore |
| AgentTransport | transport/ | InternalTransport, A2ATransport, MCPTransport |
| Observability | observability/ | ConsoleObservability, JsonlFileObservability |
| NamedRegistryProtocol | component_registry.py | NamedRegistry, ComponentRegistry |
"""
