# ADR-0007: 原生互操作协议层（MCP / A2A）

## 状态
Accepted

## 背景
Agent 生态正在快速标准化。MCP（Model Context Protocol）和 A2A（Agent-to-Agent）已成为主流云厂商共同支持的协议。如果框架自建封闭协议，后续接入外部工具/Agent 时需要额外的适配层。

## 决定
在 L0 基础设施层原生内置协议适配：

- **MCP**：工具协议适配——框架内的 `ToolProtocol` 可直接对接 MCP Server/Client
- **A2A**：Agent 间通信适配——`AgentTransport` Protocol 支持 A2A 协议的 `send_task` / `poll_status` / `receive_result`
- **DelegationSpec.protocol**：`Literal["internal", "a2a", "mcp"]`，委派时可选择通信协议

协议层本身可插拔——`AgentTransport` 是 Protocol，第三方可以实现自己的协议适配而不改框架代码。

## 放弃的方案
- **不内置协议支持，靠社区集成**：短期轻量，但长期每个用户都要自己写适配——重复劳动。
- **只支持一种协议**：MCP 和 A2A 解决不同问题（工具 vs Agent 间通信），不应二选一。

## 后果
- 正面：框架内的 Agent 能直接与框架外的工具/Agent 协作；符合行业标准化方向。
- 负面：原生集成增加框架体积——但鉴于 MCP/A2A 已是事实标准，长期互操作性收益远大于短期成本。
