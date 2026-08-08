# Architecture Decision Records

本目录只保留架构思想与原则层面的决策记录；过程性文档（执行方案、评审、提案、
实现计划）与工具链/命名/清理类决策不在收录范围。

| ADR | 标题 | 核心决定 |
|---|---|---|
| [0001](0001-five-layer-separation.md) | 五层单向依赖分层 | Accepted |
| [0002](0002-cognitive-loop.md) | 认知闭环 perceive→think→act→observe→reflect→update | Accepted |
| [0004](0004-protocol-first-pluggability.md) | Protocol-First 可插拔设计 | Accepted |
| [0005](0005-composition-root-l4.md) | L4 组合根模式（注册/组装/门面三职责） | Accepted |
| [0007](0007-interop-mcp-a2a.md) | 原生互操作协议层（MCP / A2A） | Accepted |
| [0008](0008-framework-positioning.md) | 框架定位与差异化 | Accepted |
| [0015](0015-contracts-no-behavior-classes.md) | contracts/ 仅保留类型与接口，参考实现必须放在实现层 | Accepted |
| [0030](0030-team-domain-language.md) | Team 领域语言（Lead / Coordination） | Accepted |
| [0033](0033-declarative-agent-spec.md) | 声明式 AgentSpec 与协议化门面 | Accepted |
| [0034](0034-closed-team-strategy.md) | 封闭 TeamStrategy 与 TeamSpec 单一事实来源 | Accepted |
| [0035](0035-team-awareness-unified-session.md) | TeamAwareness —— 统一 lead 团队认知，废除会话分裂 | Accepted |
| [0036](0036-retire-financial-metaphor.md) | 废除金融隐喻——团队认知词汇统一为「回报记录 / 咨询义务」 | Accepted |
| [0037](0037-journal-as-truth.md) | Journal-as-Truth —— 执行日志为唯一真相，span 树降级为投影 | Accepted |
| [0038](0038-llm-stream-event-contract.md) | LLMAdapter 流式事件契约 | Accepted |
| [0040](0040-gateway-mode-catalog-contracts.md) | 协作模式契约单一事实源 — gateway/mode_catalog → TS 生成 | Accepted |
| [0041](0041-prompt-reasoner-stream-text-delta.md) | PromptReasoner 流式增量文本；answer-delta 归属前端投影 | Proposed |
| [0042](0042-role-library-and-auto-casting.md) | 角色库与自动组队 — 一句话 → 自动选角 → 既有 Team 执行 | Accepted |
| [0043](0043-markdown-files-charts-without-lobehub-ui.md) | Markdown/文件产物/图表能力扩展；不引入 @lobehub/ui | Accepted |
| [0044](0044-code-sandbox-adapters.md) | 代码沙箱适配器 — E2B / local microVM / Mock 多后端 | Accepted |

## 维护规则
- 推翻已有决定时，新建一篇标记 `Supersedes: ADR-XXXX`，不改旧文件
- 这类文档的价值在于记录某一时刻的判断，不在于时刻反映最新状态
- CI `tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 断言本表与 `docs/adr/*.md` 编号集合一致
