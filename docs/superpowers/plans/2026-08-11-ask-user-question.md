# AskUserQuestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable LLM agents to ask users structured questions with selectable options, with the full pause → UI render → answer → resume闭环.

**Architecture:** `AskUserQuestionTool` raises `ApprovalPendingError` to pause the L2 cognitive loop. Gateway detects `INPUT_REQUIRED`, emits LobeHub-compatible intervention events, and exposes a `POST /runs/{run_id}/answer` endpoint. User answers resume the loop via `CognitiveRuntime.resume()`, injecting the answer as a synthetic Turn so the LLM sees the tool result.

**Tech Stack:** Python 3.12+, asyncio, Starlette (gateway), structlog, pytest

## Global Constraints

- 五层单向依赖：contracts → layer0 → layer1 → layer2 → layer3，layer4 组合根
- `ApprovalPendingError(approval_request: Any)` — 已有签名，不修改
- `Observation(observation_id, success, payload, ...)` — dataclass，`observation_id` 必填
- Tool Protocol: `name`, `description`, `parameters: ClassVar[dict]`, `is_idempotent`, `default_timeout_s`, `async execute(args) -> Observation`
- RunStatus 映射：`WAITING_INPUT → "waiting_input"` (LobeHub 已有此状态)
- 验证命令：`uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest`

---

### Task 1: AskUserQuestionTool + 常量

**Files:**
- Create: `lca/layer0_infra/tools/ask_user_question.py`
- Modify: `lca/layer0_infra/tools/default_set.py`
- Test: `tests/tools/test_ask_user_question.py`

**Interfaces:**
- Consumes: `Tool` Protocol from `lca.contracts.protocols`, `Observation` from `lca.contracts.models.core.decision`, `ApprovalPendingError` from `lca.contracts.models.core.result`
- Produces: `AskUserQuestionTool` class registered in `build_default_tools()`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_ask_user_question.py
"""Tests for AskUserQuestionTool."""

import pytest

from lca.contracts.models.core.result import ApprovalPendingError
from lca.layer0_infra.tools.ask_user_question import AskUserQuestionTool


@pytest.fixture
def tool() -> AskUserQuestionTool:
    return AskUserQuestionTool()


class TestAskUserQuestionTool:
    def test_metadata(self, tool: AskUserQuestionTool) -> None:
        assert tool.name == "ask_user_question"
        assert tool.is_idempotent is False
        assert "questions" in tool.parameters["properties"]

    async def test_execute_raises_approval_pending(self, tool: AskUserQuestionTool) -> None:
        args = {
            "questions": [
                {
                    "question": "Which color?",
                    "header": "Preference",
                    "options": [
                        {"label": "Blue", "description": "Cool tone"},
                        {"label": "Red", "description": "Warm tone"},
                    ],
                }
            ]
        }
        with pytest.raises(ApprovalPendingError) as exc_info:
            await tool.execute(args)
        assert exc_info.value.approval_request == args["questions"]

    def test_validate_rejects_empty_questions(self, tool: AskUserQuestionTool) -> None:
        result = tool.validate({"questions": []})
        assert result is not None  # error string

    def test_validate_accepts_valid_args(self, tool: AskUserQuestionTool) -> None:
        result = tool.validate(
            {
                "questions": [
                    {
                        "question": "Pick one",
                        "options": [{"label": "A"}, {"label": "B"}],
                    }
                ]
            }
        )
        assert result is None

    def test_registered_in_default_tools(self) -> None:
        from lca.layer0_infra.tools.default_set import build_default_tools

        names = [t.name for t in build_default_tools()]
        assert "ask_user_question" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_ask_user_question.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lca.layer0_infra.tools.ask_user_question'`

- [ ] **Step 3: Implement AskUserQuestionTool**

```python
# lca/layer0_infra/tools/ask_user_question.py
"""Structured question tool — pauses the loop for human input."""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.result import ApprovalPendingError
from lca.contracts.protocols import Tool


class AskUserQuestionTool(Tool):
    """Ask the user a structured question with selectable options.

    Raises ``ApprovalPendingError`` to pause the cognitive loop.
    The user's answer is injected as a synthetic Turn on resume.
    """

    name = "ask_user_question"
    description = (
        "Ask the user a structured question with 2-4 selectable options per question. "
        "Use when you need the user to make a choice, clarify a preference, "
        "or provide input before continuing."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "1-4 questions to ask the user",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The question text",
                        },
                        "header": {
                            "type": "string",
                            "description": "Short category label shown as a chip",
                        },
                        "options": {
                            "type": "array",
                            "description": "2-4 selectable options",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {
                                        "type": "string",
                                        "description": "Supporting text for the option",
                                    },
                                },
                                "required": ["label"],
                            },
                            "minItems": 2,
                            "maxItems": 4,
                        },
                        "multiSelect": {
                            "type": "boolean",
                            "description": "Allow selecting multiple options",
                        },
                    },
                    "required": ["question", "options"],
                },
                "minItems": 1,
                "maxItems": 4,
            }
        },
        "required": ["questions"],
    }
    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def validate(self, args: dict[str, Any]) -> str | None:
        questions = args.get("questions")
        if not questions or not isinstance(questions, list):
            return "questions must be a non-empty array"
        for i, q in enumerate(questions):
            if not isinstance(q, dict) or not q.get("question"):
                return f"questions[{i}].question is required"
            opts = q.get("options", [])
            if len(opts) < 2:
                return f"questions[{i}].options must have at least 2 items"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        raise ApprovalPendingError(args["questions"])
```

- [ ] **Step 4: Register in build_default_tools()**

In `lca/layer0_infra/tools/default_set.py`, add import and insert into both branches:

```python
from lca.layer0_infra.tools.ask_user_question import AskUserQuestionTool
```

Add `AskUserQuestionTool()` to the returned list in both sandbox and no-sandbox branches (after `search_tools`).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/tools/test_ask_user_question.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add lca/layer0_infra/tools/ask_user_question.py lca/layer0_infra/tools/default_set.py tests/tools/test_ask_user_question.py
git commit -m "feat(tool): add AskUserQuestionTool — raises ApprovalPendingError for HIL"
```

---

### Task 2: RunStatus.WAITING_INPUT + LobeHub 映射

**Files:**
- Modify: `gateway/run_registry.py:47-65`
- Test: `tests/gateway/test_run_registry_waiting_input.py`

**Interfaces:**
- Consumes: `RunStatus` enum
- Produces: `RunStatus.WAITING_INPUT` with `to_lobehub_session_status() → "waiting_input"`

- [ ] **Step 1: Write the failing test**

```python
# tests/gateway/test_run_registry_waiting_input.py
from gateway.run_registry import RunStatus


def test_waiting_input_status_exists() -> None:
    assert RunStatus.WAITING_INPUT.value == "waiting_input"


def test_waiting_input_lobehub_mapping() -> None:
    assert RunStatus.WAITING_INPUT.to_lobehub_session_status() == "waiting_input"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/gateway/test_run_registry_waiting_input.py -v`
Expected: FAIL — `AttributeError: WAITING_INPUT`

- [ ] **Step 3: Implement**

In `gateway/run_registry.py`:

Add `WAITING_INPUT = "waiting_input"` to `RunStatus` enum.

Add to `_LOBEHUB_STATUS_MAP`:
```python
RunStatus.WAITING_INPUT: "waiting_input",
```

Update docstring on `to_lobehub_session_status()` to remove the claim that `waiting_input` never appears.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/gateway/test_run_registry_waiting_input.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/run_registry.py tests/gateway/test_run_registry_waiting_input.py
git commit -m "feat(gateway): add WAITING_INPUT RunStatus with LobeHub mapping"
```

---

### Task 3: L2 Resume — 注入 Synthetic Turn

**Files:**
- Modify: `lca/layer2_runtime/runtime_loop.py:93-101` (resume method)
- Test: `tests/runtime/test_resume_injects_turn.py`

**Interfaces:**
- Consumes: `StateSnapshot`, `AgentState`, `Turn`, `Decision`, `Observation`, `ActionType.USE_TOOL`, `ToolCall`
- Produces: Modified `resume()` that injects a synthetic Turn with the user's answer into history before entering `_loop()`

- [ ] **Step 1: Write the failing test**

```python
# tests/runtime/test_resume_injects_turn.py
"""Resume injects a synthetic Turn so the LLM sees the user's answer."""

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import ApprovalPendingError, Result
from lca.contracts.models.core.state import AgentState


async def test_resume_injects_synthetic_turn(runtime, state_store):
    """After resume(input=...), history has a Turn with the user's answer."""
    # Setup: create a state with one history turn (the tool call that paused)
    state = AgentState(trace_id="test-trace", task="test task")
    state.step = 1

    # Simulate the tool call that triggered ApprovalPendingError
    decision = Decision(
        action_type=ActionType.USE_TOOL,
        thought="Asking user",
        tool_calls=[
            ToolCall(call_id="tc1", tool_name="ask_user_question", arguments={"questions": []})
        ],
    )
    # Note: observation is None because ApprovalPendingError prevented Turn creation
    # But the checkpoint saves state BEFORE the Turn is appended.
    # So on resume, history is empty of this turn.

    ref = await state_store.save(state)
    from lca.contracts.models.core.state import StateSnapshot

    snapshot = StateSnapshot(state_ref=ref, step=state.step, trace_id=state.trace_id)

    # Resume with user's answer
    result = await runtime.resume(snapshot, input="Blue")

    # The injected turn should be in history
    assert len(result.history) >= 1
    last_turn = result.history[-1]
    assert last_turn.decision.action_type == ActionType.USE_TOOL
    assert last_turn.decision.tool_calls[0].tool_name == "ask_user_question"
    assert last_turn.observation is not None
    assert last_turn.observation.success is True
    assert "Blue" in str(last_turn.observation.payload)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/runtime/test_resume_injects_turn.py -v`
Expected: FAIL — history doesn't have the synthetic turn

- [ ] **Step 3: Implement resume() modification**

In `lca/layer2_runtime/runtime_loop.py`, modify the `resume()` method:

```python
async def resume(
    self,
    snapshot: StateSnapshot,
    input: object | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> Result:
    state = await self.state_store.load(snapshot.state_ref)
    state.status = TaskStatus.WORKING
    if input is not None:
        self._inject_user_answer(state, input)
    return await self._loop(state, max_steps)


@staticmethod
def _inject_user_answer(state: AgentState, answer: object) -> None:
    """Inject a synthetic Turn so the LLM sees the user's answer as a tool result."""
    from lca.contracts.atoms.enums import ActionType
    from lca.contracts.atoms.ids import new_id
    from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn

    answer_text = str(answer) if not isinstance(answer, str) else answer
    decision = Decision(
        action_type=ActionType.USE_TOOL,
        thought="User answered the structured question",
        tool_calls=[
            ToolCall(
                call_id=new_id("tc"),
                tool_name="ask_user_question",
                arguments={},
            )
        ],
    )
    observation = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=f"User answered: {answer_text}",
    )
    state.history.append(Turn(decision=decision, observation=observation, reflection=None))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/runtime/test_resume_injects_turn.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest -x -q`
Expected: ALL PASS (existing resume tests still work)

- [ ] **Step 6: Commit**

```bash
git add lca/layer2_runtime/runtime_loop.py tests/runtime/test_resume_injects_turn.py
git commit -m "feat(runtime): resume() injects synthetic Turn with user answer"
```

---

### Task 4: Gateway — execute_run() 暂停检测 + SSE 事件

**Files:**
- Modify: `gateway/run_executor.py` (execute_run function)
- Modify: `gateway/lobehub_bridge/lca_sse_extension.py` (new event type)
- Test: `tests/gateway/test_execute_run_waiting_input.py`

**Interfaces:**
- Consumes: `RunStatus.WAITING_INPUT`, `TaskStatus.INPUT_REQUIRED`, `Result`, `RunSession`
- Produces: `execute_run()` detects `INPUT_REQUIRED` and sets `WAITING_INPUT` instead of `COMPLETED`; `lca_ask_user_event()` function

- [ ] **Step 1: Write the failing test**

```python
# tests/gateway/test_execute_run_waiting_input.py
"""execute_run detects INPUT_REQUIRED and sets WAITING_INPUT."""

from gateway.lobehub_bridge.lca_sse_extension import lca_ask_user_event


def test_lca_ask_user_event_shape() -> None:
    event = lca_ask_user_event(
        tool_call_id="tc_123",
        questions=[{"question": "Color?", "options": [{"label": "Blue"}]}],
    )
    assert event["type"] == "ask_user"
    assert event["tool_call_id"] == "tc_123"
    assert event["closed_loop"] is True
    assert len(event["questions"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/gateway/test_execute_run_waiting_input.py -v`
Expected: FAIL — `ImportError: cannot import name 'lca_ask_user_event'`

- [ ] **Step 3: Add lca_ask_user_event to SSE extension**

In `gateway/lobehub_bridge/lca_sse_extension.py`:

```python
def lca_ask_user_event(*, tool_call_id: str, questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Signal a structured user question (HIL pause)."""
    return {
        "type": "ask_user",
        "tool_call_id": tool_call_id,
        "questions": questions,
        "closed_loop": LCA_CLOSED_LOOP_MARKER,
    }
```

Also add `"ask_user"` to the `LcaToolEventType` Literal if needed (or create a new type alias).

- [ ] **Step 4: Modify execute_run() to detect INPUT_REQUIRED**

In `gateway/run_executor.py`, after `runnable.run()` returns, before the final status assignment:

```python
# After: await runnable.run(question) or await runnable.run(question, run_ctx)
# Capture the result:
result = None
if isinstance(runnable, Agent):
    result = await runnable.run(question, run_ctx)
else:
    result = await runnable.run(question)

# Check for HIL pause
if result and result.status == TaskStatus.INPUT_REQUIRED:
    session.status = RunStatus.WAITING_INPUT
    session.snapshot = result.state_snapshot  # Save for resume
    # Emit ask_user event via session hub
    questions = _extract_questions_from_result(result)
    frame = _build_ask_user_frame(session, questions)
    session.emit(frame)
    # Don't close hub — keep session alive for resume
    return
```

Add helper functions:

```python
def _extract_questions_from_result(result: Result) -> list[dict]:
    """Extract question data from ApprovalPendingError metadata."""
    # The ApprovalPendingError stores questions in approval_request
    # which is captured in the Result's error or state
    # For now, extract from state's last checkpoint
    return result.error_data.get("user_question", []) if hasattr(result, "error_data") else []


def _build_ask_user_frame(session: RunSession, questions: list[dict]) -> str:
    """Build SSE frame for ask_user event."""
    import json
    from gateway.lobehub_bridge.lca_sse_extension import lca_ask_user_event

    event = lca_ask_user_event(tool_call_id=f"ask_{session.run_id}", questions=questions)
    body = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
    body_with_ext = merge_lca_extension(body, [event])
    return f"data: {json.dumps(body_with_ext)}\n\n"
```

**关键:** `ApprovalPendingError.approval_request` 携带 questions 数据，但 `_loop()` 当前捕获后丢弃。需修改 `_loop()` 的 except 子句，将 `approval_request` 存入 `state.working_memory`，这样 gateway 可从 `Result` 的 state 中提取：

```python
# runtime_loop.py — _loop() 的 except 子句（Task 3 一并修改）
except ApprovalPendingError as e:
    state.working_memory["_pending_approval"] = e.approval_request
    await self._checkpoint(state, reason=SnapshotReason.PRE_APPROVAL)
    state.status = TaskStatus.INPUT_REQUIRED
    await self.hooks.trigger("on_pause", state)
    return Result.from_state(state)
```

Gateway 提取 questions：
```python
def _extract_questions(session: RunSession) -> list[dict]:
    """从 session 的 state 提取 pending approval 数据。"""
    # session 保存了 Result，Result 包含 state_ref
    # 从 working_memory["_pending_approval"] 读取
    ...
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/gateway/test_execute_run_waiting_input.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add gateway/run_executor.py gateway/lobehub_bridge/lca_sse_extension.py tests/gateway/test_execute_run_waiting_input.py
git commit -m "feat(gateway): execute_run detects INPUT_REQUIRED, emits ask_user SSE event"
```

---

### Task 5: Gateway — POST /runs/{run_id}/answer 端点

**Files:**
- Modify: `gateway/app.py` (new route)
- Modify: `gateway/run_executor.py` (new `resume_run()` function)
- Test: `tests/gateway/test_answer_endpoint.py`

**Interfaces:**
- Consumes: `RunRegistry`, `RunSession`, `RunStatus.WAITING_INPUT`, `build_solo_agent()`, `build_runnable_team()`, `Agent.resume()`
- Produces: `POST /runs/{run_id}/answer` endpoint that resumes a paused run and returns SSE stream

- [ ] **Step 1: Write the failing test**

```python
# tests/gateway/test_answer_endpoint.py
"""POST /runs/{run_id}/answer resumes a paused run."""

import pytest
from starlette.testclient import TestClient


def test_answer_endpoint_rejects_non_waiting_run(app, registry):
    """Answering a non-waiting run returns 409."""
    # Create a completed run
    session = create_test_session(registry, status=RunStatus.COMPLETED)
    client = TestClient(app)
    resp = client.post(
        f"/runs/{session.run_id}/answer",
        json={"answer": "Blue"},
    )
    assert resp.status_code == 409


def test_answer_endpoint_rejects_unknown_run(app):
    client = TestClient(app)
    resp = client.post("/runs/nonexistent/answer", json={"answer": "Blue"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/gateway/test_answer_endpoint.py -v`
Expected: FAIL — route doesn't exist

- [ ] **Step 3: Implement resume_run() in run_executor.py**

```python
async def resume_run(
    registry: RunRegistry,
    *,
    run_id: str,
    answer: str,
) -> None:
    """Resume a paused run with the user's answer."""
    session = registry.get(run_id)
    if session is None or session.status != RunStatus.WAITING_INPUT:
        return
    session.status = RunStatus.RUNNING

    with (
        run_id_scope(session.run_id),
        run_workspace_scope(session.run_id),
    ):
        llm = get_llm_resolver().resolve(mode=session.mode)
        # Rebuild the runnable (same config as original)
        if session.mode == SOLO_MODE_KEY:
            runnable = build_solo_agent(llm, observability=session.hub)
        else:
            runnable = await build_runnable_team(
                session.question,
                llm,
                observability=session.hub,
                trace_id=session.trace_id,
                run_id=session.run_id,
            )

        if isinstance(runnable, Agent):
            result = await runnable.resume(session.snapshot, input=answer)
        else:
            # Team doesn't have resume yet — use the lead agent
            # For now, only solo mode supports resume
            result = await runnable.resume(session.snapshot, input=answer)

    session.status = RunStatus.CANCELED if session.cancel_requested else RunStatus.COMPLETED
```

- [ ] **Step 4: Add route to app.py**

```python
# gateway/app.py
from gateway.run_executor import resume_run

async def answer_run(request: Request) -> Response:
    """POST /runs/{run_id}/answer — resume a paused run with user's answer."""
    run_id = request.path_params["run_id"]
    body = await request.json()

    session = registry.get(run_id)
    if session is None:
        return JSONResponse({"error": "run not found"}, status_code=404)
    if session.status != RunStatus.WAITING_INPUT:
        return JSONResponse(
            {"error": f"run is {session.status.value}, not waiting_input"},
            status_code=409,
        )

    # Extract answer
    answer = body.get("answer") or ""
    if "answers" in body:
        import json
        answer = json.dumps(body["answers"])

    # Resume and stream
    async def _stream():
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=256)

        def _emit(frame: str | None) -> None:
            # Non-blocking put; drop if full
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(frame)

        session.subscribers.append(_emit)

        # Start resume in background
        task = asyncio.create_task(
            resume_run(registry, run_id=run_id, answer=answer)
        )

        try:
            while True:
                frame = await queue.get()
                if frame is None:
                    break
                yield frame
        finally:
            session.subscribers.remove(_emit)
            await task

    return StreamingResponse(_stream(), media_type="text/event-stream")

# Add route
routes = [
    ...
    Route("/runs/{run_id}/answer", answer_run, methods=["POST"]),
]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/gateway/test_answer_endpoint.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add gateway/app.py gateway/run_executor.py tests/gateway/test_answer_endpoint.py
git commit -m "feat(gateway): add POST /runs/{run_id}/answer endpoint for HIL resume"
```

---

### Task 6: Tool Wire 映射

**Files:**
- Modify: `gateway/lobehub_bridge/tool_wire.py`
- Test: `tests/gateway/test_tool_wire_ask_user.py`

**Interfaces:**
- Consumes: `ToolWireSpec`, `_TOOL_REGISTRY`
- Produces: `ask_user_question` → `lobe-user-interaction____askUserQuestion` mapping

- [ ] **Step 1: Write the failing test**

```python
# tests/gateway/test_tool_wire_ask_user.py
from gateway.lobehub_bridge.tool_wire import resolve_tool_wire


def test_ask_user_question_wire_mapping() -> None:
    spec = resolve_tool_wire("ask_user_question", '{"questions": []}')
    assert spec is not None
    assert spec.identifier == "lobe-user-interaction"
    assert spec.api_name == "askUserQuestion"
    assert spec.wire_name == "lobe-user-interaction____askUserQuestion"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/gateway/test_tool_wire_ask_user.py -v`
Expected: FAIL — returns None

- [ ] **Step 3: Add mapping**

In `gateway/lobehub_bridge/tool_wire.py`, add to `_TOOL_REGISTRY`:

```python
"ask_user_question": ToolWireSpec(
    lca_name="ask_user_question",
    identifier="lobe-user-interaction",
    api_name="askUserQuestion",
    transform_args=lambda args: args,
    build_state=lambda result: {"askUserAnswers": result},
),
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/gateway/test_tool_wire_ask_user.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/lobehub_bridge/tool_wire.py tests/gateway/test_tool_wire_ask_user.py
git commit -m "feat(gateway): add ask_user_question tool wire mapping for LobeHub intervention"
```

---

### Task 7: 全量验证 + 集成测试

**Files:**
- Test: `tests/integration/test_ask_user_question_e2e.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_ask_user_question_e2e.py
"""End-to-end: tool raises ApprovalPendingError → resume with answer."""

import pytest

from lca.contracts.models.core.result import ApprovalPendingError
from lca.layer0_infra.tools.ask_user_question import AskUserQuestionTool


async def test_tool_raises_and_resume_injects_answer(solo_agent_with_tools, mock_llm):
    """Full cycle: LLM calls ask_user_question → pause → resume → LLM sees answer."""
    agent = solo_agent_with_tools(tools=[AskUserQuestionTool()])

    # Scripted LLM: first call asks user, second call responds with answer
    mock_llm.script(
        # Turn 1: LLM calls ask_user_question
        tool_calls=[
            {
                "name": "ask_user_question",
                "arguments": {
                    "questions": [
                        {
                            "question": "Color?",
                            "options": [{"label": "Blue"}, {"label": "Red"}],
                        }
                    ]
                },
            }
        ],
        # Turn 2: LLM sees the answer and responds
        content="You chose Blue!",
    )

    # First run — should pause
    result1 = await agent.run("What color do I prefer?")
    assert result1.status == "input-required"

    # Resume with answer
    result2 = await agent.resume(result1.state_snapshot, input="Blue")
    assert result2.status == "completed"
    assert "Blue" in result2.output
```

- [ ] **Step 2: Run full verification**

```bash
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
```

- [ ] **Step 3: Fix any issues and commit**

```bash
git add -A
git commit -m "test: add e2e integration test for ask_user_question HIL cycle"
```
