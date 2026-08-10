# AskUserQuestion — Human-in-the-Loop Structured Question Design

**Date:** 2026-08-11
**Status:** Approved
**Approach:** B — Tool + Pause/Resume

## Problem

LobeHub 前端已有完整的 AskUserQuestion 选择卡片 UI（`shared-tool-ui` 包），但 LCA 后端缺少触发和闭环能力。需要实现从 LLM 决策提问 → 前端渲染选项 → 用户回答 → agent 继续执行的完整闭环。

## Architecture Overview

```
LLM → tool_call: ask_user_question({questions: [...]})
  ↓
L1 Body → SafeExecutor → tool.execute()
  ↓
ApprovalPendingError(metadata={user_question: {...}})
  ↓
L2 _loop() → catch → checkpoint → INPUT_REQUIRED → return
  ↓
Gateway execute_run() → detect INPUT_REQUIRED
  → session.status = WAITING_INPUT
  → emit tool_started (wire: lobe-user-interaction____askUserQuestion)
  → emit ask_user event (lca.events extension)
  → emit finish chunk (SSE 正常结束)
  ↓
LobeHub 前端 → 解析 tool message → 检测 intervention
  → 渲染 AskUserQuestionView
  ↓
用户选择 → POST /runs/{run_id}/answer { answer }
  → 返回 SSE 流
  ↓
Gateway resume_run()
  → runnable.resume(snapshot, input=answer)
  → L2 resume() → 构造 Observation → 注入 history
  → LLM 看到答案 → 继续推理 → SSE 继续
```

## Layer-by-Layer Design

### 1. Contracts — 数据模型

**RunStatus 扩展** (`gateway/run_registry.py`):

```python
class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"  # NEW
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
```

`to_lobehub_session_status()` 映射 `WAITING_INPUT → "waiting_input"`（LobeHub 已有此状态）。

**常量** (`lca/contracts/models/core/result.py`):

```python
USER_QUESTION_METADATA_KEY = "user_question"
```

`ApprovalPendingError` 已有 `metadata: dict` 字段，直接复用。

### 2. L0 — AskUserQuestionTool

**文件:** `lca/layer0_infra/tools/ask_user_question.py`

```python
class AskUserQuestionTool:
    name = "ask_user_question"
    description = "Ask the user a structured question with selectable options. "
                    "Use when you need the user to make a choice or provide input."
    is_idempotent = False
    default_timeout_s = 300  # 5 min — user may take time

    parameters = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "1-4 questions to ask the user",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "The question text"},
                        "header": {"type": "string", "description": "Short category label"},
                        "options": {
                            "type": "array",
                            "description": "2-4 selectable options",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"}
                                },
                                "required": ["label"]
                            },
                            "minItems": 2, "maxItems": 4
                        },
                        "multiSelect": {"type": "boolean"}
                    },
                    "required": ["question", "options"]
                },
                "minItems": 1, "maxItems": 4
            }
        },
        "required": ["questions"]
    }

    async def execute(self, args: dict) -> Observation:
        raise ApprovalPendingError(
            reason="Awaiting user answer to structured question",
            metadata={USER_QUESTION_METADATA_KEY: args["questions"]},
        )
```

**注册:** 加入 `build_default_tools()` in `lca/layer0_infra/tools/default_set.py`。

### 3. L2 — Resume 路径补全

**已有:**
- `_loop()` 捕获 `ApprovalPendingError` → checkpoint → `INPUT_REQUIRED` → return
- `CognitiveRuntime.resume(snapshot, input)` → 恢复 state → `working_memory["resume_input"] = input`

**需补充:** resume 恢复后，把 `resume_input` 转化为 tool observation 注入 history。

**关键上下文:** `ApprovalPendingError` 在 `SafeExecutor.execute()` 内部抛出时，`ToolStarted` journal 事件已发射，但 `ToolInvoked` 未发射。history 最后一轮的 `Turn` 存在但 `observation` 为 `None`。resume 时需要填充这个空位，让 LLM 在下一轮 prompt 中看到工具结果。

在 `CognitiveRuntime.resume()` 中：

```python
# runtime_loop.py — resume() 方法
async def resume(self, snapshot, input=None, max_steps=DEFAULT_MAX_STEPS):
    state = await self.state_store.load(snapshot.state_ref)
    state.status = TaskStatus.WORKING
    if input is not None:
        # 找到 observation 为空的最后一轮（即被暂停的 tool call）
        for turn in reversed(state.history):
            if turn.observation is None:
                observation = Observation(payload=input, success=True)
                turn.observation = observation
                await self.memory.update(state, observation)
                break
        else:
            # 兜底：没有空 observation 的 turn，放入 working memory
            state.working_memory["resume_input"] = input
    return await self._loop(state, max_steps)
```

### 4. Gateway — execute_run() 暂停检测

**文件:** `gateway/run_executor.py`

```python
async def execute_run(session: RunSession, ...) -> None:
    ...
    result = await runnable.run(question)

    if result.state.status == TaskStatus.INPUT_REQUIRED:
        session.status = RunStatus.WAITING_INPUT
        questions = extract_questions_from_result(result)
        tool_call_id = extract_tool_call_id(result)

        # 发射 tool_started + ask_user 事件
        emit([
            lca_tool_started_event(
                tool_call_id=tool_call_id,
                wire_name="lobe-user-interaction____askUserQuestion",
                identifier="lobe-user-interaction",
                api_name="askUserQuestion",
                arguments=json.dumps({"questions": questions}),
            ),
            lca_ask_user_event(
                tool_call_id=tool_call_id,
                questions=questions,
            ),
        ])
        # 发射 finish chunk 让 SSE 正常结束
        emit_finish("stop")
        # 不关闭 hub — 保持 session 存活等待 resume
        session.snapshot = result.state  # 保存 checkpoint
        return

    # 正常完成路径（不变）
    ...
```

### 5. Gateway — SSE 扩展事件

**文件:** `gateway/lobehub_bridge/lca_sse_extension.py`

```python
def lca_ask_user_event(
    *, tool_call_id: str, questions: list[dict]
) -> dict[str, Any]:
    return {
        "type": "ask_user",
        "tool_call_id": tool_call_id,
        "questions": questions,
        "closed_loop": LCA_CLOSED_LOOP_MARKER,
    }
```

### 6. Gateway — Resume 端点

**文件:** `gateway/app.py`

```python
POST /runs/{run_id}/answer
Body: {
    "answer": "blue"                          # 单选：直接文本
    # 或
    "answers": {"Which color?": "blue"}       # 多选/多题：结构化 JSON
}
Response: SSE stream (StreamingResponse)
```

Gateway 将 answer 统一序列化为字符串传给 `resume(input=...)`：
- 单选：`answer` 字段直接使用
- 多题：`answers` JSON dump 为字符串

LLM 在下一轮 prompt 的 tool result 中看到答案文本，自然理解用户选择。

处理逻辑:

```python
async def answer_run(request: Request) -> StreamingResponse:
    run_id = request.path_params["run_id"]
    body = await request.json()
    answer = body["answer"]

    session = registry.get(run_id)
    if not session or session.status != RunStatus.WAITING_INPUT:
        return JSONResponse({"error": "not waiting"}, status_code=409)

    # 恢复 run，返回 SSE 流
    return StreamingResponse(
        resume_run_sse(session, answer),
        media_type="text/event-stream",
    )

async def resume_run_sse(session: RunSession, answer: str) -> AsyncIterator:
    session.status = RunStatus.RUNNING

    # 创建新的 SSE subscriber
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    session.subscribers.append(queue)

    # 在后台恢复 run
    async def _resume():
        try:
            result = await runnable.resume(session.snapshot, input=answer)
            session.status = RunStatus.COMPLETED
        except Exception as e:
            session.status = RunStatus.FAILED
            session.error = str(e)
        finally:
            emit(None)  # sentinel

    asyncio.create_task(_resume())

    # 流式发射事件
    while True:
        frame = await queue.get()
        if frame is None:
            break
        yield format_sse(frame)
```

### 7. Tool Wire 映射

**文件:** `gateway/lobehub_bridge/tool_wire.py`

```python
_TOOL_REGISTRY["ask_user_question"] = ToolWireSpec(
    lca_name="ask_user_question",
    identifier="lobe-user-interaction",
    api_name="askUserQuestion",
    transform_args=lambda args: args,
    build_state=lambda result: {"askUserAnswers": result},
)
```

### 8. Journal Projector 适配

**文件:** `gateway/journal_openai_projector.py`

**边界划分:**
- **正常路径（run 未暂停）:** projector 从 journal 事件投影 `tool_started`，走已有逻辑
- **暂停路径（ask_user_question 触发 ApprovalPendingError）:** `ToolStarted` journal 事件已发射，projector 正常投影。但 `ToolInvoked` 永远不会来（tool 被暂停）。gateway 在 `execute_run()` 检测到 `INPUT_REQUIRED` 后，直接通过 `emit()` 补射 `ask_user` 事件 + finish chunk，**不经过 projector**

这意味着 projector 不需要改动——它处理 journal→SSE 的实时投影，gateway 的暂停逻辑在 projector 之外补射控制事件。两者职责清晰分离：
- Projector: journal 事件的被动投影（只读）
- Gateway execute_run: run 生命周期管理（主动控制）

## Edge Cases

1. **用户不回答，run 被 cancel:** `cancel_run()` 需要处理 `WAITING_INPUT` 状态 → 直接设 CANCELED，清理 session
2. **重复 answer:** 检查 `session.status == WAITING_INPUT`，非 waiting 状态返回 409
3. **LLM 不调 ask_user_question:** 正常路径，不受影响
4. **resume 后 LLM 再次 ask:** 循环正常工作，每次 ask 都走 pause → resume
5. **SSE 断线重连:** LobeHub 有 SSE reconnect 机制（Last-Event-ID），resume 端点返回新 SSE 流

## Files Changed Summary

| Layer | File | Change |
|-------|------|--------|
| Contracts | `lca/contracts/models/core/result.py` | 新增 `USER_QUESTION_METADATA_KEY` 常量 |
| Gateway | `gateway/run_registry.py` | 新增 `WAITING_INPUT` 状态 + LobeHub 映射 |
| L0 Tool | `lca/layer0_infra/tools/ask_user_question.py` | **新建** — AskUserQuestionTool |
| L0 Tools | `lca/layer0_infra/tools/default_set.py` | 注册新工具 |
| L2 Runtime | `lca/layer2_runtime/runtime_loop.py` | resume() 补全 observation 注入 |
| Gateway | `gateway/run_executor.py` | execute_run() 暂停检测 |
| Gateway | `gateway/lobehub_bridge/lca_sse_extension.py` | 新增 `lca_ask_user_event()` |
| Gateway | `gateway/app.py` | 新增 `POST /runs/{run_id}/answer` 路由 |
| Gateway | `gateway/lobehub_bridge/tool_wire.py` | 新增 ask_user_question 映射 |
| Gateway | `gateway/journal_openai_projector.py` | 适配 ask_user 事件 |
| Tests | `tests/` | 单元测试 + 集成测试 |
