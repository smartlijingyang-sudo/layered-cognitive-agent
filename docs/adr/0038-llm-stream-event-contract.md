# ADR-0038: LLMAdapter 流式事件契约

## 状态
Accepted

## 背景

以下三点为 2026-08 代码库核实事实：

1. **`LLMAdapter.stream()` 存在但未实现**：`OpenAICompatAdapter.stream()` 直接
   `raise NotImplementedError`；生产认知回路（`reasoner.py`）零调用方，但 Protocol
   已对外暴露流式接口。
2. **可观测性链路对流式调用断裂**：`TelemetryLLMAdapter.stream()` 硬编码 token
   为 0；`LlmCallCompleted.stream` 字段从未被赋值，journal / Langfuse 永远将流式
   调用记为非流式。
3. **`LLMResponse` / `TokenUsage` 是成本链路的单一事实源**，但流式路径无法产出
   终态用量。

OpenAI 于 2025 年引入 Responses API 及对应 SSE 事件类型；第三方 OpenAI 兼容后端
（如 vLLM）截至 2026 年对 `/v1/responses` 支持仍不可靠。DashScope 等真实 LLM
测试范例走 Chat Completions 兼容路径。

## 决定

### 一、引入 provider-neutral 流式事件契约

- 新增 `LLMStreamEventType` 枚举（contracts/atoms/enums.py），三个成员值与 OpenAI
  Responses SSE `type` 字符串对齐，便于未来 HTTP/SSE 网关零翻译转发。
- 新增 `LLMStreamEvent` dataclass（contracts/models/core/llm.py），`COMPLETED`
  事件携带 `LLMResponse`，复用现有终态结构。
- **不变式**：同一次调用下 `stream()` 终态 `COMPLETED.response` 与 `complete()`
  返回值逐字段相等；由 L0 共享 `build_llm_response()` 构造函数保证，非文档约定。
- **不加 `ERROR` 事件类型**：硬失败继续走 Python 异常传播，与 `complete()` 一致。

### 二、Protocol 破坏性变更

`LLMAdapter.stream()` 返回类型从 `AsyncIterator[str]` 改为
`AsyncIterator[LLMStreamEvent]`。所有结构性实现必须在同一改动中同步迁移。

### 三、OpenAICompatAdapter Strategy 化

- 单一 `OpenAICompatAdapter`（`name="openai-compat"` 不变），内部注册表 +
  Strategy 模式。
- **Responses API 保持默认**；Chat Completions 通过构造参数 `api=` 或环境变量
  `LLM_API_STYLE=chat_completions` 显式 opt-in。
- `openai_compat.py` 拆为子包（单文件 ≤250 行有效代码门禁）。
- Chat Completions 流式强制 `stream_options={"include_usage": True}`，确保终态
  chunk 携带 token 用量。
- 流被中断且未收到 usage chunk 时，Strategy 不伪造 `COMPLETED`；由
  `TelemetryLLMAdapter` 识别退化路径并打 warning。

### 四、Telemetry 修复

`TelemetryLLMAdapter.stream()` 透传事件；遇 `COMPLETED` 取真实 token；
`_record()` 新增 `stream: bool` 参数写入 `LlmCallCompleted.stream`。

## 放弃的方案

1. **拆成两个顶层 Adapter 类** —— 扩大 factory / 测试改动面，失去
   `OpenAICompatAdapter` 通用兼容层身份。
2. **新增 `ERROR` 流事件类型** —— 异常传播已是唯一错误通道。
3. **根据 `base_url` 自动探测 API style** —— 隐式行为不可预测，违反注册表 +
   显式配置原则。

## 后果

### 正面

- 流式调用首次有真实 token 计费与 `stream=True` journal 标记。
- 未来 HTTP/SSE 网关可零翻译转发事件名。
- Responses API 为默认路径；Chat Completions 仍可通过 `LLM_API_STYLE=chat_completions`
  或 `api=` 显式切换（第三方兼容后端 fallback）。

### 负面

- contracts 层一个 Protocol 方法返回类型不兼容变更；所有结构性实现（生产 3 处 +
  测试 5 处）必须同 PR 迁移。
- 第三方 OpenAI 兼容后端（如 vLLM、DashScope）若不支持 `/v1/responses`，需显式
  设置 `LLM_API_STYLE=chat_completions`。

## 明确排除

- 不把 `stream()` 接进 `reasoner.py` / 认知回路（零生产调用方，另立 ADR）。
- 不新增 `anthropic_llm.py`（与本次改造无关，契约设计对未来 adapter 友好）。
