# 2026-09-01 Run `run_b1294a33e55d` 失败 RCA 与修复计划

> 范围：定位 `traces/runs/run_b1294a33e55d/journal.jsonl`（3868 事件，31 MB，
> 3868 条事件 / 16 事件类型）反映的根因与共性问题。
>
> **状态：已替换为 ADR-0156「清退三处架构泄漏 —— facts/progress 分离、projection 隔离、phase 收口」。本文档作为 RCA 证据与症状索引保留，不再维护修复方案（修复方案见 ADR-0156）。**
>
> 引用链：`ADR-0156 → ADR-0037 / ADR-0063 / ADR-0069 / ADR-0070 / ADR-0075 / ADR-0077`

## 0. 触发证据

| 指标 | 数值 |
|---|---|
| Run | `run_b1294a33e55d` |
| 入站 | `InboxFollowupCreated` `2026-09-01T01:21:47Z`，`actor=user` |
| LLM 调用 | `LlmCallStarted ×4 / LlmCallCompleted ×2`（最后两次无 COMPLETED） |
| Tool 流 | `ToolCallStreaming ×3800`，其中 4 个 tool_call_id 单独占 1394 / 1330 / 1000 / 76 条 chunk |
| `AgentRunFinished` | `status=failed`，`error="The agent could not complete a required think.main step after 2 attempt(s)."`，`steps=4` |
| 末尾流 | `StepTextDelta channel=answer step=-1` 列出"已生成4张图"，与 failed 状态并存 |

## 1. 问题清单与定位

| # | 现象 | 定位 | 根因 |
|---|---|---|---|
| 1 | journal 单 run 31 MB / 3868 事件中 3800 是 `ToolCallStreaming`，单 tool_call_id 最多 1394 条 chunk | `lca/cognition/brain/llm_turn/executor.py:106-122` 每收到一个 `FUNCTION_CALL_ARGUMENTS_DELTA` 就 `record(ToolCallStreaming(...))`；`lca/infrastructure/observability/journal/jsonl/projector.py:_delta_key` 合并键不含 `ToolCallStreaming` | `ToolCallStreaming` 没有落入 `_coalesce_deltas`，每 chunk = 1 条事件；与 ADR-0101 followup 描述的"best-effort partial preview"目的偏离 |
| 2 | run 标记 failed 之后，仍向 SSE / LobeHub 推送 `channel=answer` 的成功式 closure 文本 | `lca/plugins/transport/webserver/handlers/runs/observability/artifact_closure.py:18-50`，`emit_artifact_closure_if_needed` 只看 `workspace.artifacts.snapshot()`，不读 `session.status` | terminal state 与 answer channel 输出解耦；C7 控制/观察分离在这里被打破 |
| 3 | reducer 把 `final_output` 写入并把 `WORKING` 改成 `COMPLETED`，绕过 StopDecision | `lca/runtime/reducer.py:272-285` `apply_artifact_closure` 末尾 `if state.status == TaskStatus.WORKING: state.status = TaskStatus.COMPLETED` | C4 Reducer 与 C7 冲突；reducer 不该独立改 status 终态 |
| 4 | `journal.jsonl.narrative.md` 不记录 `error` 字段，失败原因在 markdown 不可见 | `lca/infrastructure/observability/journal/stream/narrative_sidecar.py:138-150` `interesting` keys 列表不含 `error` | narrative sidecar 只对部分关键字段透明化 |
| 5 | `InboxFollowupCreated.payload_preview` 截 200 字符，原始 prompt 不落盘 | `lca/plugins/transport/webserver/handlers/runs/execute/loop_drivers.py:289-292` `payload_preview=question[:200]` | preview 截断后只能从 `AgentRunStarted.objective` 反推原文 |
| 6 | think.main 重试时 step 仍=3，未推进；`LlmCallStarted #1265 → #2666` 间隔 1 分钟以上但仍 `step=3` | `lca/plugins/phase_graph/recovery.py:39-66` reflect→think edge 反射回 `think.main`，但 `step` 字段在 phase 节点内不递增；LLM 调用日志 `step=3` 两次 | state.step 由 perceive_hub 推进，phase 节点本身不推动；重试期间 step 视觉冻结 |
| 7 | `LlmCallStarted ×4 / LlmCallCompleted ×2` 失衡：后两次 LLM 调用无 COMPLETED 事件 | `lca/cognition/brain/llm_turn/executor.py:127-130` `event.type == COMPLETED and event.response is not None: break`；若无 COMPLETED 则退到 129 行 `text=accumulated.strip()` 后再走 `_EMPTY_STREAM_COMPLETE_RETRIES` 循环 | 流断流（provider 未发 COMPLETED）→ 不发 `LlmCallCompleted`，导致 OTel gen_ai 缺记录、latency/usage 缺统计 |
| 8 | `phase_failure_stop_result` 输出空 `final_output`，用户看不到 explanation | `lca/plugins/phase_graph/failure_stop.py:64-78`，`StopDecision` 没传 `final_output`；`cognitive_agent._run_lifecycle:166-185` `finish_output = result.output or ""` | reducer 只看 `state.final_output`，而 failure_stop 没回填 |
| 9 | `AgentRunFinished.output_text` 永远空字符串 | 同上 `cognitive_agent._run_lifecycle:166-185`：`finish_output = result.output or ""`，但 `result.output` 在 declarative path 走 `TerminalOutcome.final_output_ref`（独立字段），不会回填 | UI / LobeHub 显示答案的来源不一致，跨路径 status 表达不可比 |
| 10 | `ToolCallStreaming` 默认落盘全量 chunk 占用磁盘和 narrative，narrative 被淹没 | 同 #1，影响扩展性 | 与 #1 同根 |
| 11 | **LobeHub UI 工具卡片标题 "Generate analysis charts" 一开始不渲染** | LobeHub 经 `lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts:736` `fetch('/lca-api/runs/{runId}/live')` 订阅 LCA webserver `GET /runs/{run_id}/live`（`lca/plugins/transport/webserver/handlers/runs/api/routes.py:275-300`）的 SSE；SSE 帧是 `stamped_to_sse_frame` (`lca/infrastructure/observability/journal/sse/frames.py:31-42`)。LobeHub 端 `lcaJournal.ts:96-118` 把 `ToolCallStreaming` 与 `ToolStarted` 都投影成 `tool-start`，合并 `arguments_preview`（早期只有 `code` 13 字符，没有 `description`）到 `state`；标题（`description`）需 `ToolStarted.arguments.description` 才齐全，但 PDF 生成那次因 phase 重试失败**根本没有 `ToolStarted`** | UI 标题依赖 `args.description`，空时显示 `shinyText` 占位；同根于 journal 上 `ToolCallStreaming.arguments_preview` 故意不发描述字段 |
| 12 | **工具调用全部是 X** | LobeHub `applyProjected('tool-start')` (`LcaRunDriver.ts:500-541`) 在 `ToolCallStreaming` 进来时调 `optimisticCreateMessage` 把工具占位进 chat，但**后续 phase failure 截断 → 不会有 `ToolInvoked`**，于是 `existing.result` 始终 undefined；前端 spinner 不收敛 → 渲染器把这条 tool 标成 failed/X | LobeHub 端不区分"流式占位"和"已落地工具"；同根于 LCA phase graph 重试时不会回填 ToolStarted/ToolInvoked 收尾事件 |
| 13 | **折叠打开有 `import os / os.makedirs(...) / from reportlab.lib.p` 多余片段** | LobeHub `lcaJournal.ts:108-110` `merged = { ...baseState, ...rawArgs }` 把 `arguments_preview.code`（**累积整段 Python**，每 chunk 都重发）合并到 `state`；`LcaRunDriver.ts:41-50` 的 `ARG_KEYS` 包含 `code`，`pickArgs` (`LcaRunDriver.ts:80-85`) 把 `state.code` 序列化为 `call.function.arguments`；折叠面板把 `arguments.code` 整段渲染 | journal 上的 `ToolCallStreaming.arguments_preview.code` 是累积式而非 delta，每条事件都把整段 Python 重发一次；同根于 `lca/cognition/brain/llm_turn/executor.py:106-122` 把每 chunk 都构造整段累积字典 |

### 1.1 三个 UI 现象的因果链（同根：LCA 把整段累积 code 放进 ToolCallStreaming）

```text
LLM streaming (qwen3.7-plus)
    ↓ FUNCTION_CALL_ARGUMENTS_DELTA  (文本增量 ~ 字符级)
executor.py:106-122  parse_partial_tool_args(raw)  ← 累积整段 Python
    record(ToolCallStreaming(tool_call_id, arguments_preview={code: <累积全文>}))  ← 每 chunk 一次
    ↓ journal/SSE
stamped_to_sse_frame → SSE event: ToolCallStreaming, data={..., arguments_preview: {code: <累积全文>}}
    ↓ /lca-api/runs/{id}/live
LobeHub LcaRunDriver.fetch(/lca-api/runs/.../live) → readSse → projectJournalFrame
    tool-start(state = {...plugin_state, ...arguments_preview})
    ↓
LcaRunDriver.applyProjected('tool-start')
    pickArgs(state) → arguments.code = <累积全文>
    handler.handleChunk({tool_calls: [{function: {arguments: JSON.stringify({..., code: <累积全文>)}}]})
    ↓
chat 渲染器 折叠面板打开 → 把 arguments.code 整段渲染
```

> **错误原因纠正（2026-09-01 复审）**：初版报告把这三个 UI 现象归因到 OpenAI wire
> 缺 `delta.tool_calls` 增量。**实际不经过 OpenAI 兼容路径**：LobeHub 桌面端通过
> `LcaRunDriver.fetch('/lca-api/runs/{run_id}/live')` 直接订阅 LCA webserver 的
> `GET /runs/{run_id}/live` SSE，前端流式事件来自 `stamped_to_sse_frame` 原样
> 序列化 journal 事件。三个缺陷的共同根因是 **LCA 在 `ToolCallStreaming.arguments_preview.code`
> 里塞的是累积全文而非 delta**。

## 2. 修复方案 → 已被 ADR-0156 替代

**本文档不再维护修复方案**。13 个 RCA 症状最终被 ADR-0156 折叠为 3 个 seam 重写：

| ADR-0156 重构 | 覆盖本文档哪些症状 |
|---|---|
| **A. 双通道流** | 症状 #1（journal 31 MB）、症状 #11/13（折叠/标题错位）、症状 #10（narrative 淹没） |
| **B. Projection 隔离** | 症状 #2（failed 仍推 answer 流）、症状 #3（reducer 改 status）、症状 #8/9（final_output 空） |
| **C. PhaseFactsensor** | 症状 #4（narrative 不记 error 字段外，关于 phase 收口的全部）、症状 #6/7（重试期间 step / LlmCallCompleted 失衡） |

独立症状（与三处泄漏无直接因果关系，仍需单独处理）：

- **症状 #5（payload_preview 截 200 字符）** → 写入 ADR-0156 之前，需独立提交 PR；不阻塞 ADR-0156。
- **症状 #6（重试期间 step 不递增）** → 已被 ADR-0156-C 副作用消除：factsensor 收口后 phase graph 重试语义在 logs 里有完整事实链，step 是否递增不再影响 UI。

**修复方案全文与机械验证矩阵见 `docs/adr/0156-eliminate-projection-and-progress-leakage.md` §「后果」与 §「验证约束」**。

### 历史 PR 提案（已被 ADR-0156 替代）

> 早期版本曾把修复方案拆为 10 个 PR（PR-1 ~ PR-10）。本节保留作为错误方案的反面教材，**禁止按本节执行**。
>
> 错误点：
> - PR-1~PR-3、PR-8 是对 reducer / finalizer / artifact_closure 的局部补丁，未触及 projection 隔离的本质；
> - PR-4、PR-9 是对 ToolCallStreaming 的字段级修补，未触及事件本身错位在 journal 的本质；
> - PR-5、PR-6 是 LLM 流断流与 step 计数修补，被 ADR-0156-A 与 ADR-0156-C 副作用消除；
> - PR-7 是 InboxFollowupCreated 字段截断，独立于 ADR-0156；
> - PR-10 是 phase 退出多发事件，被 ADR-0156-C 的 PhaseFactsensor Protocol 通用收口取代。
>
> ADR-0156 §「决策」一、二、三分别对应这 10 个 PR 的本质修复。所有 PR 的机械验证约束已合并到 ADR-0156 §「验证约束」一节。

**目标**：run 标记 failed / canceled 时，不再向 SSE 推送 channel=answer 的 closure 文本；UI 看到的最终状态与 journal 一致。

- 文件：
  - `lca/plugins/transport/webserver/handlers/runs/observability/artifact_closure.py:18-50`
    - 在 `emit_artifact_closure_if_needed` 中先读 `session.status.value`，仅在 `COMPLETED` / `DEGRADED` 时发 channel=answer；其他状态时改为 `channel=decision`（或不发）。
    - 同步把"已发"标记写到 `session.observability` 上下文，避免重复。
  - `lca/plugins/transport/webserver/handlers/runs/terminal/terminalizer.py:49-60`
    - `_emit_artifact_closure_if_needed` 调用之前先 `_derive_terminal_status(session, success)`，确保 session.status 已收敛再决定是否推 answer。
- 验证：
  - `uv run ruff check --fix lca/plugins/transport/webserver/handlers/runs/observability/ lca/plugins/transport/webserver/handlers/runs/terminal/`
  - 新增单元测试 `tests/transport/webserver/handlers/runs/test_artifact_closure_status_gate.py`：分别 mock `session.status=FAILED/COMPLETED/INPUT_REQUIRED`，断言 `StepTextDelta` 是否落 journal store，以及 `channel` 字段。
  - `uv run pytest tests/transport/webserver/handlers/runs/ -q`

### PR-2 — Reducer 收敛：artifact closure 不再独立改 status

**目标**：reducer 严格做事实应用，不参与终态收敛决策（恢复 C4 / C7）。

- 文件：
  - `lca/runtime/reducer.py:272-285` `apply_artifact_closure`
    - 删除 `if state.status == TaskStatus.WORKING: state.status = TaskStatus.COMPLETED`
    - 仅当 `state.final_output` 为空时才写入 closure 文本；不再触发 COMPLETED。
  - `lca/runtime/result_finalizer.py:48-55` `finalize`
    - 保证 `apply_error` / `apply_paused` / `apply_terminal_outcome` 永远最后写。
  - `lca/plugins/phase_graph/stop_policy.py:104-128` `_budget_exhausted_decision`
    - `final_output` 来源改为 `decision.response_text`（与 `_completed_decision` 一致），不再依赖 `artifact_closure.synthesize()` 来决定 status。
- 验证：
  - `tests/runtime/test_reducer.py`：覆盖 `apply_artifact_closure` + 后续 `apply_error` / `apply_terminal_outcome`，验证 status 收敛于最终一次调用。
  - `tests/plugins/phase_graph/test_stop_policy.py`：覆盖 budget-exhausted + 无 output 的情况。

### PR-3 — narrative sidecar 记录 error 字段

**目标**：journal narrative markdown 显示失败原因，不需要打开 jsonl。

- 文件：
  - `lca/infrastructure/observability/journal/stream/narrative_sidecar.py:138-150`
    - `interesting` keys 增加：`error`, `failure.message`, `attempts`, `plan_ref`, `causation.parent_event_id`, `prev_event_type`, `output_text_preview`。
  - 文档：`docs/observability/journal.md` 或 README 补一句。
- 验证：
  - `tests/infrastructure/observability/journal/stream/test_narrative_sidecar.py`：构造一个 `AgentRunFinished status=failed error="..."` 事件，断言 markdown 包含 `error=`。
  - 全量回归 `tests/infrastructure/observability/journal/`。

### PR-4 — ToolCallStreaming 按 tool_call_id 合并落盘

**目标**：journal 体量降至原来的 1% 量级；narrative 可读。

- 文件：
  - `lca/infrastructure/observability/journal/jsonl/projector.py:_delta_key`
    - 增补 `("ToolCallStreaming", stamped.tool_call_id)` 合并键。
  - `lca/infrastructure/observability/journal/jsonl/projector.py:_coalesce_deltas`
    - 合并逻辑：保留首条 `tool_name` / `tool_call_id`，将 `arguments_preview` 累积字典；合并 `seq` 为首条 seq。
  - `lca/cognition/brain/llm_turn/executor.py:106-122`
    - 改：每 chunk 仍 record `ToolCallStreaming`，但 projector 合并；不再要求 stream projector 端立刻吞掉 preview（合并时取最后一段的 preview 作为最终值）。
  - `lca/contracts/models/observability/journal.py:393-413` 文档
    - 字段语义从"每 chunk 一条"调整为"按 tool_call_id 合并后一条 + live tail 仍推原始 delta"。
- 验证：
  - `tests/infrastructure/observability/journal/jsonl/test_projector.py`：新增 `ToolCallStreaming` 合并测试（同 tool_call_id → 1 条；不同 tool_call_id → N 条）。
  - `tests/cognition/brain/llm_turn/test_executor.py`：回归（流式场景）。
  - `tests/lobehub/test_sse_encoder.py`：SSE 仍实时推 chunk，不受落盘合并影响。

### PR-5 — 修复 LlmCallCompleted 在流断流时仍发出

**目标**：每次 `LlmCallStarted` 必须有对应 `LlmCallCompleted`，便于 OTel 投影、latency / usage 统计。

- 文件：
  - `lca/cognition/brain/llm_turn/executor.py:88-140` `stream_then_collect_response`
    - 用 `try/finally` 包住 async for；在 `finally` 中按"started=True → emit `LlmCallCompleted(ok=False, latency_ms=elapsed, error=...)`"。
    - 在 `_EMPTY_STREAM_COMPLETE_RETRIES` 路径补 1 条 COMPLETED 占位（如果最终拿到了响应则覆盖为 ok=True）。
  - `lca/contracts/models/observability/journal.py:381-393` `LlmCallCompleted` 字段
    - 文档补一段"流断流时 ok=False, error 字段保留 provider 错误信息"。
- 验证：
  - `tests/cognition/brain/llm_turn/test_executor.py`：mock provider stream 提前 close，断言 1 个 LlmCallCompleted (ok=False)。
  - `tests/infrastructure/observability/journal/`：对 reducer / projector 的事件成对约束。

### PR-6 — phase graph 重试期间推进 step 计数

**目标**：reflect→think 重试时 step 仍按 step 增长，上层 step-bound 不再视觉冻结。

- 文件：
  - `lca/harness/declarative/compile/phase_execution_policy.py:60-110`
    - 每次 attempt 之前调用 `_attempt_prelude()` 推进一次 step（写入 StampedEvent 触发 reducer）。
  - `lca/cognition/perceive_hub.py:73,101,118` 与 `lca/cognition/hook_registry.py:105-119`
    - 检查：是否应当在每次 phase attempt 进入前显式调 `state.step += 1`；如已有则在 declarative policy 入口接入。
- ADR（必需）：新增 `docs/adr/0152-phase-step-increment.md`（草案），描述为什么 phase 重试需要推进 step、如何与 perceive step 区分。
- 验证：
  - 单元：`tests/declarative/test_phase_execution_policy.py`：构造 policy.max_attempts=2 的场景，断言 step 计数。
  - 集成：`tests/integration/test_run_recovery.py`：走完一次 reflect→think 反弹，断言最终 `state.step` 等于预期值。

### PR-7 — InboxFollowupCreated 不再截断 payload_preview（或同步落盘原文）

**目标**：用户原文可在 journal 中无损检索。

- 文件：
  - `lca/plugins/transport/webserver/handlers/runs/execute/loop_drivers.py:289-292`
    - `payload_preview` 改为 `payload_preview=question[:2000]`（足够长），同时把 `payload` 字段（无截断）写入 `data` 字典（journal 默认 schema/2 接受任意 data 字段）；`InboxFollowupCreated` model 增加可选 `payload: str | None` 字段。
  - `lca/contracts/models/observability/journal.py:InboxFollowupCreated`
    - 加可选字段 `payload: str | None = None`，`_doc.summary` 补说明。
- 验证：
  - `tests/contracts/observability/test_journal_models.py`：构造事件，断言 `payload` 完整保留。
  - `tests/transport/webserver/handlers/runs/test_loop_drivers.py`：长 prompt 测试。

### PR-8 — failure_stop / _run_lifecycle 把 failed 解释回填到 final_output

**目标**：run failed 时 UI 至少看到简短 explanation（不含 raw exception）。

- 文件：
  - `lca/plugins/phase_graph/failure_stop.py:64-78`
    - 在 `StopDecision` 里补 `final_output=diagnostic.message`，作为"用户可读 explanation"。
  - `lca/agent/cognitive_agent.py:166-185`
    - `finish_output = result.output or diagnostic.message or ""`（如果 result 没携带 output，则取最后一次 failure 的解释）。
  - `lca/runtime/reducer.py:135-145` 终态分类时同样支持 `state.last_error` 也作为 final_output 兜底（只对 FAILED，且原 final_output 为空）。
- 验证：
  - `tests/plugins/phase_graph/test_failure_stop.py`：断言 StopDecision.final_output == diagnostic.message。
  - `tests/agent/test_cognitive_agent_lifecycle.py`：mock runtime 抛 PhaseExecutionExhaustedError，断言 AgentRunFinished.output_text 含 explanation。

### PR-9 — ToolCallStreaming.arguments_preview 改 delta 协议 + 截断 code

**目标**：消除"LobeHub 折叠面板出现整段 Python / 工具标题一开始不渲染 / 工具调用全部是 X"三处 UI 缺陷。实际根因不是 OpenAI wire（见 §1.1 末尾纠错段），而是 **LCA 在 `ToolCallStreaming.arguments_preview.code` 里塞的是累积全文而非 delta**，且 phase graph 重试失败不会回填 `ToolStarted` / `ToolInvoked`，导致 LobeHub 把"占位卡片"误认成"失败工具"。

- 文件：
  - `lca/cognition/brain/llm_turn/executor.py:106-122` `_record_tool_streaming`
    - 改：`arguments_preview.code` 不再塞累积全文，改为：
      1. 发出真正的 `arguments_delta`（最近 ~160 字符新增）；
      2. 仅当累计字典可完整 parse 时才发 `arguments_preview`；
      3. 单 chunk → 单字段增量，不冗余整段。
    - 新增字段 `arguments_delta: str = ""` 到 `ToolCallStreaming` (`lca/contracts/models/observability/journal.py:393-413`)。
  - `lca/contracts/models/observability/journal.py:393-413` `ToolCallStreaming`
    - 加 `arguments_delta: str = ""` 字段（ADR-0101 followup 兼容增量语义）；`arguments_preview` 仅在完整可解析时存在，避免整段冗余。
  - `lca/infrastructure/observability/journal/jsonl/projector.py:_coalesce_deltas`
    - 合并逻辑更新：`arguments_delta` 字符串追加；`arguments_preview` 取最后一段（不再累积）。
  - `lca/infrastructure/observability/journal/stream/fact_stream.py:473`
    - 渲染时不再累积 `arguments_preview.code` 到 narrative（避免淹没 narrative）。
    > **事后修正（2026-09-02, ADR-2026-09-02-i17-stream-align §A）**:`fact_stream.py` 整文件已删除,narrative 渲染由 `lca/infrastructure/observability/journal/step/narrative_writer.py:_render_tool_streaming` 接管,等价行为。
- 验证：
  - `tests/cognition/brain/llm_turn/test_executor.py`：构造 50 chunk stream，断言 `arguments_delta` 是字符级增量，journal 中 50 条 ToolCallStreaming 的 `arguments_delta` 拼接等价于完整 code，但每条 <=160 字符。
  - `tests/infrastructure/observability/journal/jsonl/test_projector.py`：tool_call_id 合并后 arguments_delta 拼接应等于原始累积全文。
  - `lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts:96-118` `projectJournalFrame` 同时更新：
    - 合并 `arguments_delta`（追加）而不是合并 `arguments_preview.code`（覆盖累积）；
    - `mergeInvocationArgs` 保留当前 `pickArgs` 对 `description`/`language` 等短字段的取用，对 `code` 字段改为"累计只在 ToolStarted 那一刻拉一次"，中间过程 code 仍能进 state 但不应触发 `tool_calls` chunk 重复发送整段。
  - 端到端：用 `lca-ops runs/send` 走一次"分析 PDF"任务，LobeHub 桌面端打开 :3010，断言折叠面板展开后展示的是 `description` + code 截断/折叠状态，不出现完整 Python 全文。
- ADR：新建 `docs/adr/0153-toolcallstreaming-preview-delta.md`（草案），描述：
  - `arguments_preview` 仅可解析时存在；
  - `arguments_delta` 是字符级增量；
  - journal 上的累积责任在 client side（`mergeInvocationArgs`），不再由 LCA server 重复发送。
- 风险：与 PR-4（合并落盘）有重叠。两 PR 都想合并 ToolCallStreaming，建议**先合 PR-4（journal projector 合并键）再上 PR-9（delta 语义改 wire）**。

### PR-10 — ToolCallStreaming 在 phase 重试失败路径上发 `ToolCancelled`

**目标**：phase graph 重试失败/超时/取消时，journal 显式发出 `ToolCancelled` / `ToolFailed` 事件，让 LobeHub 的 `applyProjected` 能结束 placeholder spinner，避免"工具全部是 X"和"标题始终 placeholder"。

- 文件：
  - `lca/contracts/models/observability/journal.py`：新增 `ToolCancelled(tool_call_id, reason)` / `ToolFailed(tool_call_id, error)` JournalEvent。
  - `lca/plugins/phase_graph/recovery.py:39-66` 与 `lca/harness/declarative/compile/phase_execution_policy.py:60-110`
    - 重试失败时把所有"流式占位"的 tool_call_id（最近感知到的 `ToolCallStreaming`）合成 `ToolCancelled` 事件。
  - `lca/plugins/transport/webserver/handlers/runs/api/routes.py:275-300` `stream_run_live` 与 `stamped_to_sse_frame`
    - `ToolCancelled`/`ToolFailed` 走普通 SSE 帧输出（已经是默认）。
  - `lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts:96-178` `projectJournalFrame`
    - 新增 case `ToolCancelled` / `ToolFailed` → `kind: 'tool-cancelled' | 'tool-failed'`，LcaRunDriver 收到后调用 `dispatchMessage` 把对应 placeholder 改成终止态。
- 验证：
  - `tests/cognition/brain/llm_turn/test_executor.py`：流断流时 journal 含 1 个 `LlmCallCompleted(ok=False)`；phase 重试失败时 journal 含 N 个 `ToolCancelled`。
  - `tests/plugins/phase_graph/test_recovery.py` / `tests/declarative/test_phase_execution_policy.py`：触发 think.main 重试耗尽 → journal 末尾有 ToolCancelled 而非直接 AgentRunFinished。
- ADR：新建 `docs/adr/0154-tool-cancelled-event.md`，确认新事件 catalog 合法（与 C1 闭集一致）。


## 3. 验证矩阵

完整机械验证约束（每条 `uv run <cmd>` 直跑）见 ADR-0156 §「验证约束」一节。

## 4. 落地顺序（替代原 PR 提案）

按 ADR-0156 §「落地顺序（机械可验证）」执行（5 个 seam × 3 commit = 15 个 atomic commit）：

1. **重构 A（双通道流）** 3 个 commit：
   - commit 1：新增 `ProgressStream` Protocol + 默认实现，所有 `record(ToolCallStreaming(...))` 改为 `progress.emit(...)`。
   - commit 2：journal catalog 删除 `ToolCallStreaming`；`live_tail.py` 拆 `iter_journal_sse` + `iter_progress_sse`；SSE 端点双通道。
   - commit 3：LobeHub `lcaJournal.ts` 拆为 `lcaJournalFacts.ts` + `lcaProgressStream.ts`；删除 ToolCallStreaming 单元测试。

2. **重构 B（Projection 隔离）** 3 个 commit：
   - commit 1：新增 `ArtifactClosureProjection` Protocol；`stop_policy.py` 改为 `final_output=decision.response_text`。
   - commit 2：reducer Protocol 移除 `apply_artifact_closure`；reducer.py 删除方法；`finalizer` 改为 `progress.emit`。
   - commit 3：`AgentState.final_output` 字段删除；`TerminalOutcome.final_output_ref` 改 `TextRef` / `ArtifactRef` / `StructuredRef`；`Result.from_state(state)` 删除。

3. **重构 C（PhaseFactsensor）** 3 个 commit：
   - commit 1：新增 `PhaseFactsensor` Protocol + `ToolCallPhaseFactsensor` 默认实现 + journal catalog 增加 `ToolCancelled` / `ToolFailed`。
   - commit 2：`GenericPlanInterpreter` / `execute_with_policy` 集成 factsensor；`ToolCallStream` 槽管理加 `has_invoke_event`。
   - commit 3：LobeHub `applyProjected` 加 `tool-cancelled` / `tool-failed` case。

4. **重构 D（LlmCallLifecycleGuard）** 3 个 commit：
   - commit 1：新增 `LlmCallLifecycleGuard` Protocol + `DefaultLlmCallLifecycleGuard` 默认实现；boot 注册。
   - commit 2：`executor.py:stream_then_collect_response` 重构接 `lifecycle_guard`；happy path / 流自然结束 / 异常路径都必产 `LlmCallCompleted`；删除 happy path 直发旧代码。
   - commit 3：provider stream 提前 close mock 测试，断言 `LlmCallCompleted.ok=False` 仍 commit；narrative.md 显示 LlmCallCompleted 完整。

5. **重构 E（StepClock）** 3 个 commit：
   - commit 1：新增 `StepClock` Protocol + `DefaultStepClock` 默认实现 + journal catalog 增加 `StepAdvanced(step, source, at)`。
   - commit 2：`perceive_hub.py` 改读 `step_clock.current()` 取代 `state.step`；`phase_execution_policy.py:execute_with_policy` 每次 attempt 入口调 `step_clock.advance()`；删除 `state.step += 1` 散落写入点。
   - commit 3：`cognitive_agent._run_lifecycle` 与 terminal outcome 投影也读 `step_clock.current()`，不读 state.step；步骤计数 UI 由 StepAdvanced 序列驱动。

每步跑 ADR-0156 §「验证约束」中的对应测试 + `lint` + `mypy` + `pytest`。
