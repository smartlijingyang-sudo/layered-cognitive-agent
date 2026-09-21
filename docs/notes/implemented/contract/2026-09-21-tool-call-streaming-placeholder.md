# Agent Note: 工具调用参数生成期的轻量占位 EP（llm.tool_call.streaming）

Status: implemented

## Problem

LCA gateway 路径下，模型生成工具调用参数期间前端没有任何工具调用渲染。run_41fbd76ce118 中模型生成 executeCode 参数耗时 148.8 秒（completion_tokens=8636），期间 `FUNCTION_CALL_ARGUMENTS_DELTA` 在 `TelemetryLLMAdapter` 的流循环里被静默丢弃，`tools_calling` 只能等 LLM 结束后的 `step.tool_call.record` 才发布，前端一直静态。用户体感「思考准备写文档到真正写，中间前端是静态的」。

## Decision

新增 spine EP `llm.tool_call.streaming`，对齐 LobeHub 原生 `stream_chunk.tools_calling` 契约：

1. `lca/loop/emit/cognitive/llm.py` 新增 `emit_llm_tool_call_streaming`，`LlmSpineEmitter` 协议同步扩展。
2. `TelemetryLLMAdapter` 在首个带工具名的 `FUNCTION_CALL_ARGUMENTS_DELTA` 时发布一次该 EP（同一调用 id 去重）。
3. `EventTranslator` 把 `llm.tool_call.streaming` 映射为 `stream_chunk { chunkType: 'tools_calling' }`，参数留空；随后 `step.tool_call.record` 携带完整参数覆盖（前端 `preserveToolResultMessageIds` 按工具 id 合并）。
4. `llm.tool_call.streaming` 加入 `LLM_SPINE_EPS` 白名单。

关键约束：占位是进度事件，best_effort、可丢、**不携带参数增量**（ADR-0162）；不是 per-delta 事实落库（ADR-0157 的 31MB journal 教训）。完整工具参数仍由 `step.tool_call.record` 在 LLM 结束后落库。

## Alternatives considered

### 前端超时占位（无新 EP）

在 `stream_start` 后长时间无 text delta 时显示「正在调用工具…」骨架。被否：是猜测而非事实，无法显示工具名，长文本生成会误触发，其他消费者看不到 wire 缺口。

### per-delta 工具调用增量落 spine

把每个 `FUNCTION_CALL_ARGUMENTS_DELTA` 都作为事实记录。被否：ADR-0157 曾因此膨胀 journal 31MB 而退役该机制；工具参数是瞬态进度，不是事实。

### 仅提示词约束（消症状）

引导模型不要把大文档内联进工具参数。仍保留：作为配套手段（tool-wire-budget-harvest 已有先例），但不能解决 30 秒级参数生成的 UX 空白。

## Consequences

- 新 run 在工具调用参数生成开始时，前端立即出现工具卡片（复用原生 `tools_calling` 渲染组件）。
- `llm.tool_call.streaming` 只发一次、不带参数，journal 不膨胀。
- 回归测试：`tests/runtime/coordinator/test_event_translator.py` 覆盖 EP→`tools_calling` 映射；`tests/unit/observability/adapters/test_telemetry_llm_adapter.py` 覆盖同一调用只发一次。
- 相关审计：`docs/notes/plans/2026-09-16-resume-askuser-flow-audit.md` 的 Gap 家族不涉及本 EP；本 EP 只解决「生成中无反馈」，不改变 HITL 状态机。