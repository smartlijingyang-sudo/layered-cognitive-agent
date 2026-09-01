# ADR-0157：ToolCallStreaming 按 tool_call_id 合并 + executor emit 真实 delta

## 状态

**Revised — 2026-09-01**(由 subagent 深度评审后重做。原 ProgressStream 双通道方案作废)

Supersedes: ADR-0156 §「决策 一」 / 原 ADR-0157 v1

Refines: ADR-0063 §I6 (动态扩展不扩张核心原语)、ADR-0101 followup 注释 (ToolCallStreaming 仅作 live preview,ToolStarted.arguments 才是事实)、ADR-0037 (journal-as-truth)

## 背景

`run_b1294a33e55d` RCA 暴露 `ToolCallStreaming` 占据 3800 / 3868 journal entries(31 MB / run)。症状包括:
- journal 体量膨胀、narrative 被淹没
- LobeHub `lcaJournal.ts:108-110` 把 `arguments_preview.code` 累积全文误当 delta 合并
- 工具标题 `description` 在 phase 重试失败时缺失(无 `ToolStarted.arguments.description`)

## 第一性原理:已有机制可以直接承担

LCA 已经具备以下成熟机制(subagent 评审发现,grep 仓库全文件可验证):

1. **`EventDurability.best_effort`**(`lca/contracts/models/observability/event.py:49-53`):
   - `ToolCallStreaming` 的 EventDescriptor 已标注 `durability="best_effort", retention="short"`(`event_descriptors_data.py:395-403`)
   - `StepTextDelta` / `ReasoningDelta` / `SandboxOutputDelta` 都是同模式,**完整表达"可丢、可不持久"的 progress 语义**

2. **`JsonlJournalProjector._delta_key` 合并键**(`lca/infrastructure/observability/journal/jsonl/projector.py:80-95`):
   ```python
   if isinstance(event, StepTextDelta):
       return ("StepTextDelta", event.step, event.channel)
   if isinstance(event, ReasoningDelta):
       return ("ReasoningDelta", event.step)
   if isinstance(event, SandboxOutputDelta):
       return ("SandboxOutputDelta", event.invocation_id, event.stream)
   return None  # ← ToolCallStreaming 在这里返回 None,所以不被合并
   ```
   - 流式增量按 `(类型, step/invocation, channel/stream)` 在落盘前拼成一次完整文本
   - 注释明确:"LiveTail / SSE 仍接收原始增量"
   - **ToolCallStreaming 完全可套同一范式**,无需新增 ProgressStream 协议

3. **`LiveTail` pub/sub**(`lca/infrastructure/observability/journal/stream/live_tail.py:50-241`):
   - 已有 ring buffer、subscriber queue、LiveGap 协议、SSE 编码、channel 过滤
   - 完整覆盖"journal 侧的 pub/sub"职责

4. **`StepTextDelta.channel: str` 字段**(`journal.py:332`):
   - channel 已经是 payload 内字段,不是 envelope tag
   - SSE 层用 event 名区分即可,不污染 envelope

## 原方案错在哪里

ADR-0157 v1 错误地把已经存在的 `best_effort` 语义重新发明为:

- `ProgressStream` Protocol + `ProgressFrame` dataclass
- `stamped_to_record` 加 `channel` 字段(污染 envelope,违反 §I6)
- SSE 双通道(`iter_journal_sse + iter_progress_sse`)
- LobeHub 双文件、双 consumer

总计 7 个新文件、零行为改善。这违反 AGENTS.md §3 C6 最小化原则。

## 决策(减法)

### 一、`_delta_key` 增加 ToolCallStreaming 合并键(3 行)

`lca/infrastructure/observability/journal/jsonl/projector.py:80-95`:

```python
def _delta_key(stamped: StampedEvent) -> _DeltaKey | None:
    event = stamped.event
    if isinstance(event, StepTextDelta):
        return ("StepTextDelta", event.step, event.channel)
    if isinstance(event, ReasoningDelta):
        return ("ReasoningDelta", event.step)
    if isinstance(event, SandboxOutputDelta):
        return ("SandboxOutputDelta", event.invocation_id, event.stream)
    if isinstance(event, ToolCallStreaming):
        return ("ToolCallStreaming", event.tool_call_id)  # ← 新增一行
    return None
```

### 二、`_coalesce_deltas` 适配 ToolCallStreaming

合并语义:同 `tool_call_id` 合并为 1 条,`arguments_preview` 取最后一条(payload 是 best-effort 最新值,不是字符流拼接),`seq` 取首条 seq。

### 三、executor 改 emit `arguments_delta`(根因修复)

`lca/cognition/brain/llm_turn/executor.py:106-122` 把累积式 `arguments_preview` 改为真实增量:

```python
record(
    ToolCallStreaming(
        tool_name=str(frame["tool_name"]),
        tool_call_id=str(frame["tool_call_id"]),
        arguments_delta=slot.get("raw_delta", ""),  # 最近 ~160 字符新增
        # arguments_preview 仅在完整可 parse 时存在,避免整段冗余
        arguments_preview=dict(partial) if partial and len(partial) > 0 else {},
    )
)
```

`lca/contracts/models/core/llm.py:65` 已定义 `arguments_delta: str = ""` 字段,直接复用。

### 四、LobeHub `merged` 改为 delta 追加(根因修复)

`lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts:108-110`:

```typescript
const merged = rawArgs && typeof rawArgs === 'object'
  ? {
      ...baseState,
      ...(rawArgs as Record<string, unknown>),
      // 关键:code 字段单独走 delta 追加,不 spread 累积
      code: rawArgs.code_delta ?? baseState.code ?? '',
    }
  : baseState;
```

### 五、`fact_stream._render_tool_streaming` 默认折叠 narrative

`lca/infrastructure/observability/journal/stream/fact_stream.py:473-481` 加 `show_streaming=False` 默认值,narrative 不再显示3800 行 tool.streaming(用户可选展开)。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| ADR-0063 §I6 兑现 | 不新增事件类型;不污染 envelope | 无 |
| journal 体量 | 31 MB → ~100 KB(3800 条 → ~100 条合并后) | 无 |
| LobeHub 折叠面板 | 整段 Python 消失(delta 追加而非累积) | 一处 lcaJournal.ts 改动 |
| UI 工具标题 | 提前出现(`ToolStarted.arguments.description` 已含) | 无 |
| narrative | 默认折叠 tool.streaming,不再被淹没 | 用户可控开关 |
| **新增代码量** | **~20 行** | — |
| **新增文件** | **0** | — |
| **新增 Protocol** | **0** | — |
| **新增 SSE 通道** | **0** | — |
| **新增 LobeHub 文件** | **0** | — |

## 替代方案(已否决)

| 方案 | 否决理由 |
|---|---|
| 新建 ProgressStream Protocol | EventDurability.best_effort 已表达语义,重复 seam |
| `stamped_to_record` 加 `channel` 字段 | 污染 envelope,违反 §I6 |
| SSE 双通道 + LobeHub 双 consumer | 现有 LiveTail + 单一 driver 已足够 |
| journal projector 按 tool_call_id 合并 + 同时改 payload 为 delta(采纳) | 这是本 ADR 的方案 |

## 验证约束(机械可执行)

```bash
# 1. journal 不再含 ToolCallStreaming 累积全文(仅含合并后条目)
uv run pytest tests/infrastructure/observability/journal/jsonl/test_projector_tool_call_stream.py -v

# 2. _delta_key 含 ToolCallStreaming 合并
uv run pytest tests/infrastructure/observability/journal/jsonl/test_delta_key.py -v

# 3. arguments_delta 字段是真实增量(非累积全文)
uv run pytest tests/cognition/brain/llm_turn/test_executor_arguments_delta.py -v

# 4. journal 体量降级(集成测试)
uv run pytest tests/integration/test_journal_size_no_streaming.py -v

# 5. LobeHub delta 合并
cd lobehub-ui && bun test src/store/chat/agents/transports/lcaJournal.argumentsDelta.test.ts

# 6. narrative 默认折叠 tool.streaming
uv run pytest tests/infrastructure/observability/journal/stream/test_narrative_fold_streaming.py -v
```

## 修改清单

| 修改位置 | 修改内容 |
|---|---|
| `lca/infrastructure/observability/journal/jsonl/projector.py:80-95` | `_delta_key` 加 `("ToolCallStreaming", tool_call_id)` 合并键 |
| `lca/infrastructure/observability/journal/jsonl/projector.py:106-124` | `_coalesce_deltas` 适配 ToolCallStreaming(`arguments_preview` 取最后一段) |
| `lca/cognition/brain/llm_turn/executor.py:106-122` | emit `arguments_delta` 而非 `arguments_preview` 累积 |
| `lca/infrastructure/observability/journal/stream/fact_stream.py:473-481` | `_render_tool_streaming` 加 `show_streaming` 默认 False |
| `lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts:108-110` | `merged` 改为 delta 追加 |

## 新增清单

无新增。

## 落地顺序

2 个 commit:

1. commit 1:`_delta_key` + `_coalesce_deltas` 适配 ToolCallStreaming;`executor.py` emit `arguments_delta`。
2. commit 2:LobeHub `merged` 改 delta 追加;narrative `show_streaming` 默认 False。

每步跑 `tests/infrastructure/observability/journal/jsonl/test_projector_tool_call_stream.py tests/cognition/brain/llm_turn/test_executor_arguments_delta.py`。

## 风险

- **风险 1**:`arguments_preview` 合并后"取最后一段"语义,若最后一次 chunk 的 preview 不完整,UI 仍可能看到不完整代码。**缓解**:测试覆盖 incomplete preview 路径;LobeHub `merged` 仅在 last_invoke 时拉取完整 `ToolStarted.arguments`,而非合并 preview。
- **风险 2**:narrative `show_streaming=False` 默认隐藏,用户调试时需显式 `--show-streaming`。**缓解**:`lca-ops logs --show-streaming` 命令加开关。