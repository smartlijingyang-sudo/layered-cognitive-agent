# ADR-0101 Followup: ToolCallStreaming partial preview — inline best-effort arguments

**状态**: Proposed — 2026-09-01
**作者**: LCA Agent
**取代**: 无（修订 ADR-0101 §5.1 / §5.3 关于 ToolCallStreaming 的字段定义）
**关联 ADR**: 0101 / 0065

## 0. 上下文

ADR-0101 PR-2 在 2026-08-29 删除了 `ToolCallStreaming` 的 `arguments_preview / code / language / command / ...` 等字段，只保留 `tool_name / tool_call_id / arguments_ref`，理由是"journal 不带 view-only 渲染字段"。ADR §5.1 把 ToolCallStreaming 设计为 `tool_name, tool_call_id, arguments_ref`，§5.1 末尾注释说"流式累积由调用方在 ToolCall 周期内多次 emit 同一 `arguments_ref` 完成"。

但**这条 streaming 路径在 PR-2 当时没真正落地**：

- `lca/cognition/brain/tool_call_stream.py` 保留了 `parse_partial_tool_args(raw)` 函数但**没有任何调用方**
- `lca/cognition/brain/llm_turn/executor.py` 在 `FUNCTION_CALL_ARGUMENTS_DELTA` 时调 `push_tool_call_stream()`，得到 frame 后只 emit `(tool_name, tool_call_id)`，**不传 `arguments_ref`**
- `tool_call_stream.py` 也没有 `EvidenceStore` 句柄，无法就地 `prepare_streaming()` / `append()`

后果：当前 streaming 阶段 ToolCallStreaming 事件只携带 `tool_name + tool_call_id`，**前端 LobeHub 拿到 21 个空 streaming 事件**（鸡兔同笼实测），必须在 `ToolStarted` 触发后才能拿到完整 args —— 视觉上"代码写完才一次性出现"，违反 LobeHub 的 stream-paint 期望。

## 1. 决策

**ToolCallStreaming 允许携带 inline `arguments_preview: Mapping[str, object]`（best-effort partial dict），但不视为事实账本字段，仅作为 SSE live 通道的 preview hint。**

具体规则：

| 维度 | ToolStarted | ToolCallStreaming |
|---|---|---|
| 字段 | `arguments`（inline dict）/ `arguments_ref` | 新增 `arguments_preview`（inline dict） |
| 数据来源 | 完整 args + `EvidencePolicy.should_inline()` 决策 | `parse_partial_tool_args(slot["raw"])` —— 在累积到 160 字符时调用 |
| 写入 disk jsonl | 写入 | **不写入**（view-only，stream-only） |
| 通过 SSE 推给前端 | 是 | 是（live 通道） |
| 视为"事实" | 是 | **否**（前端不得把 streaming preview 当作最终 args 来执行） |

`arguments_preview` 在 `ToolStarted` 触发后由前端覆盖：`ToolStarted.arguments` 是事实，`arguments_preview` 仅作为提示。

## 2. 字段设计

```python
@dataclass(frozen=True)
class ToolCallStreaming(JournalEvent):
    """LLM 正在流式生成工具调用参数（tool call arguments still streaming）。

    ADR-0101 + 本 followup:
    - ``tool_name`` / ``tool_call_id`` —— 关联 ToolStarted 的 invocation_id
    - ``arguments_preview`` —— best-effort partial dict (从 partial JSON 解析);
      仅作 SSE live preview,**不进 journal fact / 不进 evidence 平面**
    - ``arguments_ref`` —— ADR §5.3 设想的 streaming 累积引用;当前实现未启用
    """

    tool_name: str = ""
    tool_call_id: str = ""
    arguments_preview: Mapping[str, object] = field(default_factory=dict)
    arguments_ref: EvidenceRef | None = None
```

## 3. 写入策略

- `lca/infrastructure/observability/journal/engine/journal_io.py` 在 `stamped_to_record` 时检测 `arguments_preview` 空 —— 非空时**保留**（仍写入 jsonl）但标记为 preview 字段；为避免破坏 ADR §4.1 "journal 不再携带 view-only"原则，新增例外条款：

> ADR-0101 §4.1 例外：ToolCallStreaming.arguments_preview 保留进 journal，
> 因为它是事实"LLM 在这个时刻累积了 partial JSON `parse_partial_tool_args(raw)` 的结果"，不是渲染细节。但 **replay 工具不得依赖此字段**（ToolStarted.arguments 才是事实）。

- `lca/infrastructure/observability/journal/sse/frames.py` `stamped_to_sse_frame` 不变 —— SSE 透传该字段，前端可读。

## 4. 前端 patch 改动

`deploy/lobehub/patches/runtime/lcaJournal.ts`：

```ts
case 'ToolCallStreaming':
case 'ToolStarted': {
  // ADR-0101 followup: ToolCallStreaming.arguments_preview 也是 inline arguments,
  // 与 ToolStarted.arguments 同样 merge 进 projected.state。
  const baseState = (payload.plugin_state as Record<string, unknown> | undefined) ?? {};
  const rawArgs = payload.arguments ?? payload.arguments_preview;
  const merged = rawArgs && typeof rawArgs === 'object' && !Array.isArray(rawArgs)
    ? { ...baseState, ...(rawArgs as Record<string, unknown>) }
    : baseState;
  return { idHint: ..., kind: 'tool-start', state: merged, toolName: ... };
}
```

**前端 lobehub-ui 自带组件（builtin-tool-cloud-sandbox ExecuteCode 等）零改动** —— 它们读 `args.code`，patch 在 projected.state 里 merge 了 preview，UI 自然显示 streaming 代码。

## 5. ADR 修订条款

- ADR-0101 §4.1 增加例外：`ToolCallStreaming.arguments_preview` 是唯一例外
- ADR-0101 §5.1 ToolCallStreaming 字段定义更新为包含 `arguments_preview`
- ADR-0101 §5.3 inline 决策扩到 ToolCallStreaming：streaming preview 永远 inline（不强制 evidence），因为它本身是 best-effort

## 6. 验收

- V1：`tests/test_tool_event_facts.py` 新增 "streaming_preview_inline" —— 模拟 21 个 partial delta，验证 ToolCallStreaming.arguments_preview 在每个 emit 都被填充且 partial 解析失败时也不抛错
- V2：`tests/journal/test_journal_io.py` 验证 `stamped_to_record` 把 `arguments_preview` 写入 disk（不再 view-only）
- V3：手动 `lca-ops kernel serve` + 浏览器跑 executeCode 任务，确认 ToolCallStreaming 21 个事件后 LobeHub 即时显示 partial 代码
- V4：replay 工具仍按 `ToolStarted.arguments` 读 args（preview 仅作 hint）

## 7. 风险

- replay / journal-analyzer 工具误读 preview → 已在 V4 限制 preview 仅作 hint，replay 只信 ToolStarted.arguments
- partial 解析失败 → `parse_partial_tool_args` 已实现 fallback（regex 提取 code/command 等 string 字段）
- 字段增加 6 个文件改动，但都是增量字段，不破坏现有 schema