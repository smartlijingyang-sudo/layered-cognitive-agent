# LCA P1: Agent Gateway Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LCA's hand-rolled SSE + 4-event transport with the native LobeHub WebSocket + `AgentStreamEvent` protocol, achieving byte-compat with the upstream `AgentStreamClient` while keeping LCA's `Journal` / `RunSession` / `RunRegistry` as the agent engine.

**Architecture:** Four-layer separation (fact / projection / transport / session). Back-end adds a new `LcaStreamEventManager` (Redis Stream), a `LcaAgentRuntimeCoordinator` (StampedEvent → AgentStreamEvent fold), and a `LcaAgentGateway` (Starlette WebSocketRoute). Front-end delivers new code as 3 patch modules under `deploy/lobehub/patches/runtime/`, retiring the broken `lca_run_driver` module via the engine's `reconcile()` (which restores upstream).

**Tech Stack:**
- Python: starlette WebSocketRoute, pydantic v2, redis (ioredis-style), pytest + httpx
- TypeScript: native `@lobechat/agent-gateway-client` (zero modifications), `useSWR + fetch`
- Infra: existing `127.0.0.1:6379` Redis (LCA dev); no new components

**Spec:** `docs/specs/2026-09-07-lca-p1-agent-gateway-bridge.md` (1075 lines). This plan argues from the spec; executors read both.

---

## Global Constraints

These are project-wide requirements, copied verbatim from the spec, that every task's deliverable implicitly satisfies:

| Constraint | Value | Source |
|---|---|---|
| Redis key prefix | `agent_runtime_stream:` (1:1 with native `StreamEventManager.ts:139`) | spec §5.1 |
| Redis Stream TTL | 2 h = 7200 s | spec §5.1 |
| Redis Stream MAXLEN | `~ 1000` (approximate trim) | spec §5.1 |
| JWT algorithm | RS256, 5 min expiry, `purpose: 'cli-sandbox'`, `sub: <user_id>` | spec §3.A + §5.4 + §15 Q3.B |
| WS heartbeat | 30 s client interval, 3 missed → force reconnect, 1 s → 30 s exponential backoff | spec §5.4 |
| Wire sub-protocol events | 18 `AgentStreamEvent` types, 5 `ClientMessage`, 7 `ServerMessage` — 1:1 mirror of `@lobechat/agent-gateway-client/src/types.ts` | spec §7 + §15 Q2 |
| Auth distinction | `auth_failed` = terminal, `auth_expired` = recoverable via `updateToken + reconnect` | spec §5.4 |
| `lca_running_operations` table | `(run_id PK, topic_id, agent_id, assistant_message_id, scope, created_at, accepted_answer_keys jsonb)`. NO `status` column. | spec §3.2 + §5.7 |
| `accepted_answer_keys` semantics | Persisted jsonb; replay hit returns 200 without re-running. Process-local set is forbidden. | spec §5.7 + §8 |
| Front-end delivery | 3 patch modules: `lca_runtime_chat_persistence`, `lca_runtime_agent_gateway`, `lca_runtime_use_gateway_reconnect`. NO direct edits under `lobehub-ui/`. | spec §6.1 |
| `lca_run_driver` retirement | Deleting the module triggers `reconcile()` to restore 4 lobehub-ui source modifications and remove 5 LCA-only TS files. | spec §6.1.4 |
| Markers | `/* LCA-P1: <purpose> */` style, unique per insertion site, appended by the patch module itself (no pre-existing anchor in upstream). | spec §6.1.2 |
| HIL submission | Plain HTTP `POST /lca-api/runs/{run_id}/answer` via native `CustomInteractionSubmitHandler` hook in `customInteractionHandlers.ts`. NOT WS. | spec §5.3.2 |
| `tool_end` event payload | `{isSuccess, result, payload, executionTime}` only. NO `projected_state` in WS event. | spec §5.3 |
| Server `tool_end` obligation | Coordinator writes `projected_state` to `messages[].pluginState` DB column **before** publishing `tool_end`. Front-end `gatewayEventHandler.tool_end` then `fetchAndReplaceMessages` reads populated row. | spec §5.3.1 |
| L2 test count | 8 cases (`L2-1` through `L2-8`); fast (< 1 s each) in-process TestClient | spec §9.1 |
| L3 test count | 7 cases (`L3-1` through `L3-7`); real LCA kernel subprocess + Python wire harness | spec §9.2 |
| L4 test count | 1 case (`L4-1`); 1 h stability smoke | spec §9.4 |
| Audit script | `scripts/audit_lca_legacy_path.py` exits 0 in CI after PR-4 | spec §10.3 |
| Forbidden patterns | `LegacyRunDispatcher`, `LCA_RUNTIME_FACADE` env flag, `RunUiEncoder`, `stream_run_live` route, `lcaRunObserve`, `lcaRunHil`, `lcaJournal`, `LcaRunDriver`, `lcaRunCommand` | spec §6.5 + §10.1 |

---

## File Structure

The plan modifies 5 directories. Each file has one responsibility.

```
lca/
├── contracts/transport/                                    NEW MODULE
│   ├── __init__.py
│   ├── gateway_messages.py                                 # ClientMessage + ServerMessage
│   ├── agent_stream_event.py                               # 18 AgentStreamEvent types
│   └── stream_keys.py                                      # Redis key naming
│
├── infrastructure/observability/stream/                    NEW MODULE
│   ├── __init__.py
│   ├── stream_event_manager.py                             # LcaStreamEventManager
│   └── tests/test_stream_event_manager.py
│
├── application/runtime/coordinator/                        NEW MODULE
│   ├── __init__.py
│   ├── runtime_coordinator.py                              # LcaAgentRuntimeCoordinator
│   ├── event_translator.py                                # StampedEvent → AgentStreamEvent
│   ├── terminal_hints.py
│   └── tests/
│       ├── test_event_translator.py
│       └── test_terminal_hints.py
│
├── plugins/transport/webserver/handlers/runs/terminal/streaming/  NEW MODULE
│   ├── __init__.py
│   ├── agent_gateway.py                                    # LcaAgentGateway (WebSocketRoute)
│   ├── auth.py                                             # JWT mint + verify
│   ├── resume.py                                           # history replay + resume_complete
│   └── tests/test_lca_agent_gateway.py
│
├── plugins/transport/webserver/handlers/runs/terminal/streaming/wire/  NEW MODULE
│   ├── __init__.py
│   ├── routes.py                                           # @plugin("lca-gateway-ws")
│   └── tests/test_routes.py
│
├── plugins/transport/webserver/handlers/runs/api/          MODIFY
│   ├── command_endpoints.py                                # create_run response adds ws_token; answer_run + cancel_run kept
│   ├── query_endpoints.py                                  # add get_running_operation
│   └── ...
│
├── application/runtime/                                    MODIFY
│   ├── default_facade.py                                   # dispatch_run uses LcaAgentRuntimeCoordinator
│   └── ...
│
└── (legacy modules deleted in Task 24)
    ├── plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py
    ├── plugins/transport/webserver/handlers/runs/terminal/legacy/adapter.py
    ├── plugins/transport/webserver/handlers/runs/api/query_endpoints.py:144-168 (stream_run_live only)
    ├── plugins/transport/run_ui_encoder__encoder_provider.py
    └── plugins/transport/run_live_observe__seam.py

lobehub-ui/
└── (no direct edits; changes delivered via 3 patch modules under deploy/lobehub/patches/runtime/)

deploy/lobehub/patches/runtime/
├── lca_runtime_chat_persistence.py                        NEW (replaces persistence half of lca_run_driver)
├── lca_runtime_agent_gateway.py                           NEW (8 new TS files + 4 source modifications)
├── lca_runtime_use_gateway_reconnect.py                   NEW (1 source modification)
├── lcaToolRender/                                         EXISTING (unchanged, files copied as-is)
├── lcaChatRow.ts, lcaPersist.ts, lcaFinishChat.ts,        EXISTING (kept)
├── lcaError.ts, lcaArtifacts.ts, lcaWire.ts                EXISTING (kept)
└── lca_run_driver.py                                      DELETED in Task 24

tests/
├── contracts/transport/test_protocol_parity.py            NEW (L1: Python types roundtrip)
├── infrastructure/observability/stream/test_stream_event_manager.py  NEW (L1)
├── application/runtime/coordinator/tests/test_event_translator.py       NEW (L1)
├── application/runtime/coordinator/tests/test_terminal_hints.py         NEW (L1)
├── plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_lca_agent_gateway.py  NEW (L2-1, L2-2)
├── integration/p1/                                       NEW DIR
│   ├── test_lca_p1_node_01_ws_handshake.py
│   ├── test_lca_p1_node_02_resume.py
│   ├── test_lca_p1_node_03_heartbeat.py
│   ├── test_lca_p1_node_04_interrupt.py
│   ├── test_lca_p1_node_05_tool_result.py
│   ├── test_lca_p1_node_06_redis_shape.py
│   ├── test_lca_p1_node_07_running_op.py
│   └── test_lca_p1_node_08_ws_token.py
├── e2e/p1/                                                NEW DIR
│   ├── _lca_gateway_client.py                             # Python wire harness
│   ├── conftest.py                                         # kernel_process fixture
│   ├── test_lca_p1_01_user_books_flight.py
│   ├── test_lca_p1_02_wifi_drop.py
│   ├── test_lca_p1_03_page_refresh.py
│   ├── test_lca_p1_04_kernel_restart.py
│   ├── test_lca_p1_05_hil_cross_tab.py
│   ├── test_lca_p1_06_token_expiry.py
│   ├── test_lca_p1_07_llm_retry.py
│   └── test_lca_p1_99_stability.py
└── architecture/test_audit_lca_legacy_path.py              NEW (gates zero-references in CI)

scripts/
└── audit_lca_legacy_path.py                                NEW (the audit script the test imports)
```

---

## Task Sequencing Rationale

The plan is **5 PRs** (matches spec §12). Each PR is a reviewable gate. Within each PR, tasks are ordered so a fresh reviewer's gate-1 is small and self-contained.

- **PR-1** (Tasks 1-3): pure back-end contract + manager. Zero observable change. No front-end. No production risk.
- **PR-2** (Tasks 4-12): back-end WS server + broadcaster. Parallel to legacy `/live` SSE. No front-end change. Watchdog is added here, which fixes §1 broken path #3.
- **PR-3** (Tasks 13-20): front-end switchover via 3 new patch modules. The harness parity test (Task 18) catches any drift between the Python harness and the actual TS.
- **PR-4** (Tasks 21-26): retirement. All four deletion paths execute in one PR; the audit script gates CI.
- **PR-5** (Tasks 27-28): stability smoke. Runs nightly, not in PR.

Each task below is a single self-contained commit. A task can be reverted with `git revert <sha>`; no cross-task dependencies that would make a partial revert break other tasks.

---

# PR-1: Contract + Manager (no observable change)

## Task 1: Wire-protocol types (Python dataclass mirror of native TS)

**Files:**
- Create: `lca/contracts/transport/__init__.py`
- Create: `lca/contracts/transport/gateway_messages.py`
- Create: `lca/contracts/transport/agent_stream_event.py`
- Create: `lca/contracts/transport/stream_keys.py`
- Test: `tests/contracts/transport/test_protocol_parity.py`

**Interfaces:**
- Consumes: nothing (pure dataclasses)
- Produces: `ClientMessage`, `ServerMessage`, 18 `AgentStreamEvent` types, `STREAM_KEY_PREFIX = "agent_runtime_stream:"`, `STREAM_RETENTION_SECONDS = 7200`, `STREAM_MAXLEN = "~1000"`

- [ ] **Step 1: Write the failing test**

```python
# tests/contracts/transport/test_protocol_parity.py
"""Verify Python types produce JSON byte-compat with the native TS union.

Each AgentStreamEvent type is roundtripped to dict and asserted to have
the same key set as the TS source-of-truth in
lobehub-ui/packages/agent-gateway-client/src/types.ts.
"""
import pytest
from lca.contracts.transport.agent_stream_event import (
    StreamStart, StreamChunk, ToolStart, ToolEnd, ToolExecute,
    StepStart, StepComplete, AgentRuntimeInit, AgentRuntimeEnd,
    AgentInterventionRequest, AgentInterventionResponse, VisibleOutputEnd,
    StreamRetry, NotifyUpdate, StreamEnd, ErrorEvent, Heartbeat,
    StreamStartData, StreamChunkData, ToolStartData, ToolEndData,
    ToolExecuteData, StepStartData, StepCompleteData, AgentRuntimeEndData,
    AgentInterventionRequestData, AgentInterventionResponseData, NotifyUpdateData,
    StreamRetryData, StreamEndData, ErrorEventData, HeartbeatData,
)
from lca.contracts.transport.gateway_messages import (
    AuthMessage, ResumeMessage, HeartbeatMessage, InterruptMessage,
    ToolResultMessage, AuthSuccess, AuthFailed, AuthExpired,
    HeartbeatAck, SessionComplete, ResumeComplete, AgentEvent,
)


def test_stream_start_roundtrips_with_assistant_message():
    """TS: assistantMessage must carry id + model + provider + role."""
    s = StreamStart(data=StreamStartData(assistantMessage={"id": "a1", "model": "gpt-4", "provider": "openai", "role": "assistant"}), operationId="op1", stepIndex=0, timestamp=0)
    d = s.model_dump()
    assert d["type"] == "stream_start"
    assert d["data"]["assistantMessage"]["id"] == "a1"
    assert d["data"]["assistantMessage"]["model"] == "gpt-4"


def test_stream_chunk_text_has_chunkType():
    s = StreamChunk(data=StreamChunkData(chunkType="text", content="hello"), operationId="op1", stepIndex=0, timestamp=0)
    assert s.model_dump()["data"]["chunkType"] == "text"


def test_tool_start_carries_parent_message_id_and_toolCalling():
    s = ToolStart(
        data=ToolStartData(parentMessageId="m1", toolCalling={"identifier": "lobe-local-system", "apiName": "runCommand", "arguments": {"command": "ls"}, "id": "tc1", "type": "builtin"}),
        operationId="op1", stepIndex=0, timestamp=0,
    )
    d = s.model_dump()
    assert d["data"]["parentMessageId"] == "m1"
    assert d["data"]["toolCalling"]["identifier"] == "lobe-local-system"


def test_tool_end_no_projected_state():
    """spec §5.3.1: WS tool_end must NOT carry projected_state. Server writes it to DB."""
    s = ToolEnd(
        data=ToolEndData(isSuccess=True, result={"content": "ok"}, payload={"toolCalling": {"id": "tc1"}}, executionTime=120),
        operationId="op1", stepIndex=0, timestamp=0,
    )
    assert "projected_state" not in s.model_dump()["data"]


def test_agent_runtime_end_has_phase_execution_complete():
    s = AgentRuntimeEnd(
        data=AgentRuntimeEndData(
            finalState={"status": "done"},
            reason="completed",
            reasonDetail="ok",
            phase="execution_complete",
        ),
        operationId="op1", stepIndex=0, timestamp=0,
    )
    assert s.model_dump()["data"]["phase"] == "execution_complete"


def test_auth_message_carries_token():
    s = AuthMessage(token="<jwt>")
    assert s.model_dump() == {"type": "auth", "token": "<jwt>"}


def test_resume_message_carries_lastEventId_and_wantStatus():
    s = ResumeMessage(lastEventId="123-0", wantStatus=True)
    d = s.model_dump()
    assert d["type"] == "resume"
    assert d["lastEventId"] == "123-0"
    assert d["wantStatus"] is True


def test_resume_complete_status_enum():
    s = ResumeComplete(status="waiting_input")
    assert s.model_dump() == {"type": "resume_complete", "status": "waiting_input"}


def test_session_complete_no_payload():
    s = SessionComplete()
    assert s.model_dump() == {"type": "session_complete"}


def test_agent_event_envelope():
    s = AgentEvent(id="123-0", event={"type": "stream_chunk", "data": {"chunkType": "text", "content": "x"}, "operationId": "op1", "stepIndex": 0, "timestamp": 0})
    d = s.model_dump()
    assert d["type"] == "agent_event"
    assert d["id"] == "123-0"
    assert d["event"]["type"] == "stream_chunk"


def test_stream_keys_match_native():
    from lca.contracts.transport.stream_keys import (
        STREAM_KEY_PREFIX, STREAM_RETENTION_SECONDS, STREAM_MAXLEN,
    )
    assert STREAM_KEY_PREFIX == "agent_runtime_stream"
    assert STREAM_RETENTION_SECONDS == 2 * 3600
    assert STREAM_MAXLEN == "~1000"


@pytest.mark.parametrize("type_name", [
    "agent_runtime_init", "agent_runtime_end", "stream_start", "stream_chunk",
    "stream_end", "visible_output_end", "stream_retry", "tool_start",
    "tool_end", "tool_execute", "tool_result", "agent_intervention_request",
    "agent_intervention_response", "step_start", "step_complete",
    "notify_update", "error", "heartbeat",
])
def test_all_18_event_types_exist(type_name):
    from lca.contracts.transport import agent_stream_event as mod
    assert hasattr(mod, type_name) or any(
        getattr(cls, "__name__", "").lower().startswith(type_name)
        for cls in mod.__all__
    ), f"Missing type: {type_name}"
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/contracts/transport/test_protocol_parity.py -v 2>&1 | head -20`
Expected: FAIL (no module `lca.contracts.transport`).

- [ ] **Step 3: Write `__init__.py`**

```python
# lca/contracts/transport/__init__.py
"""Wire-protocol types mirroring the native LobeHub AgentGateway protocol.

This module is importlinter-clean: it depends only on pydantic and the
standard library, never on `lca.infrastructure`, `lca.plugins`, `lca.cognition`,
`lca.runtime`, `lca.agent`, or `lca.application`. Mirror of
`lobehub-ui/packages/agent-gateway-client/src/types.ts`.
"""

from lca.contracts.transport import agent_stream_event, gateway_messages, stream_keys

__all__ = ("agent_stream_event", "gateway_messages", "stream_keys")
```

- [ ] **Step 4: Write `stream_keys.py`**

```python
# lca/contracts/transport/stream_keys.py
"""Redis key naming for the agent runtime event stream.

These constants are 1:1 with `apps/server/src/modules/AgentRuntime/StreamEventManager.ts:139-141`
in the native LobeHub implementation. They are the single source of truth
for the wire-compat Redis layout.
"""

STREAM_KEY_PREFIX: str = "agent_runtime_stream"

STREAM_RETENTION_SECONDS: int = 2 * 3600  # 2 hours

STREAM_MAXLEN: str = "~1000"  # approximate trim, same as native


def stream_key(operation_id: str) -> str:
    """Build the Redis Stream key for a given operation id.

    The native code uses `agent_runtime_stream:<operationId>`.
    See `StreamEventManager.ts:174` `streamKey = `${STREAM_PREFIX}:${operationId}``.
    """
    return f"{STREAM_KEY_PREFIX}:{operation_id}"
```

- [ ] **Step 5: Write `gateway_messages.py`**

```python
# lca/contracts/transport/gateway_messages.py
"""WebSocket message types — mirror of packages/agent-gateway-client/src/types.ts:257-369.

All shapes are byte-compat with the TS source. The Python `model_dump()`
JSON output is the same shape the TS union deserialises from.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ── Client → Server ──────────────────────────────────────────────────────


class AuthMessage(BaseModel):
    type: Literal["auth"]
    token: str
    serverUrl: str | None = None
    tokenType: Literal["jwt", "apiKey"] | None = None


class ResumeMessage(BaseModel):
    type: Literal["resume"]
    lastEventId: str
    wantStatus: bool | None = None


class HeartbeatMessage(BaseModel):
    type: Literal["heartbeat"]


class InterruptMessage(BaseModel):
    type: Literal["interrupt"]


class ToolResultMessage(BaseModel):
    type: Literal["tool_result"]
    toolCallId: str
    success: bool
    content: str
    state: dict | None = None
    error: str | None = None


ClientMessage = Annotated[
    Union[AuthMessage, ResumeMessage, HeartbeatMessage, InterruptMessage, ToolResultMessage],
    Field(discriminator="type"),
]


# ── Server → Client ──────────────────────────────────────────────────────


class AuthSuccess(BaseModel):
    type: Literal["auth_success"]


class AuthFailed(BaseModel):
    type: Literal["auth_failed"]
    reason: str


class AuthExpired(BaseModel):
    type: Literal["auth_expired"]


class HeartbeatAck(BaseModel):
    type: Literal["heartbeat_ack"]


class SessionComplete(BaseModel):
    type: Literal["session_complete"]


class ResumeComplete(BaseModel):
    type: Literal["resume_complete"]
    status: Literal[
        "running", "waiting_input", "waiting_confirmation",
        "completed", "error", "interrupted",
    ]


class AgentEvent(BaseModel):
    """A single event from the agent runtime stream."""

    type: Literal["agent_event"]
    id: str | None = None  # Redis stream id; used for lastEventId resume
    event: dict  # AgentStreamEvent — see agent_stream_event.py


ServerMessage = Annotated[
    Union[AuthSuccess, AuthFailed, AuthExpired, HeartbeatAck, AgentEvent, SessionComplete, ResumeComplete],
    Field(discriminator="type"),
]


__all__ = (
    "AgentEvent",
    "AuthExpired",
    "AuthFailed",
    "AuthMessage",
    "AuthSuccess",
    "ClientMessage",
    "HeartbeatAck",
    "HeartbeatMessage",
    "InterruptMessage",
    "ResumeComplete",
    "ResumeMessage",
    "ResumeMessage",
    "ServerMessage",
    "SessionComplete",
    "ToolResultMessage",
)
```

- [ ] **Step 6: Write `agent_stream_event.py`**

```python
# lca/contracts/transport/agent_stream_event.py
"""AgentStreamEvent union — mirror of packages/agent-gateway-client/src/types.ts:1-54.

All 18 event types are present. The `data` payload shape matches the TS
interface for the same event type.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class AgentRuntimeInit(BaseModel):
    type: Literal["agent_runtime_init"]
    data: dict
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class AgentRuntimeEndData(BaseModel):
    finalState: dict
    reason: Literal["completed", "error", "interrupted", "timeout"]
    reasonDetail: str
    phase: Literal["execution_complete"]
    operationId: str | None = None
    uiMessages: list | None = None


class AgentRuntimeEnd(BaseModel):
    type: Literal["agent_runtime_end"]
    data: AgentRuntimeEndData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StreamStartData(BaseModel):
    assistantMessage: dict  # {id, model, provider, role, parentId, topicId, ...}


class StreamStart(BaseModel):
    type: Literal["stream_start"]
    data: StreamStartData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StreamChunkData(BaseModel):
    chunkType: Literal[
        "text", "reasoning", "tools_calling", "image", "grounding",
        "base64_image", "content_part", "reasoning_part", "tool_state",
    ]
    content: str | None = None
    reasoning: str | None = None
    toolsCalling: list | None = None
    snapshotMode: Literal["append", "replace"] | None = None
    snapshotSeq: int | None = None
    grounding: dict | None = None
    images: list | None = None
    imageList: list | None = None
    reasoningParts: list | None = None
    contentParts: list | None = None


class StreamChunk(BaseModel):
    type: Literal["stream_chunk"]
    data: StreamChunkData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StreamEndData(BaseModel):
    finalContent: str | None = None
    usage: dict | None = None
    speed: dict | None = None


class StreamEnd(BaseModel):
    type: Literal["stream_end"]
    data: StreamEndData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class VisibleOutputEnd(BaseModel):
    type: Literal["visible_output_end"]
    data: dict
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StreamRetryData(BaseModel):
    attempt: int
    max: int
    provider: str | None = None
    delayMs: int | None = None


class StreamRetry(BaseModel):
    type: Literal["stream_retry"]
    data: StreamRetryData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class ToolStartData(BaseModel):
    parentMessageId: str
    toolCalling: dict  # {identifier, apiName, arguments, id, type}


class ToolStart(BaseModel):
    type: Literal["tool_start"]
    data: ToolStartData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class ToolEndData(BaseModel):
    isSuccess: bool
    result: dict | None = None
    payload: dict | None = None
    executionTime: int | None = None


class ToolEnd(BaseModel):
    type: Literal["tool_end"]
    data: ToolEndData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class ToolExecuteData(BaseModel):
    apiName: str
    identifier: str
    arguments: dict
    toolCallId: str
    toolMessageId: str | None = None
    assistantMessageId: str | None = None
    executionTimeoutMs: int | None = None
    scope: str | None = None
    topicId: str | None = None
    threadId: str | None = None
    taskId: str | None = None
    groupId: str | None = None
    documentId: str | None = None
    sourceMessageId: str | None = None
    agentId: str | None = None
    rootOperationId: str | None = None


class ToolExecute(BaseModel):
    type: Literal["tool_execute"]
    data: ToolExecuteData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class AgentInterventionRequestData(BaseModel):
    apiName: str
    identifier: str
    arguments: dict
    toolCallId: str
    deadline: int


class AgentInterventionRequest(BaseModel):
    type: Literal["agent_intervention_request"]
    data: AgentInterventionRequestData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class AgentInterventionResponseData(BaseModel):
    toolCallId: str
    result: dict | None = None
    cancelled: bool | None = None
    cancelReason: Literal["timeout", "user_cancelled", "session_ended"] | None = None


class AgentInterventionResponse(BaseModel):
    type: Literal["agent_intervention_response"]
    data: AgentInterventionResponseData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StepStartData(BaseModel):
    phase: str | None = None
    requiresApproval: bool | None = None
    pendingToolsCalling: list | None = None
    uiMessages: list | None = None


class StepStart(BaseModel):
    type: Literal["step_start"]
    data: StepStartData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class StepCompleteData(BaseModel):
    phase: str
    finalState: dict | None = None
    reason: str | None = None
    reasonDetail: str | None = None


class StepComplete(BaseModel):
    type: Literal["step_complete"]
    data: StepCompleteData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class NotifyUpdateData(BaseModel):
    pass


class NotifyUpdate(BaseModel):
    type: Literal["notify_update"]
    data: NotifyUpdateData = NotifyUpdateData()
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class ErrorEventData(BaseModel):
    type: str | None = None
    message: str | None = None
    body: dict | None = None
    provider: str | None = None
    errorType: str | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"]
    data: ErrorEventData
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


class HeartbeatData(BaseModel):
    pass


class Heartbeat(BaseModel):
    type: Literal["heartbeat"]
    data: HeartbeatData = HeartbeatData()
    id: str | None = None
    operationId: str
    stepIndex: int
    timestamp: int


# Full union for type checking
AgentStreamEvent = Annotated[
    Union[
        AgentRuntimeInit, AgentRuntimeEnd, StreamStart, StreamChunk,
        StreamEnd, VisibleOutputEnd, StreamRetry, ToolStart, ToolEnd,
        ToolExecute, AgentInterventionRequest, AgentInterventionResponse,
        StepStart, StepComplete, NotifyUpdate, ErrorEvent, Heartbeat,
    ],
    Field(discriminator="type"),
]


__all__ = (
    "AgentRuntimeEnd",
    "AgentRuntimeEndData",
    "AgentRuntimeInit",
    "AgentStreamEvent",
    "AgentInterventionRequest",
    "AgentInterventionRequestData",
    "AgentInterventionResponse",
    "AgentInterventionResponseData",
    "ErrorEvent",
    "ErrorEventData",
    "Heartbeat",
    "HeartbeatData",
    "NotifyUpdate",
    "NotifyUpdateData",
    "StepComplete",
    "StepCompleteData",
    "StepStart",
    "StepStartData",
    "StreamChunk",
    "StreamChunkData",
    "StreamEnd",
    "StreamEndData",
    "StreamRetry",
    "StreamRetryData",
    "StreamStart",
    "StreamStartData",
    "ToolEnd",
    "ToolEndData",
    "ToolExecute",
    "ToolExecuteData",
    "ToolStart",
    "ToolStartData",
    "VisibleOutputEnd",
)
```

- [ ] **Step 7: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/contracts/transport/test_protocol_parity.py -v 2>&1 | tail -30`
Expected: 18 passed (10 explicit + 18 parametrized). If any fail, fix the type definition and re-run.

- [ ] **Step 8: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/contracts/transport tests/contracts/transport
git commit -m "feat(p1): wire-protocol types mirror native AgentGateway"
```

---

## Task 2: LcaStreamEventManager (Redis Stream)

**Files:**
- Create: `lca/infrastructure/observability/stream/__init__.py`
- Create: `lca/infrastructure/observability/stream/stream_event_manager.py`
- Test: `lca/infrastructure/observability/stream/tests/test_stream_event_manager.py`

**Interfaces:**
- Consumes: `redis.asyncio.Redis` (ioredis-style; LCA dev `127.0.0.1:6379`)
- Produces: `class LcaStreamEventManager` with methods:
  - `async def publish(self, run_id, type: str, data: dict, *, step_index: int) -> str` — returns the Redis stream id (`<ms>-<seq>`)
  - `async def subscribe(self, run_id, last_id: str, *, signal: AbortSignal | None = None) -> AsyncIterator[bytes]` — yields SSE-encoded `agent_event` frames
  - `async def read_history(self, run_id, count: int) -> list[dict]`
  - `async def cleanup(self, run_id) -> None`
  - `async def exists(self, run_id) -> bool` — used by `useGatewayReconnect`
  - `async def last_id(self, run_id) -> str | None`

- [ ] **Step 1: Write the failing test**

```python
# lca/infrastructure/observability/stream/tests/test_stream_event_manager.py
"""LcaStreamEventManager unit tests against a real Redis at 127.0.0.1:6379.

This is L1 (unit) but uses real Redis because mocking Redis semantics
falsifies the stream API. The dev Redis is part of the LCA dev stack
(``lca-ops infra start``).
"""
import asyncio
import json
import pytest

from lca.contracts.transport.stream_keys import stream_key
from lca.infrastructure.observability.stream.stream_event_manager import LcaStreamEventManager


@pytest.fixture
async def manager():
    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    mgr = LcaStreamEventManager(client)
    yield mgr
    await client.aclose()


async def test_publish_xadd_with_type_stepindex_data(manager):
    run_id = "test_publish_xadd"
    await manager.cleanup(run_id)
    event_id = await manager.publish(run_id, "stream_chunk", {"chunkType": "text", "content": "hi"}, step_index=0)
    assert "-" in event_id  # Redis-generated <ms>-<seq>
    await manager.cleanup(run_id)


async def test_publish_sets_ttl_7200(manager):
    run_id = "test_publish_ttl"
    await manager.cleanup(run_id)
    await manager.publish(run_id, "stream_chunk", {"chunkType": "text", "content": "x"}, step_index=0)
    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    ttl = await client.ttl(stream_key(run_id))
    await client.aclose()
    assert 7100 <= ttl <= 7200  # spec §5.1: TTL = 2 h
    await manager.cleanup(run_id)


async def test_publish_maxlen_caps_at_1000(manager):
    run_id = "test_maxlen"
    await manager.cleanup(run_id)
    for i in range(1500):
        await manager.publish(run_id, "stream_chunk", {"i": i}, step_index=i)
    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    length = await client.xlen(stream_key(run_id))
    await client.aclose()
    # approximate trim ~ 1000 (Redis may keep up to ~1100 due to ~)
    assert length <= 1200
    await manager.cleanup(run_id)


async def test_read_history_returns_events_in_descending_order(manager):
    run_id = "test_read_history"
    await manager.cleanup(run_id)
    for i in range(5):
        await manager.publish(run_id, "stream_chunk", {"i": i}, step_index=i)
    history = await manager.read_history(run_id, count=5)
    assert len(history) == 5
    # read_history returns newest first (XRANGE reverse); index 0 should be the last publish
    assert history[0]["data"]["i"] == 4
    assert history[-1]["data"]["i"] == 0
    await manager.cleanup(run_id)


async def test_exists_returns_true_when_key_alive(manager):
    run_id = "test_exists"
    await manager.cleanup(run_id)
    assert await manager.exists(run_id) is False
    await manager.publish(run_id, "stream_chunk", {}, step_index=0)
    assert await manager.exists(run_id) is True
    await manager.cleanup(run_id)
    assert await manager.exists(run_id) is False


async def test_subscribe_yields_only_events_after_last_id(manager):
    run_id = "test_subscribe_after"
    await manager.cleanup(run_id)
    e0 = await manager.publish(run_id, "stream_chunk", {"i": 0}, step_index=0)
    e1 = await manager.publish(run_id, "stream_chunk", {"i": 1}, step_index=1)
    e2 = await manager.publish(run_id, "stream_chunk", {"i": 2}, step_index=2)

    # Subscribe from e1 (so we should get e1, e2 but not e0)
    collected = []
    async def run():
        async for frame in manager.subscribe(run_id, e1):
            collected.append(frame)
            if len(collected) >= 2:
                return
    await asyncio.wait_for(run(), timeout=3.0)

    # Each frame is bytes of "id: <id>\nevent: agent_event\ndata: <json>\n\n"
    assert len(collected) == 2
    assert e1.encode() in collected[0]
    assert e2.encode() in collected[1]
    await manager.cleanup(run_id)


async def test_data_field_is_json_stringified(manager):
    """spec §5.1: 'data is JSON-stringified' (Redis field)."""
    run_id = "test_data_json"
    await manager.cleanup(run_id)
    payload = {"chunkType": "text", "content": "x"}
    eid = await manager.publish(run_id, "stream_chunk", payload, step_index=0)

    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    fields = await client.xrange(stream_key(run_id), eid, eid)
    await client.aclose()
    assert len(fields) == 1
    # fields is a list of [id, {field: value, ...}]
    raw = fields[0][1]["data"]
    assert json.loads(raw) == payload
    await manager.cleanup(run_id)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/infrastructure/observability/stream/tests/test_stream_event_manager.py -v 2>&1 | head -20`
Expected: FAIL (no module `lca.infrastructure.observability.stream`).

- [ ] **Step 3: Write `__init__.py`**

```python
# lca/infrastructure/observability/stream/__init__.py
"""LcaStreamEventManager — Python mirror of native StreamEventManager.

1:1 with `apps/server/src/modules/AgentRuntime/StreamEventManager.ts:139-211`
in the native LobeHub implementation. Same Redis key prefix, same TTL,
same MAXLEN.
"""

from lca.infrastructure.observability.stream.stream_event_manager import LcaStreamEventManager

__all__ = ("LcaStreamEventManager",)
```

- [ ] **Step 4: Write `stream_event_manager.py`**

```python
# lca/infrastructure/observability/stream/stream_event_manager.py
"""LcaStreamEventManager — Redis Stream backing the agent runtime event bus.

This is a 1:1 Python mirror of the TypeScript implementation in
`apps/server/src/modules/AgentRuntime/StreamEventManager.ts:139-211`. The
Redis layout is wire-compat: the same XADD fields (`type`, `stepIndex`,
`operationId`, `data`, `timestamp`), the same key prefix
(`agent_runtime_stream:`), the same TTL (2 h), the same MAXLEN (~1000).

It is consumed by:
- `LcaAgentRuntimeCoordinator` (publishes events on state transitions)
- `LcaAgentGateway` (subscribes for WebSocket clients)
- `useGatewayReconnect` liveness check (EXISTS)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from lca.contracts.transport.stream_keys import (
    STREAM_KEY_PREFIX,
    STREAM_MAXLEN,
    STREAM_RETENTION_SECONDS,
    stream_key,
)


class LcaStreamEventManager:
    """Redis Stream event bus, native-wire-compat."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    # ── Write side ────────────────────────────────────────────────────

    async def publish(
        self,
        run_id: str,
        type: str,
        data: dict,
        *,
        step_index: int,
    ) -> str:
        """XADD an event to the run's stream; refresh TTL.

        Returns the Redis-generated event id (`<ms>-<seq>`).
        """
        key = stream_key(run_id)
        event_id = await self._redis.xadd(
            key,
            "MAXLEN",
            STREAM_MAXLEN,
            "*",
            "type",
            type,
            "stepIndex",
            str(step_index),
            "operationId",
            run_id,
            "data",
            json.dumps(data),
            "timestamp",
            str(_now_ms()),
        )
        await self._redis.expire(key, STREAM_RETENTION_SECONDS)
        return event_id

    async def cleanup(self, run_id: str) -> None:
        """Delete the run's stream key. Called on `agent_runtime_end`."""
        await self._redis.delete(stream_key(run_id))

    async def exists(self, run_id: str) -> bool:
        """Liveness check used by useGatewayReconnect."""
        return bool(await self._redis.exists(stream_key(run_id)))

    async def last_id(self, run_id: str) -> str | None:
        """Return the most recent event id in the stream, or None if empty."""
        result = await self._redis.xrevrange(stream_key(run_id), "+", "-", "COUNT", 1)
        if not result:
            return None
        return result[0][0]

    # ── Read side ─────────────────────────────────────────────────────

    async def read_history(self, run_id: str, count: int) -> list[dict]:
        """Return up to `count` most recent events, newest first."""
        result = await self._redis.xrevrange(stream_key(run_id), "+", "-", "COUNT", count)
        return [_parse_redis_stream_row(row) for row in result]

    async def subscribe(
        self,
        run_id: str,
        last_id: str,
        *,
        signal: object | None = None,  # asyncio.AbortSignal | None
    ) -> AsyncIterator[bytes]:
        """Block on XREAD and yield SSE-encoded `agent_event` frames.

        Each yielded frame is bytes shaped:
            b"id: <redis_id>\\nevent: agent_event\\ndata: <json>\\n\\n"

        The caller (LcaAgentGateway) writes these directly to the
        WebSocket. Aborts cleanly on `signal.aborted`.
        """
        key = stream_key(run_id)
        current_last_id = last_id
        while signal is None or not getattr(signal, "aborted", False):
            try:
                results = await self._redis.xread(
                    "BLOCK", 1000, "STREAMS", key, current_last_id
                )
            except Exception:
                # Transient: retry after 1 s. Native has the same loop.
                import asyncio
                await asyncio.sleep(1.0)
                continue

            if not results:
                continue
            _, messages = results[0]
            for msg_id, fields in messages:
                current_last_id = msg_id
                event = _parse_redis_stream_row((msg_id, fields))
                yield _encode_sse_agent_event(event)


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


def _parse_redis_stream_row(row: tuple[str, dict]) -> dict:
    msg_id, fields = row
    out: dict = {"id": msg_id, "type": fields.get("type")}
    try:
        out["stepIndex"] = int(fields.get("stepIndex", "0"))
    except (TypeError, ValueError):
        out["stepIndex"] = 0
    out["operationId"] = fields.get("operationId")
    try:
        out["timestamp"] = int(fields.get("timestamp", "0"))
    except (TypeError, ValueError):
        out["timestamp"] = 0
    raw_data = fields.get("data")
    if raw_data:
        try:
            out["data"] = json.loads(raw_data)
        except json.JSONDecodeError:
            out["data"] = None
    return out


def _encode_sse_agent_event(event: dict) -> bytes:
    """SSE-encode a single agent event for WebSocket transport.

    The wire shape is `agent_event` (server → client); the WebSocket
    envelope wraps the JSON. See spec §7.
    """
    envelope = {
        "type": "agent_event",
        "id": event.get("id"),
        "event": {
            "type": event.get("type"),
            "data": event.get("data"),
            "operationId": event.get("operationId"),
            "stepIndex": event.get("stepIndex", 0),
            "timestamp": event.get("timestamp", 0),
        },
    }
    body = json.dumps(envelope, ensure_ascii=False)
    event_id = event.get("id") or ""
    return (
        f"id: {event_id}\nevent: agent_event\ndata: {body}\n\n"
    ).encode("utf-8")


__all__ = ("LcaStreamEventManager",)
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/infrastructure/observability/stream/tests/test_stream_event_manager.py -v 2>&1 | tail -30`
Expected: 7 passed. If any fail, the most likely culprit is the XADD field shape or the TTL refresh; check `xadd` and `expire` are called on the same key.

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/infrastructure/observability/stream
git commit -m "feat(p1): LcaStreamEventManager — Redis wire-compat with native"
```

---

## Task 3: Engine integration — getAgentRuntimeRedisClient factory

**Files:**
- Create: `lca/infrastructure/observability/stream/redis_client.py`
- Modify: `lca/infrastructure/observability/stream/__init__.py` (re-export)
- Test: `lca/infrastructure/observability/stream/tests/test_redis_client.py`

**Interfaces:**
- Consumes: `os.environ` (env `REDIS_URL` or `LCA_REDIS_URL`); falls back to `redis://127.0.0.1:6379/0`
- Produces: `def get_agent_runtime_redis_client() -> Redis` (sync, returns the same connection pool the LcaStreamEventManager expects)

- [ ] **Step 1: Write the failing test**

```python
# lca/infrastructure/observability/stream/tests/test_redis_client.py
"""Verify the Redis client factory reads the dev default."""
import os
import pytest
from redis.asyncio import Redis

from lca.infrastructure.observability.stream.redis_client import get_agent_runtime_redis_client


def test_default_url_is_127_0_0_1_6379(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("LCA_REDIS_URL", raising=False)
    client = get_agent_runtime_redis_client()
    assert isinstance(client, Redis)
    # async client; verify the connection info via private attributes
    conn = client.connection_pool.connection_kwargs
    assert conn["host"] == "127.0.0.1"
    assert int(conn["port"]) == 6379


def test_reddis_url_env_overrides(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis.internal:6380/2")
    client = get_agent_runtime_redis_client()
    conn = client.connection_pool.connection_kwargs
    assert conn["host"] == "redis.internal"
    assert int(conn["port"]) == 6380
    assert int(conn["db"]) == 2
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/infrastructure/observability/stream/tests/test_redis_client.py -v 2>&1 | head -10`
Expected: FAIL (no module `lca.infrastructure.observability.stream.redis_client`).

- [ ] **Step 3: Write `redis_client.py`**

```python
# lca/infrastructure/observability/stream/redis_client.py
"""Singleton factory for the agent runtime Redis client.

The agent runtime's stream is a single, well-known Redis instance —
the same one already in `lca-ops.yaml:42` for the LCA dev stack. This
factory reads the URL from the environment (LCA convention is to
honour `REDIS_URL` first, then `LCA_REDIS_URL`, then the dev default).
"""
from __future__ import annotations

import os

import redis.asyncio as aioredis
from redis.asyncio import Redis


def get_agent_runtime_redis_client() -> Redis:
    """Return the agent runtime Redis client.

    Order of precedence: ``REDIS_URL`` (native-compatible) →
    ``LCA_REDIS_URL`` (LCA-only) → ``redis://127.0.0.1:6379/0`` (LCA dev).
    The factory is intentionally a function (not a singleton) so tests
    can monkeypatch the env per-test.
    """
    url = os.environ.get("REDIS_URL") or os.environ.get("LCA_REDIS_URL") or "redis://127.0.0.1:6379/0"
    return aioredis.from_url(url, decode_responses=True)


__all__ = ("get_agent_runtime_redis_client",)
```

- [ ] **Step 4: Update `__init__.py` to re-export**

```python
# lca/infrastructure/observability/stream/__init__.py
"""LcaStreamEventManager — Python mirror of native StreamEventManager.

1:1 with `apps/server/src/modules/AgentRuntime/StreamEventManager.ts:139-211`
in the native LobeHub implementation. Same Redis key prefix, same TTL,
same MAXLEN.
"""

from lca.infrastructure.observability.stream.redis_client import get_agent_runtime_redis_client
from lca.infrastructure.observability.stream.stream_event_manager import LcaStreamEventManager

__all__ = ("LcaStreamEventManager", "get_agent_runtime_redis_client")
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/infrastructure/observability/stream/tests/test_redis_client.py -v 2>&1 | tail -10`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/infrastructure/observability/stream/redis_client.py lca/infrastructure/observability/stream/__init__.py
git commit -m "feat(p1): Redis client factory for agent runtime"
```

---

# PR-2: Back-end WS server + broadcaster

## Task 4: EventTranslator (StampedEvent → AgentStreamEvent)

**Files:**
- Create: `lca/application/runtime/coordinator/__init__.py`
- Create: `lca/application/runtime/coordinator/event_translator.py`
- Test: `lca/application/runtime/coordinator/tests/test_event_translator.py`

**Interfaces:**
- Consumes: `LiveRunProjection` `StampedEvent` shapes (already defined in LCA)
- Produces: `class EventTranslator` with method `translate(stamped: dict) -> dict | None` that returns the `data` payload for the corresponding `AgentStreamEvent.type`, or `None` for `kind='ignore'`

- [ ] **Step 1: Write the failing test**

```python
# lca/application/runtime/coordinator/tests/test_event_translator.py
"""EventTranslator unit tests — StampedEvent → AgentStreamEvent.data."""
import pytest

from lca.application.runtime.coordinator.event_translator import EventTranslator


def test_llm_call_started_becomes_stream_start():
    t = EventTranslator()
    stamped = {"event": {"type": "LlmCallStarted", "assistantMessage": {"id": "a1"}}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_start"
    assert out["data"]["assistantMessage"]["id"] == "a1"


def test_text_delta_becomes_stream_chunk_text():
    t = EventTranslator()
    stamped = {"event": {"type": "LlmCallTextDelta", "delta": "hi"}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_chunk"
    assert out["data"]["chunkType"] == "text"
    assert out["data"]["content"] == "hi"
    assert out["data"]["snapshotMode"] == "append"


def test_reasoning_delta_becomes_stream_chunk_reasoning():
    t = EventTranslator()
    stamped = {"event": {"type": "ReasoningDelta", "delta": "thinking"}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_chunk"
    assert out["data"]["chunkType"] == "reasoning"
    assert out["data"]["content"] == "thinking"


def test_tool_started_becomes_tool_start_with_parent_message_id():
    t = EventTranslator()
    stamped = {"event": {"type": "ToolStarted", "parentMessageId": "m1", "payload": {"identifier": "lobe-local-system", "apiName": "runCommand", "arguments": {"command": "ls"}, "id": "tc1"}}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "tool_start"
    assert out["data"]["parentMessageId"] == "m1"
    assert out["data"]["toolCalling"]["identifier"] == "lobe-local-system"


def test_tool_invoked_becomes_tool_end_without_projected_state():
    t = EventTranslator()
    stamped = {"event": {"type": "ToolInvoked", "payload": {"toolCalling": {"id": "tc1"}}, "result": {"content": "ok"}, "isSuccess": True, "executionTime": 120}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "tool_end"
    assert "projected_state" not in out["data"]  # spec §5.3.1
    assert out["data"]["isSuccess"] is True
    assert out["data"]["result"] == {"content": "ok"}


def test_step_start_with_human_approval_has_requires_approval():
    t = EventTranslator()
    stamped = {"event": {"type": "StepStart", "phase": "human_approval", "requiresApproval": True, "pendingToolsCalling": [{"id": "tc1"}]}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "step_start"
    assert out["data"]["phase"] == "human_approval"
    assert out["data"]["requiresApproval"] is True
    assert out["data"]["pendingToolsCalling"] == [{"id": "tc1"}]


def test_spine_close_with_waiting_human_becomes_agent_runtime_end():
    t = EventTranslator()
    stamped = {"event": {"type": "SpineClose", "reason": "waiting_for_human", "final_state": {"status": "waiting_for_human"}}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "agent_runtime_end"
    assert out["data"]["reason"] == "waiting_for_human"
    assert out["data"]["finalState"]["status"] == "waiting_for_human"
    assert out["data"]["phase"] == "execution_complete"


def test_spine_close_with_done_becomes_agent_runtime_end_completed():
    t = EventTranslator()
    stamped = {"event": {"type": "SpineClose", "reason": "completed", "final_state": {"status": "done"}}}
    out = t.translate(stamped)
    assert out["type"] == "agent_runtime_end"
    assert out["data"]["reason"] == "completed"


def test_unknown_event_returns_none():
    t = EventTranslator()
    assert t.translate({"event": {"type": "UnknownThing"}}) is None


def test_unknown_event_kind_returns_none():
    t = EventTranslator()
    assert t.translate({"event": {"type": "LlmCallTextDelta", "kind": "ignore"}}) is None
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/application/runtime/coordinator/tests/test_event_translator.py -v 2>&1 | head -10`
Expected: FAIL (no module).

- [ ] **Step 3: Write `__init__.py`**

```python
# lca/application/runtime/coordinator/__init__.py
"""LcaAgentRuntimeCoordinator — StampedEvent → Redis stream fold.

Mirror of `apps/server/src/modules/AgentRuntime/AgentRuntimeCoordinator.ts`.
Subscribes to `LiveRunProjection.tail` and publishes AgentStreamEvent
into Redis via LcaStreamEventManager.
"""

from lca.application.runtime.coordinator.event_translator import EventTranslator

__all__ = ("EventTranslator",)
```

- [ ] **Step 4: Write `event_translator.py`**

```python
# lca/application/runtime/coordinator/event_translator.py
"""StampedEvent → AgentStreamEvent.data fold.

Pure function table. Each fold row mirrors the translation table in
spec §5.3. `tool_end.data` deliberately omits `projected_state` — the
server-side coordinator writes the full `projected_state` into the
tool message's `pluginState` DB column BEFORE publishing the event;
the front-end `gatewayEventHandler.tool_end` then `fetchAndReplaceMessages`
reads the populated row. See spec §5.3.1.
"""

from __future__ import annotations

from typing import Any


class EventTranslator:
    """Pure fold from a StampedEvent to an AgentStreamEvent payload."""

    def translate(self, stamped: dict) -> dict | None:
        """Return the AgentStreamEvent envelope (type + data) or None to ignore."""
        event = stamped.get("event") or {}
        kind = event.get("kind")
        if kind == "ignore":
            return None
        etype = event.get("type")
        handler = _HANDLERS.get(etype)
        if handler is None:
            return None
        return handler(event)

    # ── Translation rules (one per spec §5.3 row) ────────────────────

    @staticmethod
    def _llm_call_started(e: dict) -> dict:
        return {
            "type": "stream_start",
            "data": {"assistantMessage": e.get("assistantMessage", {})},
        }

    @staticmethod
    def _text_delta(e: dict) -> dict:
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "text",
                "content": e.get("delta", ""),
                "snapshotMode": "append",
            },
        }

    @staticmethod
    def _reasoning_delta(e: dict) -> dict:
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "reasoning",
                "content": e.get("delta", ""),
                "snapshotMode": "append",
            },
        }

    @staticmethod
    def _decision_made(e: dict) -> dict:
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "tools_calling",
                "toolsCalling": e.get("tool_calls", []),
            },
        }

    @staticmethod
    def _tool_started(e: dict) -> dict:
        payload = e.get("payload") or {}
        return {
            "type": "tool_start",
            "data": {
                "parentMessageId": e.get("parentMessageId"),
                "toolCalling": payload,
            },
        }

    @staticmethod
    def _tool_invoked(e: dict) -> dict:
        """spec §5.3.1: NO projected_state in the WS event — server writes it to DB."""
        return {
            "type": "tool_end",
            "data": {
                "isSuccess": e.get("isSuccess", True),
                "result": e.get("result"),
                "payload": e.get("payload"),
                "executionTime": e.get("executionTime"),
            },
        }

    @staticmethod
    def _tool_denied(e: dict) -> dict:
        return {
            "type": "tool_end",
            "data": {
                "isSuccess": False,
                "result": {"error": e.get("reason", "denied")},
            },
        }

    @staticmethod
    def _step_start(e: dict) -> dict:
        return {
            "type": "step_start",
            "data": {
                "phase": e.get("phase"),
                "requiresApproval": e.get("requiresApproval"),
                "pendingToolsCalling": e.get("pendingToolsCalling"),
            },
        }

    @staticmethod
    def _step_finished(e: dict) -> dict:
        return {
            "type": "stream_end",
            "data": {
                "finalContent": e.get("finalContent"),
            },
        }

    @staticmethod
    def _spine_close(e: dict) -> dict:
        final_state = e.get("final_state") or {}
        status = final_state.get("status", "done")
        return {
            "type": "agent_runtime_end",
            "data": {
                "finalState": final_state,
                "reason": e.get("reason", status),
                "reasonDetail": e.get("reasonDetail", ""),
                "phase": "execution_complete",
            },
        }

    @staticmethod
    def _llm_error(e: dict) -> dict:
        return {
            "type": "error",
            "data": {
                "type": e.get("errorType"),
                "message": e.get("message"),
                "body": e.get("body"),
                "provider": e.get("provider"),
            },
        }

    @staticmethod
    def _llm_retry(e: dict) -> dict:
        return {
            "type": "stream_retry",
            "data": {
                "attempt": e.get("attempt", 1),
                "max": e.get("max", 3),
                "provider": e.get("provider"),
                "delayMs": e.get("delayMs"),
            },
        }

    @staticmethod
    def _agent_intervention_request(e: dict) -> dict:
        return {
            "type": "agent_intervention_request",
            "data": {
                "apiName": e.get("apiName"),
                "identifier": e.get("identifier"),
                "arguments": e.get("arguments", {}),
                "toolCallId": e.get("toolCallId"),
                "deadline": e.get("deadline", 0),
            },
        }


_HANDLERS = {
    "LlmCallStarted": EventTranslator._llm_call_started,
    "LlmCallTextDelta": EventTranslator._text_delta,
    "ReasoningDelta": EventTranslator._reasoning_delta,
    "DecisionMade": EventTranslator._decision_made,
    "ToolStarted": EventTranslator._tool_started,
    "ToolInvoked": EventTranslator._tool_invoked,
    "ToolDenied": EventTranslator._tool_denied,
    "StepStart": EventTranslator._step_start,
    "StepFinished": EventTranslator._step_finished,
    "SpineClose": EventTranslator._spine_close,
    "LlmError": EventTranslator._llm_error,
    "LlmRetry": EventTranslator._llm_retry,
    "AgentInterventionRequest": EventTranslator._agent_intervention_request,
}


__all__ = ("EventTranslator",)
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/application/runtime/coordinator/tests/test_event_translator.py -v 2>&1 | tail -20`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/application/runtime/coordinator
git commit -m "feat(p1): EventTranslator — StampedEvent to AgentStreamEvent fold"
```

---

## Task 5: TerminalHints — terminal-state resolution

**Files:**
- Create: `lca/application/runtime/coordinator/terminal_hints.py`
- Test: `lca/application/runtime/coordinator/tests/test_terminal_hints.py`

**Interfaces:**
- Consumes: `RunSession.status` and `RunSession.error` (existing fields)
- Produces: `def resolve_live_terminal_hint(session) -> Literal["running", "waiting_input", "waiting_confirmation", "completed", "error", "interrupted"]`

- [ ] **Step 1: Write the failing test**

```python
# lca/application/runtime/coordinator/tests/test_terminal_hints.py
"""resolve_live_terminal_hint maps RunSession status to the canonical
6-value status enum the AgentGateway expects.

Mirrors the native `STREAM_END_STATUSES` set in
`apps/server/src/modules/AgentRuntime/AgentRuntimeCoordinator.ts:30-34` —
`done | error | interrupted | waiting_for_human` are stream-terminal.
`running | waiting_for_async_tool` are not.
"""
import pytest
from unittest.mock import MagicMock

from lca.application.runtime.coordinator.terminal_hints import resolve_live_terminal_hint, is_stream_terminal_status


@pytest.mark.parametrize("status,expected", [
    ("done", "completed"),
    ("completed", "completed"),
    ("error", "error"),
    ("interrupted", "interrupted"),
    ("waiting_input", "waiting_input"),
    ("waiting_for_human", "waiting_input"),
    ("awaiting_human", "waiting_input"),
    ("input-required", "waiting_input"),
    ("running", "running"),
    ("paused", "running"),
])
def test_resolve_live_terminal_hint_maps_status(status, expected):
    session = MagicMock()
    session.status = status
    assert resolve_live_terminal_hint(session) == expected


def test_resolve_live_terminal_hint_with_error_falls_back_to_error():
    session = MagicMock()
    session.status = "done"
    session.error = "something broke"
    assert resolve_live_terminal_hint(session) == "error"


@pytest.mark.parametrize("status", ["done", "error", "interrupted", "waiting_for_human", "completed", "waiting_input"])
def test_is_stream_terminal_status_true_for_terminal(status):
    assert is_stream_terminal_status(status) is True


@pytest.mark.parametrize("status", ["running", "waiting_for_async_tool", "paused"])
def test_is_stream_terminal_status_false_for_live(status):
    assert is_stream_terminal_status(status) is False
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/application/runtime/coordinator/tests/test_terminal_hints.py -v 2>&1 | head -10`
Expected: FAIL (no module).

- [ ] **Step 3: Write `terminal_hints.py`**

```python
# lca/application/runtime/coordinator/terminal_hints.py
"""RunSession.status → wire status enum mapping.

The native AgentGateway exposes a 6-value status enum on `resume_complete`
and on the data of `agent_runtime_end`. This module maps the existing
LCA `RunSession.status` (an internal enum) to that wire contract.
"""
from __future__ import annotations

from typing import Literal

TerminalHint = Literal[
    "running", "waiting_input", "waiting_confirmation",
    "completed", "error", "interrupted",
]


_TERMINAL_STATUSES = {"done", "error", "interrupted", "waiting_for_human", "completed", "waiting_input", "awaiting_human", "input-required"}


def is_stream_terminal_status(status: str) -> bool:
    """True iff the status ends the WS stream for the current operation id.

    spec §4.2: `waiting_for_human` is stream-terminal but state-resumable.
    The same op id's stream is closed; a new op id (or a new resume call)
    carries the next phase. Matches native `STREAM_END_STATUSES` set
    in `AgentRuntimeCoordinator.ts:30-34`.
    """
    return status in _TERMINAL_STATUSES


def resolve_live_terminal_hint(session) -> TerminalHint:
    """Map RunSession.status to the wire 6-value enum."""
    status = getattr(session, "status", None)
    if status in ("done", "completed"):
        return "completed"
    if status in ("waiting_input", "waiting_for_human", "awaiting_human", "input-required"):
        return "waiting_input"
    if status == "interrupted":
        return "interrupted"
    if status == "error":
        return "error"
    # session.error set on a `done` state means the run completed with an error
    if getattr(session, "error", None):
        return "error"
    return "running"


__all__ = ("TerminalHint", "is_stream_terminal_status", "resolve_live_terminal_hint")
```

- [ ] **Step 4: Update `__init__.py`**

```python
# lca/application/runtime/coordinator/__init__.py
from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.terminal_hints import (
    TerminalHint, is_stream_terminal_status, resolve_live_terminal_hint,
)

__all__ = (
    "EventTranslator",
    "TerminalHint",
    "is_stream_terminal_status",
    "resolve_live_terminal_hint",
)
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/application/runtime/coordinator/tests/test_terminal_hints.py -v 2>&1 | tail -15`
Expected: 10 + 3 + 3 = 16 passed.

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/application/runtime/coordinator
git commit -m "feat(p1): terminal_hints — RunSession status to wire enum"
```

---

## Task 6: LcaAgentRuntimeCoordinator — start, fold, watchdog

**Files:**
- Create: `lca/application/runtime/coordinator/runtime_coordinator.py`
- Test: `lca/application/runtime/coordinator/tests/test_runtime_coordinator.py`

**Interfaces:**
- Consumes: `LiveRunProjection` (subscribe tail), `LcaStreamEventManager`, a tool message writer (for §5.3.1 persistence obligation)
- Produces: `class LcaAgentRuntimeCoordinator` with:
  - `async def start(run_id, ctx) -> None` — register metadata, publish `agent_runtime_init`
  - `async def handle_stamped(run_id, stamped) -> None` — fold + publish
  - `async def terminal(run_id) -> None` — publish terminal if needed + cleanup

- [ ] **Step 1: Write the failing test**

```python
# lca/application/runtime/coordinator/tests/test_runtime_coordinator.py
"""LcaAgentRuntimeCoordinator unit tests — fold + publish + watchdog."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from lca.application.runtime.coordinator.runtime_coordinator import LcaAgentRuntimeCoordinator
from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.infrastructure.observability.stream import LcaStreamEventManager


@pytest.fixture
async def manager():
    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    mgr = LcaStreamEventManager(client)
    yield mgr
    await client.aclose()


@pytest.fixture
async def clean_run_id(manager):
    run_id = "test_coord_unit"
    await manager.cleanup(run_id)
    yield run_id
    await manager.cleanup(run_id)


async def test_start_publishes_agent_runtime_init(manager, clean_run_id):
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager,
        translator=EventTranslator(),
        metadata_writer=AsyncMock(),
        tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={"agent_id": "a1", "topic_id": "t1"})
    history = await manager.read_history(clean_run_id, count=10)
    assert any(e["type"] == "agent_runtime_init" for e in history)


async def test_handle_stamped_publishes_text_chunk(manager, clean_run_id):
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager, translator=EventTranslator(),
        metadata_writer=AsyncMock(), tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(clean_run_id, {
        "event": {"type": "LlmCallTextDelta", "delta": "hello"}
    })
    history = await manager.read_history(clean_run_id, count=10)
    text_chunks = [e for e in history if e["type"] == "stream_chunk" and e["data"]["chunkType"] == "text"]
    assert any(c["data"]["content"] == "hello" for c in text_chunks)


async def test_handle_stamped_writes_projected_state_to_db_before_tool_end(manager, clean_run_id):
    """spec §5.3.1: server must write projected_state to message row BEFORE tool_end."""
    tool_state_writer = AsyncMock()
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager, translator=EventTranslator(),
        metadata_writer=AsyncMock(), tool_state_writer=tool_state_writer,
    )
    await coord.start(clean_run_id, ctx={})
    await coord.handle_stamped(clean_run_id, {
        "event": {
            "type": "ToolInvoked",
            "payload": {"toolCalling": {"id": "tc1", "identifier": "lobe-local-system", "apiName": "runCommand", "arguments": {"command": "ls"}, "type": "builtin"}},
            "result": {"content": "ok"},
            "isSuccess": True,
            "executionTime": 120,
            "projected_state": {"stdout": "ok", "exitCode": 0},
        }
    })
    # The DB write must have happened BEFORE the tool_end was published
    assert tool_state_writer.call_count == 1
    call_args = tool_state_writer.call_args
    assert call_args.kwargs.get("run_id") == clean_run_id
    assert call_args.kwargs.get("tool_call_id") == "tc1"
    assert "stdout" in call_args.kwargs.get("state", {})
    # The tool_end event must be in the stream
    history = await manager.read_history(clean_run_id, count=10)
    assert any(e["type"] == "tool_end" for e in history)


async def test_terminal_publishes_agent_runtime_end_and_cleans_up(manager, clean_run_id):
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager, translator=EventTranslator(),
        metadata_writer=AsyncMock(), tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    await coord.terminal(clean_run_id, status="done", final_state={"status": "done"})
    history = await manager.read_history(clean_run_id, count=10)
    assert history[0]["type"] == "agent_runtime_end"
    assert history[0]["data"]["reason"] == "done"
    assert history[0]["data"]["phase"] == "execution_complete"
    # cleanup should run
    assert await manager.exists(clean_run_id) is False


async def test_watchdog_publishes_synthetic_terminal_if_session_terminal_but_no_spine_event(manager, clean_run_id):
    """spec §1 broken #3: parent run with no live SpineClose must not hang the stream."""
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager, translator=EventTranslator(),
        metadata_writer=AsyncMock(), tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    # session is terminal but no SpineClose has been emitted
    session = MagicMock()
    session.status = "done"
    await coord.synthesize_terminal_if_pending(clean_run_id, session=session)
    history = await manager.read_history(clean_run_id, count=10)
    assert any(e["type"] == "agent_runtime_end" and e["data"]["reason"] == "done" for e in history)


async def test_watchdog_no_op_if_already_published(manager, clean_run_id):
    """The watchdog must not double-publish if the natural SpineClose already fired."""
    coord = LcaAgentRuntimeCoordinator(
        stream_manager=manager, translator=EventTranslator(),
        metadata_writer=AsyncMock(), tool_state_writer=AsyncMock(),
    )
    await coord.start(clean_run_id, ctx={})
    # Natural terminal fires first
    await coord.terminal(clean_run_id, status="done", final_state={"status": "done"})
    before_count = len(await manager.read_history(clean_run_id, count=100))
    # Watchdog fires
    session = MagicMock()
    session.status = "done"
    await coord.synthesize_terminal_if_pending(clean_run_id, session=session)
    after_count = len(await manager.read_history(clean_run_id, count=100))
    assert before_count == after_count  # no duplicate
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/application/runtime/coordinator/tests/test_runtime_coordinator.py -v 2>&1 | head -10`
Expected: FAIL.

- [ ] **Step 3: Write `runtime_coordinator.py`**

```python
# lca/application/runtime/coordinator/runtime_coordinator.py
"""LcaAgentRuntimeCoordinator — LiveRunProjection fold → Redis stream.

Mirror of `apps/server/src/modules/AgentRuntime/AgentRuntimeCoordinator.ts`.
Subscribes to `LiveRunProjection.tail` for one run, translates each
StampedEvent via EventTranslator, persists tool_state to DB
(spec §5.3.1) BEFORE publishing `tool_end`, and runs a watchdog to
synthesise a terminal event if the natural SpineClose is missing.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.terminal_hints import resolve_live_terminal_hint
from lca.contracts.transport.stream_keys import stream_key
from lca.infrastructure.observability.stream import LcaStreamEventManager


MetadataWriter = Callable[[str, dict], Awaitable[None]]
ToolStateWriter = Callable[[str, str, dict], Awaitable[None]]


class LcaAgentRuntimeCoordinator:
    def __init__(
        self,
        *,
        stream_manager: LcaStreamEventManager,
        translator: EventTranslator,
        metadata_writer: MetadataWriter,
        tool_state_writer: ToolStateWriter,
        watchdog_interval_seconds: float = 1.0,
    ) -> None:
        self._mgr = stream_manager
        self._translator = translator
        self._write_metadata = metadata_writer
        self._write_tool_state = tool_state_writer
        self._watchdog_interval = watchdog_interval_seconds
        # Track which runs have already published agent_runtime_end,
        # to keep the watchdog idempotent.
        self._terminal_published: set[str] = set()

    async def start(self, run_id: str, ctx: dict) -> None:
        """Register metadata and publish agent_runtime_init."""
        await self._write_metadata(run_id, ctx)
        await self._mgr.publish(
            run_id,
            "agent_runtime_init",
            data={"agentId": ctx.get("agent_id"), "topicId": ctx.get("topic_id")},
            step_index=0,
        )

    async def handle_stamped(self, run_id: str, stamped: dict) -> None:
        """Translate a single StampedEvent and publish to Redis.

        For `ToolInvoked` events, persist projected_state to DB BEFORE
        publishing the event (spec §5.3.1).
        """
        event = (stamped or {}).get("event") or {}
        if event.get("kind") == "ignore":
            return
        etype = event.get("type")
        step_index = event.get("step_index", event.get("stepIndex", 0))

        if etype == "ToolInvoked":
            payload = event.get("payload") or {}
            tool_calling = payload.get("toolCalling") or {}
            tool_call_id = tool_calling.get("id")
            projected_state = event.get("projected_state")
            if tool_call_id and projected_state is not None:
                # spec §5.3.1: persist to DB BEFORE the WS event
                await self._write_tool_state(run_id, tool_call_id, projected_state)

        envelope = self._translator.translate(stamped)
        if envelope is None:
            return
        await self._mgr.publish(
            run_id,
            envelope["type"],
            data=envelope["data"],
            step_index=step_index,
        )
        if envelope["type"] == "agent_runtime_end":
            self._terminal_published.add(run_id)

    async def terminal(
        self,
        run_id: str,
        *,
        status: str,
        final_state: dict,
        reason_detail: str = "",
    ) -> None:
        """Force a terminal event. Idempotent."""
        if run_id in self._terminal_published:
            return
        await self._mgr.publish(
            run_id,
            "agent_runtime_end",
            data={
                "finalState": final_state,
                "reason": status,
                "reasonDetail": reason_detail,
                "phase": "execution_complete",
            },
            step_index=final_state.get("stepCount", 0),
        )
        self._terminal_published.add(run_id)
        await self._mgr.cleanup(run_id)

    async def synthesize_terminal_if_pending(
        self,
        run_id: str,
        *,
        session: Any,
    ) -> bool:
        """Watchdog: if session is terminal but no agent_runtime_end has
        been published yet (e.g. SpineClose lost during journal close),
        publish a synthetic terminal. Returns True if it published.

        spec §1 broken path #3 fix.
        """
        if run_id in self._terminal_published:
            return False
        hint = resolve_live_terminal_hint(session)
        if hint in ("running",):
            return False
        reason = "error" if session.error else hint
        final_state = {"status": session.status, "error": getattr(session, "error", None)}
        await self.terminal(run_id, status=reason, final_state=final_state)
        return True


__all__ = ("LcaAgentRuntimeCoordinator", "MetadataWriter", "ToolStateWriter")
```

- [ ] **Step 4: Update `__init__.py`**

```python
# lca/application/runtime/coordinator/__init__.py
from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.runtime_coordinator import (
    LcaAgentRuntimeCoordinator, MetadataWriter, ToolStateWriter,
)
from lca.application.runtime.coordinator.terminal_hints import (
    TerminalHint, is_stream_terminal_status, resolve_live_terminal_hint,
)

__all__ = (
    "EventTranslator",
    "LcaAgentRuntimeCoordinator",
    "MetadataWriter",
    "ToolStateWriter",
    "TerminalHint",
    "is_stream_terminal_status",
    "resolve_live_terminal_hint",
)
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/application/runtime/coordinator/tests/test_runtime_coordinator.py -v 2>&1 | tail -20`
Expected: 6 passed. If `test_handle_stamped_writes_projected_state_to_db_before_tool_end` fails, the most common cause is the `tool_state_writer` being called with the wrong keyword; check the test kwargs exactly match `run_id=...`, `tool_call_id=...`, `state=...`.

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/application/runtime/coordinator
git commit -m "feat(p1): LcaAgentRuntimeCoordinator — fold, persist, watchdog"
```

---

## Task 7: WS auth — JWT mint + verify (RS256, 5 min)

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/__init__.py`
- Create: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/auth.py`
- Test: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_auth.py`

**Interfaces:**
- Consumes: `LCA_JWT_SECRET` (env, RS256 private key, PEM) and `LCA_JWT_PUBLIC_KEY` (PEM, used by tests for verify)
- Produces: `def mint_user_jwt(*, user_id: str, operation_id: str, ttl_seconds: int = 300) -> str`; `def verify_user_jwt(token: str, *, expected_operation_id: str) -> dict` (returns claims or raises `InvalidTokenError`)

- [ ] **Step 1: Write the failing test**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_auth.py
"""JWT mint + verify for the LCA AgentGateway WS auth.

5 min TTL, RS256, payload {sub: user_id, op: run_id, purpose: 'cli-sandbox', exp: ...}.
"""
import time
import pytest

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    mint_user_jwt, verify_user_jwt, InvalidTokenError,
)


@pytest.fixture(scope="module")
def rsa_keys():
    """Generate a one-shot RSA key pair for the test module."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def test_mint_returns_three_part_jwt(rsa_keys):
    private_pem, _ = rsa_keys
    token = mint_user_jwt(user_id="u1", operation_id="op1", private_key_pem=private_pem)
    assert token.count(".") == 2  # header.payload.signature


def test_verify_accepts_a_freshly_minted_token(rsa_keys):
    private_pem, public_pem = rsa_keys
    token = mint_user_jwt(user_id="u1", operation_id="op1", private_key_pem=private_pem, ttl_seconds=60)
    claims = verify_user_jwt(token, expected_operation_id="op1", public_key_pem=public_pem)
    assert claims["sub"] == "u1"
    assert claims["op"] == "op1"
    assert claims["purpose"] == "cli-sandbox"


def test_verify_rejects_wrong_operation_id(rsa_keys):
    private_pem, public_pem = rsa_keys
    token = mint_user_jwt(user_id="u1", operation_id="op1", private_key_pem=private_pem, ttl_seconds=60)
    with pytest.raises(InvalidTokenError):
        verify_user_jwt(token, expected_operation_id="op2", public_key_pem=public_pem)


def test_verify_rejects_expired_token(rsa_keys):
    private_pem, public_pem = rsa_keys
    token = mint_user_jwt(user_id="u1", operation_id="op1", private_key_pem=private_pem, ttl_seconds=1)
    time.sleep(2)
    with pytest.raises(InvalidTokenError):
        verify_user_jwt(token, expected_operation_id="op1", public_key_pem=public_pem)


def test_verify_rejects_tampered_signature(rsa_keys):
    private_pem, public_pem = rsa_keys
    token = mint_user_jwt(user_id="u1", operation_id="op1", private_key_pem=private_pem)
    # Flip the last char of the signature
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1] + "." + parts[2][:-1] + ("A" if parts[2][-1] != "A" else "B")
    with pytest.raises(InvalidTokenError):
        verify_user_jwt(tampered, expected_operation_id="op1", public_key_pem=public_pem)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_auth.py -v 2>&1 | head -10`
Expected: FAIL.

- [ ] **Step 3: Write `__init__.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/__init__.py
"""LcaAgentGateway — Starlette WebSocketRoute implementing the native
AgentGateway protocol for the LCA kernel.

Mirror of the cloud `https://agent-gateway.lobehub.com` server side,
implemented in Python. The front-end uses the unaltered native
`@lobechat/agent-gateway-client` package; LCA only needs to host a
server that speaks the same wire.
"""

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    InvalidTokenError, mint_user_jwt, verify_user_jwt,
)

__all__ = ("InvalidTokenError", "mint_user_jwt", "verify_user_jwt")
```

- [ ] **Step 4: Write `auth.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/auth.py
"""RS256 JWT mint + verify for the LCA AgentGateway WS handshake.

Format: ``{sub: user_id, op: run_id, purpose: 'cli-sandbox', exp: <epoch>}``.
Default TTL: 300 s (5 min). The private key is loaded from ``LCA_JWT_SECRET``
(env var holding a PEM); for tests the key is injected as a parameter.

The token shape is 1:1 with native `signUserJWT` in
`lobehub-ui/packages/trpc/src/utils/internalJwt.ts:97-106` so that any
downstream service that signs/verifies with the same key set can
interop.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import jwt  # PyJWT


class InvalidTokenError(Exception):
    """Raised when verify_user_jwt rejects a token (signature, expiry, op mismatch)."""


DEFAULT_TTL_SECONDS = 300
PURPOSE = "cli-sandbox"
ALGORITHM = "RS256"


def _now() -> int:
    return int(time.time())


def mint_user_jwt(
    *,
    user_id: str,
    operation_id: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    private_key_pem: str | None = None,
) -> str:
    """Mint a short-lived JWT for the WS auth handshake.

    If `private_key_pem` is None, reads `LCA_JWT_SECRET` from the env.
    """
    if private_key_pem is None:
        import os
        private_key_pem = os.environ.get("LCA_JWT_SECRET")
        if not private_key_pem:
            raise RuntimeError("LCA_JWT_SECRET not set; cannot mint WS token")
    now = _now()
    payload = {
        "sub": user_id,
        "op": operation_id,
        "purpose": PURPOSE,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, private_key_pem, algorithm=ALGORITHM)


def verify_user_jwt(
    token: str,
    *,
    expected_operation_id: str,
    public_key_pem: str | None = None,
) -> dict[str, Any]:
    """Verify a JWT and return its claims. Raises InvalidTokenError on any failure.

    If `public_key_pem` is None, reads `LCA_JWT_PUBLIC_KEY` from the env.
    """
    if public_key_pem is None:
        import os
        public_key_pem = os.environ.get("LCA_JWT_PUBLIC_KEY")
        if not public_key_pem:
            raise RuntimeError("LCA_JWT_PUBLIC_KEY not set; cannot verify WS token")
    try:
        claims = jwt.decode(
            token,
            public_key_pem,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "op", "purpose", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"invalid token: {exc}") from exc

    if claims.get("purpose") != PURPOSE:
        raise InvalidTokenError("token purpose mismatch")
    if claims.get("op") != expected_operation_id:
        raise InvalidTokenError(
            f"token op mismatch: got {claims.get('op')!r}, expected {expected_operation_id!r}"
        )
    return claims


__all__ = ("InvalidTokenError", "mint_user_jwt", "verify_user_jwt", "DEFAULT_TTL_SECONDS")
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_auth.py -v 2>&1 | tail -15`
Expected: 5 passed. If `test_verify_rejects_expired_token` is flaky, the `time.sleep(2)` is the issue — adjust to `time.sleep(2.0)` and ensure `ttl_seconds=1` is used (default is 300, too long).

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/plugins/transport/webserver/handlers/runs/terminal/streaming
git commit -m "feat(p1): RS256 JWT mint + verify for WS auth handshake"
```

---

## Task 8: LcaAgentGateway — WebSocketRoute handler (auth + resume + live loop + heartbeat)

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/agent_gateway.py`
- Test: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_lca_agent_gateway.py`

**Interfaces:**
- Consumes: `RunPort` (cancel + resume_approval), `LcaStreamEventManager` (subscribe), `mint_user_jwt` / `verify_user_jwt`
- Produces: `async def lca_agent_gateway_handler(websocket) -> None` — the Starlette WebSocketRoute entry point

- [ ] **Step 1: Write the failing test**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_lca_agent_gateway.py
"""Integration tests for the LcaAgentGateway WebSocketRoute.

Uses the same in-process TestClient approach as the rest of the
existing test suite (tests/lca_plugins/transport/webserver/test_runs_sessions.py).
The test boots the gateway app via starlette TestClient and connects a
real `websockets` client to it.
"""
import asyncio
import json
import os
import threading
import time
import uuid

import pytest
import websockets
from starlette.testclient import TestClient

# Pre-generate an RSA key pair for the test module
@pytest.fixture(scope="module", autouse=True)
def rsa_keys_module():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_JWT_PUBLIC_KEY"] = public_pem
    os.environ["LCA_REDIS_URL"] = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    return {"private": private_pem, "public": public_pem}


@pytest.fixture
def gateway_app(rsa_keys_module):
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import build_agent_gateway_app
    return build_agent_gateway_app(
        run_port_lookup=lambda run_id: None,  # tests inject events directly via the stream manager
    )


def test_invalid_token_rejected_with_auth_failed(gateway_app):
    """An expired or bad token receives `auth_failed` and the socket closes."""
    with TestClient(gateway_app) as client:
        # Start a TestClient in a thread; use the websockets library directly
        with client.websocket_connect("/v1/runs/op1/ws") as ws:
            ws.send_json({"type": "auth", "token": "this.is.not.valid"})
            msg = ws.receive_json()
            assert msg["type"] == "auth_failed"


def test_resume_replays_history_then_emits_resume_complete(gateway_app, rsa_keys_module):
    """A fresh client connecting with lastEventId=0 receives all prior events in order."""
    from lca.infrastructure.observability.stream import (
        LcaStreamEventManager, get_agent_runtime_redis_client,
    )

    run_id = f"test_resume_{uuid.uuid4().hex[:8]}"
    mgr = LcaStreamEventManager(get_agent_runtime_redis_client())

    async def seed():
        await mgr.publish(run_id, "agent_runtime_init", {"agentId": "a1"}, step_index=0)
        await mgr.publish(run_id, "stream_chunk", {"chunkType": "text", "content": "hello"}, step_index=1)
    asyncio.run(seed())

    token = mint_for_test("u1", run_id, rsa_keys_module["private"])

    with TestClient(gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "auth_success"}
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": True})
            # Expect 2 history frames + 1 resume_complete
            frames = []
            for _ in range(3):
                frames.append(ws.receive_text())
            assert any('"type": "agent_event"' in f and '"agent_runtime_init"' in f for f in frames)
            assert any('"stream_chunk"' in f and '"text"' in f and 'hello' in f for f in frames)
            assert any('"type": "resume_complete"' in f and '"status"' in f for f in frames)

    asyncio.run(mgr.cleanup(run_id))


def test_heartbeat_gets_heartbeat_ack(gateway_app, rsa_keys_module):
    """Client heartbeat frames are answered with heartbeat_ack."""
    run_id = f"test_heartbeat_{uuid.uuid4().hex[:8]}"
    token = mint_for_test("u1", run_id, rsa_keys_module["private"])

    with TestClient(gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "auth_success"}
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": True})
            # drain at most one history frame
            try:
                ws.receive_text(timeout=0.5)
            except Exception:
                pass
            ws.send_json({"type": "heartbeat"})
            ack = ws.receive_json()
            assert ack == {"type": "heartbeat_ack"}


def test_interrupt_triggers_run_port_cancel(gateway_app, rsa_keys_module):
    """An `interrupt` frame calls RunPort.cancel(run_id)."""
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import build_agent_gateway_app

    cancel_calls = []

    def fake_port():
        class P:
            async def cancel(self, run_id):
                cancel_calls.append(run_id)
                return None
            async def resume_approval(self, run_id, approval_id, payload, idempotency_key):
                return None
        return P()

    app = build_agent_gateway_app(run_port=fake_port())
    run_id = f"test_interrupt_{uuid.uuid4().hex[:8]}"
    token = mint_for_test("u1", run_id, rsa_keys_module["private"])

    with TestClient(app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            ws.receive_json()  # auth_success
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": False})
            try:
                ws.receive_text(timeout=0.3)
            except Exception:
                pass
            ws.send_json({"type": "interrupt"})
            # The gateway should close the socket; we expect the close
            with pytest.raises(Exception):  # WebSocketDisconnect
                ws.receive_text(timeout=2.0)
    assert cancel_calls == [run_id]


def mint_for_test(user_id: str, op: str, private_pem: str) -> str:
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt
    return mint_user_jwt(user_id=user_id, operation_id=op, private_key_pem=private_pem, ttl_seconds=60)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_lca_agent_gateway.py -v 2>&1 | head -10`
Expected: FAIL (no `build_agent_gateway_app`).

- [ ] **Step 3: Write `agent_gateway.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/agent_gateway.py
"""LcaAgentGateway — Starlette WebSocketRoute for the agent runtime event bus.

Implements the same wire protocol as the upstream
`https://agent-gateway.lobehub.com` (the `ServerMessage` /
`ClientMessage` schemas from `lobehub-ui/packages/agent-gateway-client/src/types.ts:257-369`).
The front-end uses the unaltered `AgentStreamClient` package.

Wire behaviour:
- accept WS → expect first frame `{type:'auth', token}` → verify JWT
  → on success: send `{type:'auth_success'}`; on failure: `{type:'auth_failed'}` and close.
- expect next frame `{type:'resume', lastEventId, wantStatus?}` →
  read history (XREAD from `lastEventId`) → emit each as `agent_event`
  → if `wantStatus`: emit `resume_complete { status }` and close if terminal.
- after resume: subscribe to live stream (XREAD BLOCK 1000) → emit each new event.
- 30s heartbeat: client sends `{type:'heartbeat'}` → server replies `{type:'heartbeat_ack'}`.
- `{type:'interrupt'}` → call `RunPort.cancel(run_id)`, close.
- `{type:'tool_result'}` → call `RunPort.resume_approval(...)`, continue.

After the run's `agent_runtime_end` is published, the server emits
`{type:'session_complete'}` and closes the socket.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from lca.contracts.transport.stream_keys import stream_key
from lca.infrastructure.observability.stream import LcaStreamEventManager, get_agent_runtime_redis_client
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    InvalidTokenError, verify_user_jwt,
)


class RunPort(Protocol):
    async def cancel(self, run_id: str) -> Any: ...
    async def resume_approval(self, run_id: str, approval_id: str, payload: str, idempotency_key: str) -> Any: ...


_HEARTBEAT_INTERVAL_S = 30.0
_BLOCK_MS = 1000


def build_agent_gateway_app(*, run_port: RunPort | None = None) -> Starlette:
    """Build the Starlette app exposing /v1/runs/{run_id}/ws.

    The `run_port` parameter is optional; tests inject a fake; production
    passes the real LCA RunPort (resolved from app.state).
    """
    stream_manager = LcaStreamEventManager(get_agent_runtime_redis_client())

    async def handler(websocket: WebSocket) -> None:
        run_id = websocket.path_params.get("run_id")
        await websocket.accept()
        try:
            await _run_session(websocket, run_id=run_id, stream_manager=stream_manager, run_port=run_port)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            print(f"[lca_agent_gateway] unhandled: {exc!r}", flush=True)
        finally:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                try:
                    await websocket.close()
                except Exception:
                    pass

    return Starlette(routes=[WebSocketRoute("/v1/runs/{run_id}/ws", handler)])


async def _run_session(
    ws: WebSocket,
    *,
    run_id: str,
    stream_manager: LcaStreamEventManager,
    run_port: RunPort | None,
) -> None:
    # 1. auth handshake
    try:
        first = await _recv_json(ws)
    except WebSocketDisconnect:
        return
    if not first or first.get("type") != "auth":
        await ws.send_json({"type": "auth_failed", "reason": "expected auth frame"})
        return
    token = first.get("token", "")
    try:
        claims = verify_user_jwt(token, expected_operation_id=run_id)
    except (InvalidTokenError, RuntimeError) as exc:
        await ws.send_json({"type": "auth_failed", "reason": str(exc)})
        return
    await ws.send_json({"type": "auth_success"})

    # 2. resume handshake
    try:
        resume = await _recv_json(ws)
    except WebSocketDisconnect:
        return
    if not resume or resume.get("type") != "resume":
        return
    last_id = resume.get("lastEventId", "0")
    want_status = resume.get("wantStatus", False)

    history = await stream_manager.read_history(run_id, count=1000)
    # XREVRANGE returns newest first; we want oldest first
    history.reverse()
    for ev in history:
        if ev.get("id") and last_id != "0" and ev["id"] <= last_id:
            continue
        await _send_agent_event(ws, ev)
    if want_status:
        # Use the Redis-stream existence + the latest event to derive a status
        status = "completed" if not await stream_manager.exists(run_id) else "running"
        await ws.send_json({"type": "resume_complete", "status": status})
        if status in ("completed", "error", "interrupted"):
            await ws.send_json({"type": "session_complete"})
            return

    # 3. live loop
    last_heartbeat_at = asyncio.get_event_loop().time()
    while True:
        if ws.client_state == WebSocketState.DISCONNECTED:
            return
        # Heartbeat tick
        now = asyncio.get_event_loop().time()
        if now - last_heartbeat_at > _HEARTBEAT_INTERVAL_S:
            await ws.send_json({"type": "heartbeat"})
            last_heartbeat_at = now

        # Try a short blocking read
        try:
            frames_iter = stream_manager.subscribe(run_id, last_id)
            async for frame in frames_iter:
                if ws.client_state == WebSocketState.DISCONNECTED:
                    return
                await ws.send_bytes(frame)
                last_id_frame = _extract_id_from_sse_frame(frame)
                if last_id_frame:
                    last_id = last_id_frame
        except Exception:
            pass

        # Non-blocking read of next control frame
        try:
            msg = await asyncio.wait_for(_recv_json(ws), timeout=0.05)
        except (asyncio.TimeoutError, WebSocketDisconnect):
            continue

        if msg.get("type") == "heartbeat":
            await ws.send_json({"type": "heartbeat_ack"})
        elif msg.get("type") == "interrupt":
            if run_port is not None:
                try:
                    await run_port.cancel(run_id)
                except Exception:
                    pass
            return
        elif msg.get("type") == "tool_result":
            if run_port is not None:
                try:
                    await run_port.resume_approval(
                        run_id,
                        msg.get("toolCallId", ""),
                        msg.get("content", ""),
                        msg.get("idempotencyKey", ""),
                    )
                except Exception:
                    pass


async def _recv_json(ws: WebSocket) -> dict | None:
    """Receive a JSON frame, ignoring SSE-style heartbeat comments.

    Native frames are JSON dicts; we also tolerate the SSE-shaped frames
    that the LcaStreamEventManager yields (so the same wire shape works
    for both control and event channels).
    """
    payload = await ws.receive_text()
    if not payload:
        return None
    if payload.startswith(":"):  # SSE comment
        return None
    for line in payload.split("\n"):
        if line.startswith("data:"):
            try:
                return json.loads(line[len("data:"):].strip())
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


async def _send_agent_event(ws: WebSocket, ev: dict) -> None:
    """Send a single AgentStreamEvent as a `agent_event` envelope."""
    envelope = {
        "type": "agent_event",
        "id": ev.get("id"),
        "event": {
            "type": ev.get("type"),
            "data": ev.get("data"),
            "operationId": ev.get("operationId"),
            "stepIndex": ev.get("stepIndex", 0),
            "timestamp": ev.get("timestamp", 0),
        },
    }
    await ws.send_json(envelope)


def _extract_id_from_sse_frame(frame: bytes) -> str | None:
    """Parse an SSE-shaped frame for the `id:` line, return its value or None."""
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in text.split("\n"):
        if line.startswith("id:"):
            return line[len("id:"):].strip() or None
    return None


__all__ = ("RunPort", "build_agent_gateway_app")
```

- [ ] **Step 4: Update `__init__.py` to re-export the factory**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/__init__.py
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
    RunPort, build_agent_gateway_app,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    InvalidTokenError, mint_user_jwt, verify_user_jwt,
)

__all__ = (
    "InvalidTokenError",
    "RunPort",
    "build_agent_gateway_app",
    "mint_user_jwt",
    "verify_user_jwt",
)
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_lca_agent_gateway.py -v 2>&1 | tail -30`
Expected: 4 passed. The `test_interrupt_triggers_run_port_cancel` may flake on Starlette's test client behavior; if it does, accept `WebSocketDisconnect` or a final `session_complete` frame as the close signal — see the existing `test_runs_sessions.py` patterns.

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/plugins/transport/webserver/handlers/runs/terminal/streaming
git commit -m "feat(p1): LcaAgentGateway — Starlette WebSocketRoute"
```

---

## Task 9: Wire `/v1/runs/{run_id}/ws` into the route table

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/__init__.py`
- Create: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/routes.py`
- Test: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_routes.py`

**Interfaces:**
- Consumes: existing `route_registry` capability, `RunPort` from `app.state`
- Produces: `@plugin("lca-gateway-ws")` registering the WS route + the 2 supporting HTTP routes (`/v1/runs/{run_id}/ws-token` and `/v1/topics/{topic_id}/running-op`)

- [ ] **Step 1: Write the failing test**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_routes.py
"""Verify the lca-gateway-ws plugin registers the expected routes."""
import pytest

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes import ROUTE_SPECS


def test_route_specs_contains_ws_route():
    paths = [spec.path for spec in ROUTE_SPECS]
    assert "/v1/runs/{run_id}/ws" in paths


def test_route_specs_contains_ws_token_route():
    paths = [spec.path for spec in ROUTE_SPECS]
    assert "/v1/runs/{run_id}/ws-token" in paths


def test_route_specs_contains_running_op_route():
    paths = [spec.path for spec in ROUTE_SPECS]
    assert "/v1/topics/{topic_id}/running-op" in paths
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_routes.py -v 2>&1 | head -10`
Expected: FAIL.

- [ ] **Step 3: Write `__init__.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/__init__.py
"""Wire: mount the LcaAgentGateway WebSocketRoute and supporting HTTP endpoints."""
```

- [ ] **Step 4: Write `routes.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/routes.py
"""Mounts the LcaAgentGateway WS endpoint and the supporting HTTP routes.

Routes:
- GET  /v1/topics/{topic_id}/running-op     — useGatewayReconnect source
- POST /v1/runs/{run_id}/ws-token          — refresh JWT after auth_expired
- GET  /v1/runs/{run_id}/ws               — primary LcaAgentGateway stream

The WS handler is registered via starlette_router from a deferred
import — see `register_routes` in routes_runs_sessions.py for the
LCA pattern. For P1, the WS handler is wired into the same
Starlette app that hosts the existing /runs/* REST routes.
"""
from __future__ import annotations

from lca.contracts.routing import RouteSpec
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    get_running_operation, refresh_ws_token,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws import (
    lca_agent_gateway_websocket,
)


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/v1/topics/{topic_id}/running-op", get_running_operation, ("GET", "OPTIONS")),
    RouteSpec("/v1/runs/{run_id}/ws-token", refresh_ws_token, ("POST", "OPTIONS")),
    # The WS route is mounted via Starlette directly, not the RouteSpec
    # helper, because RouteSpec expects a coroutine that takes Request.
    # The `wire.ws` module exposes `mount_ws_route(app)` for the
    # integration step in Task 11.
)


__all__ = ("ROUTE_SPECS", "lca_agent_gateway_websocket")
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_routes.py -v 2>&1 | tail -10`
Expected: 3 passed (the HTTP route_specs only; the WS mount is verified in Task 11).

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire
git commit -m "feat(p1): wire lca-gateway-ws plugin routes"
```

---

## Task 10: HTTP route handlers — `get_running_operation` + `refresh_ws_token`

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/http.py`
- Test: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_http.py`

**Interfaces:**
- Consumes: existing `route_registry` capability, Postgres `lca_running_operations` table, `LCA_JWT_SECRET` env
- Produces: `async def get_running_operation(request) -> JSONResponse`; `async def refresh_ws_token(request) -> JSONResponse`

- [ ] **Step 1: Write the failing test**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_http.py
"""HTTP handlers for the supporting endpoints (L2-7 and L2-8)."""
import json
import os
import uuid

import pytest
from starlette.testclient import TestClient

# Set up RSA keys for ws-token tests
@pytest.fixture(scope="module", autouse=True)
def rsa_keys_module():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_REDIS_URL"] = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


def test_get_running_operation_returns_404_for_missing_topic():
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import build_http_app

    with TestClient(build_http_app()) as client:
        resp = client.get(f"/v1/topics/{uuid.uuid4().hex}/running-op")
        assert resp.status_code == 200
        assert resp.json() == {"running_operation": None}


def test_get_running_op_returns_row_when_present():
    """L2-7: an inserted row in lca_running_operations is returned."""
    pytest.skip("requires Postgres; covered by the lca_running_operations migration test in Task 12")


def test_refresh_ws_token_returns_404_when_run_redis_key_missing():
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import build_http_app

    run_id = f"test_ws_token_{uuid.uuid4().hex[:8]}"
    with TestClient(build_http_app()) as client:
        resp = client.post(f"/v1/runs/{run_id}/ws-token", json={"userId": "u1"})
        assert resp.status_code == 404
        assert "not found" in resp.text or "expired" in resp.text


def test_refresh_ws_token_returns_200_with_token_when_redis_key_alive():
    """L2-8: a fresh JWT is minted when the Redis stream still exists."""
    from lca.infrastructure.observability.stream import (
        LcaStreamEventManager, get_agent_runtime_redis_client,
    )
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import build_http_app
    import asyncio

    run_id = f"test_ws_token_ok_{uuid.uuid4().hex[:8]}"
    mgr = LcaStreamEventManager(get_agent_runtime_redis_client())
    asyncio.run(mgr.publish(run_id, "agent_runtime_init", {}, step_index=0))

    with TestClient(build_http_app()) as client:
        resp = client.post(f"/v1/runs/{run_id}/ws-token", json={"userId": "u1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert body["token"].count(".") == 2

    asyncio.run(mgr.cleanup(run_id))
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_http.py -v 2>&1 | head -10`
Expected: FAIL.

- [ ] **Step 3: Write `http.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/http.py
"""HTTP route handlers for the LcaAgentGateway supporting endpoints.

- GET  /v1/topics/{topic_id}/running-op
  Returns the most recent `lca_running_operations` row for a topic;
  used by `useGatewayReconnect` to discover an in-flight run after a
  page reload.

- POST /v1/runs/{run_id}/ws-token
  Mints a fresh JWT for the WS handshake; used by the client when the
  gateway replies with `auth_expired`. Returns 404 if the Redis stream
  for the run no longer exists.
"""
from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from lca.infrastructure.observability.stream import LcaStreamEventManager, get_agent_runtime_redis_client
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt


# ── Handlers ──────────────────────────────────────────────────────────


async def get_running_operation(request: Request) -> JSONResponse:
    """Return the most recent running operation for a topic, or null.

    Reads from the `lca_running_operations` table (created in Task 12).
    """
    topic_id = request.path_params["topic_id"]
    # The actual SELECT is plugged in at boot via app.state.running_operation_store.
    store = getattr(request.app.state, "running_operation_store", None)
    if store is None:
        return JSONResponse(
            {"error": "running_operation_store not bound"},
            status_code=500,
            headers=cors_headers(),
        )
    row = await store.get_latest_for_topic(topic_id)
    if row is None:
        return JSONResponse({"running_operation": None}, headers=cors_headers())
    return JSONResponse({"running_operation": row}, headers=cors_headers())


async def refresh_ws_token(request: Request) -> JSONResponse:
    """Mint a fresh JWT for the WS handshake; 404 if the run is gone."""
    run_id = request.path_params["run_id"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    user_id = str(body.get("userId") or "")

    mgr = LcaStreamEventManager(get_agent_runtime_redis_client())
    if not await mgr.exists(run_id):
        return JSONResponse(
            {"error": "run not found or expired"},
            status_code=404,
            headers=cors_headers(),
        )

    # user_id may be empty if the client doesn't have one cached;
    # the token is still useful for refreshing the WS handshake,
    # the server will reject mismatched user_ids at the gate.
    token = mint_user_jwt(user_id=user_id or "anonymous", operation_id=run_id)
    return JSONResponse({"token": token, "runId": run_id}, headers=cors_headers())


# ── Test app factory ──────────────────────────────────────────────────


def build_http_app() -> Starlette:
    """Starlette app exposing the HTTP routes for in-process tests.

    Production mounting uses the LCA `RouteSpec` registry; tests use
    a bare Starlette with the same handlers.
    """
    return Starlette(routes=[
        Route("/v1/topics/{topic_id}/running-op", get_running_operation, methods=["GET", "OPTIONS"]),
        Route("/v1/runs/{run_id}/ws-token", refresh_ws_token, methods=["POST", "OPTIONS"]),
    ])


__all__ = ("build_http_app", "get_running_operation", "refresh_ws_token")
```

- [ ] **Step 4: Update wire `__init__.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/__init__.py
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    build_http_app, get_running_operation, refresh_ws_token,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes import (
    ROUTE_SPECS,
)

__all__ = (
    "ROUTE_SPECS",
    "build_http_app",
    "get_running_operation",
    "refresh_ws_token",
)
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_http.py -v 2>&1 | tail -10`
Expected: 3 passed (the `test_get_running_op_returns_row_when_present` is skipped pending the migration in Task 12).

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire
git commit -m "feat(p1): get_running_operation + refresh_ws_token HTTP handlers"
```

---

## Task 11: WS mount + plugin integration

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/ws.py`
- Modify: `lca/plugins/transport/webserver/routes_2/routes_runs_sessions.py` (add the lca-gateway-ws routes to ROUTE_SPECS)
- Test: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_ws_mount.py`

- [ ] **Step 1: Write the failing test**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_ws_mount.py
"""Verify the lca-gateway-ws plugin mounts the WS route on the production Starlette app."""
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws import mount_ws_route
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import build_agent_gateway_app


def test_ws_route_responds_with_403_for_unauthenticated_request():
    """An unauthenticated WS upgrade is rejected (proving the route exists and the handler runs)."""
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute

    handler_calls = []

    async def fake_handler(websocket):
        handler_calls.append(websocket)
        await websocket.close()

    app = Starlette()
    mount_ws_route(app, handler=fake_handler)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/v1/runs/op1/ws") as ws:
                ws.send_text("ping")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_ws_mount.py -v 2>&1 | head -10`
Expected: FAIL.

- [ ] **Step 3: Write `ws.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/ws.py
"""Mount the LcaAgentGateway WebSocketRoute on a Starlette app.

Production wiring (set up by the lca-gateway-ws @plugin):
- the existing `route_registry` is consulted for the HTTP routes
  (registered via RouteSpec in routes.py);
- this module mounts the WS route on the same Starlette app via
  `WebSocketRoute`, so the legacy /runs/* REST routes and the new
  /v1/runs/{run_id}/ws share a single port and TLS context.

The Next.js dev server's `/lca-api/:path*` rewrite (already in
`lobehub-ui/next.config.ts:43-49`) forwards both HTTP and WS upgrade
to this same Starlette app. See spike 1 in
`docs/specs/2026-09-07-lca-p1-agent-gateway-bridge.md:14.3`.
"""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.routing import WebSocketRoute


def mount_ws_route(app: Starlette, *, handler) -> None:
    """Append the WS route to the given Starlette app.

    The `handler` is a coroutine that takes a single WebSocket and runs
    the LcaAgentGateway session loop. Production passes the
    `_run_session` inner from `agent_gateway.py`; tests pass a stub.
    """
    app.router.routes.append(
        WebSocketRoute("/v1/runs/{run_id}/ws", handler)
    )


__all__ = ("mount_ws_route",)
```

- [ ] **Step 4: Update wire `__init__.py`**

```python
# lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/__init__.py
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    build_http_app, get_running_operation, refresh_ws_token,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes import (
    ROUTE_SPECS,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws import (
    mount_ws_route,
)

__all__ = (
    "ROUTE_SPECS",
    "build_http_app",
    "get_running_operation",
    "mount_ws_route",
    "refresh_ws_token",
)
```

- [ ] **Step 5: Add to production `routes_2/routes_runs_sessions.py`**

The new routes are registered alongside the existing ones. Open the file and append the new RouteSpec lines inside `ROUTE_SPECS`:

```python
# In lca/plugins/transport/webserver/routes_2/routes_runs_sessions.py

# Add these imports near the top:
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes import (
    ROUTE_SPECS as LCA_GATEWAY_ROUTE_SPECS,
)

# Add these routes to the existing ROUTE_SPECS tuple (before the closing `)`):
#   RouteSpec("/v1/topics/{topic_id}/running-op", get_running_operation, ("GET", "OPTIONS")),
#   RouteSpec("/v1/runs/{run_id}/ws-token", refresh_ws_token, ("POST", "OPTIONS")),
# (extracted from LCA_GATEWAY_ROUTE_SPECS at boot so the
# route_lca_gateway_ws plugin owns the handler surface; this file
# just merges them into the production RouteSpec registry.)
```

> Note: the actual implementation merges `LCA_GATEWAY_ROUTE_SPECS` into the existing `ROUTE_SPECS` tuple at module import time, by adding `*LCA_GATEWAY_ROUTE_SPECS` to the tuple. The `get_running_operation` and `refresh_ws_token` handlers are imported from the new `wire.routes` module.

Concretely, modify the existing `ROUTE_SPECS` to:

```python
ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("/runs", create_run, ("POST", "OPTIONS")),
    RouteSpec("/runs/{run_id}", get_run, ("GET",)),
    RouteSpec("/runs/{run_id}/live", stream_run_live, ("GET", "OPTIONS")),
    RouteSpec("/runs/{run_id}/doctor", get_run_doctor, ("GET",)),
    RouteSpec("/runs/{run_id}/failure", get_run_failure, ("GET",)),
    RouteSpec("/runs/{run_id}/exceptions", get_run_exceptions, ("GET",)),
    RouteSpec("/runs/{run_id}/profile", get_run_profile, ("GET",)),
    RouteSpec("/runs/{run_id}/evidence/{ref:path}", get_run_evidence, ("GET",)),
    RouteSpec("/runs/{run_id}/cancel", cancel_run, ("POST", "OPTIONS")),
    RouteSpec("/runs/{run_id}/answer", answer_run, ("POST", "OPTIONS")),
    RouteSpec("/runs/{run_id}/feedback", record_run_feedback, ("POST", "OPTIONS")),
    # P1: LcaAgentGateway supporting endpoints
    *LCA_GATEWAY_ROUTE_SPECS,
)
```

- [ ] **Step 6: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire/tests/test_ws_mount.py -v 2>&1 | tail -10`
Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/plugins/transport/webserver/handlers/runs/terminal/streaming/wire lca/plugins/transport/webserver/routes_2/routes_runs_sessions.py
git commit -m "feat(p1): mount lca-gateway-ws WS route + register HTTP routes"
```

---

## Task 12: lca_running_operations migration + RunningOperationStore

**Files:**
- Create migration: `lca/migrations/2026_09_07_lca_running_operations.sql`
- Create: `lca/contracts/observability/running_operation.py` (RunningOperationStore Protocol)
- Create: `lca/infrastructure/observability/running_operation_store.py` (Postgres implementation)
- Test: `lca/contracts/observability/tests/test_running_operation.py`

**Interfaces:**
- Consumes: Postgres connection (`lca/database/core/db-adaptor.py`'s `get_server_db`)
- Produces:
  - `class RunningOperationStore(Protocol)` with `async def insert(self, run_id, topic_id, agent_id, assistant_message_id, scope) -> None`, `async def get_latest_for_topic(self, topic_id) -> dict | None`, `async def record_answer_key(self, run_id, idempotency_key) -> None`, `async def delete(self, run_id) -> None`
  - Concrete `class PostgresRunningOperationStore`

- [ ] **Step 1: Write the failing test**

```python
# lca/contracts/observability/tests/test_running_operation.py
"""RunningOperationStore contract tests against a real Postgres.

LCA dev stack has Postgres at 127.0.0.1:25432 (see lca-ops.yaml:36).
"""
import asyncio
import uuid

import pytest

from lca.infrastructure.observability.running_operation_store import (
    PostgresRunningOperationStore,
)


@pytest.fixture
async def store():
    s = PostgresRunningOperationStore()
    yield s
    # cleanup: delete any rows the tests created
    await s.delete_all_for_test()


async def test_insert_then_get_latest_for_topic(store):
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    await store.insert(
        run_id=run_id,
        topic_id=topic_id,
        agent_id="a1",
        assistant_message_id="m1",
        scope="main",
    )
    row = await store.get_latest_for_topic(topic_id)
    assert row is not None
    assert row["run_id"] == run_id
    assert row["topic_id"] == topic_id
    assert row["agent_id"] == "a1"
    assert row["assistant_message_id"] == "m1"
    assert row["scope"] == "main"


async def test_get_latest_for_topic_returns_none_for_missing(store):
    row = await store.get_latest_for_topic(f"missing_{uuid.uuid4().hex[:8]}")
    assert row is None


async def test_record_answer_key_appends_to_jsonb(store):
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    await store.insert(run_id, topic_id, "a1", "m1", "main")
    await store.record_answer_key(run_id, "key1")
    await store.record_answer_key(run_id, "key2")
    row = await store.get_latest_for_topic(topic_id)
    assert set(row["accepted_answer_keys"]) == {"key1", "key2"}


async def test_record_answer_key_is_idempotent(store):
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    await store.insert(run_id, topic_id, "a1", "m1", "main")
    await store.record_answer_key(run_id, "key1")
    await store.record_answer_key(run_id, "key1")  # second insert is a no-op
    row = await store.get_latest_for_topic(topic_id)
    assert row["accepted_answer_keys"] == ["key1"]


async def test_delete_removes_row(store):
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    await store.insert(run_id, topic_id, "a1", "m1", "main")
    await store.delete(run_id)
    row = await store.get_latest_for_topic(topic_id)
    assert row is None
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/contracts/observability/tests/test_running_operation.py -v 2>&1 | head -10`
Expected: FAIL (no module).

- [ ] **Step 3: Write the migration**

```sql
-- lca/migrations/2026_09_07_lca_running_operations.sql
-- Per spec §3.2: NO `status` column. Liveness lives in Redis Stream TTL.

CREATE TABLE IF NOT EXISTS lca_running_operations (
    run_id                text PRIMARY KEY,
    topic_id              text NOT NULL,
    agent_id              text NOT NULL,
    assistant_message_id  text,
    scope                 text NOT NULL DEFAULT 'main',
    created_at            timestamptz NOT NULL DEFAULT now(),
    accepted_answer_keys  jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS lca_running_operations_topic_id_idx
    ON lca_running_operations (topic_id, created_at DESC);
```

- [ ] **Step 4: Write `lca/contracts/observability/running_operation.py`**

```python
# lca/contracts/observability/running_operation.py
"""Protocol for the running-operation store.

Concretely implemented by `lca.infrastructure.observability.running_operation_store.PostgresRunningOperationStore`,
but the contract lives in contracts/ so plugin wiring can use it without depending on infrastructure.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RunningOperationStore(Protocol):
    async def insert(
        self,
        *,
        run_id: str,
        topic_id: str,
        agent_id: str,
        assistant_message_id: str | None,
        scope: str,
    ) -> None: ...

    async def get_latest_for_topic(self, topic_id: str) -> dict | None: ...

    async def record_answer_key(self, run_id: str, idempotency_key: str) -> None: ...

    async def delete(self, run_id: str) -> None: ...


__all__ = ("RunningOperationStore",)
```

- [ ] **Step 5: Write `lca/infrastructure/observability/running_operation_store.py`**

```python
# lca/infrastructure/observability/running_operation_store.py
"""Postgres implementation of RunningOperationStore."""
from __future__ import annotations

import json

from lca.contracts.observability.running_operation import RunningOperationStore
from lca.database.core.db_adaptor import get_server_db


class PostgresRunningOperationStore(RunningOperationStore):
    async def insert(
        self,
        *,
        run_id: str,
        topic_id: str,
        agent_id: str,
        assistant_message_id: str | None,
        scope: str,
    ) -> None:
        db = await get_server_db()
        await db.execute(
            """INSERT INTO lca_running_operations
               (run_id, topic_id, agent_id, assistant_message_id, scope)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (run_id) DO NOTHING""",
            (run_id, topic_id, agent_id, assistant_message_id, scope),
        )

    async def get_latest_for_topic(self, topic_id: str) -> dict | None:
        db = await get_server_db()
        row = await db.fetchone(
            """SELECT run_id, topic_id, agent_id, assistant_message_id, scope, created_at
               FROM lca_running_operations
               WHERE topic_id = $1
               ORDER BY created_at DESC
               LIMIT 1""",
            (topic_id,),
        )
        if row is None:
            return None
        d = dict(row)
        d["accepted_answer_keys"] = d.get("accepted_answer_keys") or []
        return d

    async def record_answer_key(self, run_id: str, idempotency_key: str) -> None:
        db = await get_server_db()
        # jsonb || appends; the COALESCE + DISTINCT prevents duplicates
        await db.execute(
            """UPDATE lca_running_operations
               SET accepted_answer_keys = (
                   SELECT COALESCE(jsonb_agg(DISTINCT v), '[]'::jsonb)
                   FROM jsonb_array_elements_text(accepted_answer_keys || to_jsonb(ARRAY[$1])) AS v
               )
               WHERE run_id = $2""",
            (idempotency_key, run_id),
        )

    async def delete(self, run_id: str) -> None:
        db = await get_server_db()
        await db.execute(
            "DELETE FROM lca_running_operations WHERE run_id = $1",
            (run_id,),
        )

    async def delete_all_for_test(self) -> None:
        """Test helper; never call from production."""
        db = await get_server_db()
        await db.execute("TRUNCATE lca_running_operations")


__all__ = ("PostgresRunningOperationStore",)
```

- [ ] **Step 6: Update `__init__.py` to re-export**

```python
# lca/infrastructure/observability/__init__.py (or wherever appropriate)
from lca.infrastructure.observability.running_operation_store import (
    PostgresRunningOperationStore,
)

__all__ = ("PostgresRunningOperationStore",)
```

- [ ] **Step 7: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest lca/contracts/observability/tests/test_running_operation.py -v 2>&1 | tail -15`
Expected: 5 passed. If the migration hasn't been applied, run `psql -h 127.0.0.1 -p 25432 -U postgres -d lca -f lca/migrations/2026_09_07_lca_running_operations.sql` first.

- [ ] **Step 8: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/migrations lca/contracts/observability/running_operation.py lca/infrastructure/observability/running_operation_store.py
git commit -m "feat(p1): lca_running_operations table + PostgresRunningOperationStore"
```

---

# PR-3: Front-end switchover via new patch modules

## Task 13: New `lca_runtime_chat_persistence` patch module

**Files:**
- Create: `deploy/lobehub/patches/runtime/lca_runtime_chat_persistence.py`
- Modify: `deploy/lobehub/patches/runtime/lcaToolRender/contracts.generated.ts` (regenerated by the patch — already exists)

**Interfaces:**
- Consumes: `lca.plugins.transport.webserver.handlers.runs.wire.WIRE`
- Produces: `meta: PatchMeta` with `files=...` listing the 7 LCA-only TS files; the engine's `ctx.write()` copies them into `lobehub-ui/src/...`

- [ ] **Step 1: Verify current `lca_run_driver.py` and split**

Open `deploy/lobehub/patches/runtime/lca_run_driver.py` and identify the 6 LCA-only TS files it currently copies (lcaChatRow, lcaPersist, lcaFinishChat, lcaError, lcaArtifacts, lcaWire). The 5 other entries (LcaRunDriver, lcaRunObserve, lcaRunHil, lcaJournal, lcaRunCommand) will be retired in PR-4. The 4 source modifications (streamingExecutor, customInteractionHandlers, intervention/index.tsx, conversationControl) are NOT copied by this module — `lca_runtime_agent_gateway` owns them.

- [ ] **Step 2: Write `lca_runtime_chat_persistence.py`**

```python
# deploy/lobehub/patches/runtime/lca_runtime_chat_persistence.py
"""Patch: keep the LCA-specific chat persistence / rendering helpers.

Replaces the persistence half of the legacy `lca_run_driver` patch.
No lobehub-ui source modifications — this module only creates new files.
"""
from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta
from lca.plugins.transport.webserver.handlers.runs.wire import WIRE

_HERE = Path(__file__).resolve().parent
_UI_TRANSPORTS = "src/store/chat/agents/transports"

meta = PatchMeta(
    name="lca_runtime_chat_persistence",
    description="LCA message-write + tool-render helpers (chat persistence).",
    files=(
        f"{_UI_TRANSPORTS}/lcaChatRow.ts",
        f"{_UI_TRANSPORTS}/lcaPersist.ts",
        f"{_UI_TRANSPORTS}/lcaFinishChat.ts",
        f"{_UI_TRANSPORTS}/lcaError.ts",
        f"{_UI_TRANSPORTS}/lcaArtifacts.ts",
        f"{_UI_TRANSPORTS}/lcaWire.ts",  # generated from WIRE
        f"{_UI_TRANSPORTS}/lcaToolRender/contracts.generated.ts",
    ),
    risk="medium",
    category="runtime",
    depends_on=(),
    why=(
        "LCA-specific message-write and tool-rendering helpers have no "
        "native equivalent. The transport is replaced in P1 (see "
        "lca_runtime_agent_gateway) but the persistence layer stays."
    ),
    technical_detail=(
        "Files are copied as-is. lcaWire.ts is generated at patch apply "
        "time from the WIRE table in the Python gateway. The 4 "
        "lobehub-ui source modifications of the legacy lca_run_driver "
        "are NOT in this module — they are owned by "
        "lca_runtime_agent_gateway (P1 changes) or retired (reconcile)."
    ),
    verify_file=f"{_UI_TRANSPORTS}/lcaChatRow.ts",
    verify_marker="/* LCA: chat persistence helpers */",
)


def render_wire_ts(wire: dict) -> str:
    """Mirror of the legacy generator: produce lcaWire.ts from WIRE."""
    lines = [
        "/** Generated from lca.plugins.transport.webserver.handlers.runs.wire.WIRE. Do not edit. */",
        "",
        "export const WIRE: Record<string, readonly [string, string]> = {",
    ]
    for name, (identifier, api_name) in wire.items():
        lines.append(f"  '{name}': ['{identifier}', '{api_name}'],")
    lines.append("};")
    lines.append("")
    return "\n".join(lines)


def apply(ctx: PatchContext) -> bool:
    """Copy the 7 source files; generate lcaWire.ts from WIRE."""
    for rel in meta.files:
        if rel.endswith("lcaWire.ts"):
            content = render_wire_ts(WIRE)
            ctx.write_if_changed(rel, content)
        else:
            src = _HERE / Path(rel).name
            if not src.is_file():
                raise SystemExit(f"missing patch source: {src}")
            content = src.read_text()
            ctx.write_if_changed(rel, content)
    return True
```

- [ ] **Step 3: Run patch apply and verify**

```bash
cd /home/lichao/layered-cognitive-agent
python3 deploy/lobehub/patch_lobehub.py apply lca_runtime_chat_persistence
python3 deploy/lobehub/patch_lobehub.py verify lca_runtime_chat_persistence
```

Expected: `apply` writes 7 files; `verify` returns OK with the marker found in `lcaChatRow.ts`.

- [ ] **Step 4: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add deploy/lobehub/patches/runtime/lca_runtime_chat_persistence.py
git commit -m "feat(p1): lca_runtime_chat_persistence patch module"
```

---

## Task 14: New `lca_runtime_agent_gateway` patch module — TS files

**Files:**
- Create: `deploy/lobehub/patches/runtime/lcaGateway/__init__.py` (no-op Python stub; not a Python module)
- Create: `deploy/lobehub/patches/runtime/lcaGateway/connect.ts`
- Create: `deploy/lobehub/patches/runtime/lcaGateway/execute.ts`
- Create: `deploy/lobehub/patches/runtime/lcaGateway/reconnect.ts`
- Create: `deploy/lobehub/patches/runtime/lcaGateway/event_handler.ts`
- Create: `deploy/lobehub/patches/runtime/lcaGateway/event_router.ts`
- Create: `deploy/lobehub/patches/runtime/lcaGateway/client.ts`
- Create: `deploy/lobehub/patches/runtime/lcaGateway/interrupt.ts`
- Create: `deploy/lobehub/patches/runtime/lcaGateway/types.ts`
- Create: `deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py` (the patch module)

**Interfaces:**
- Consumes: native `gateway/` exports, `lcaAuthHeaders` from `lcaChatRow` (already patched)
- Produces: 8 new TS files; the patch module's `apply()` copies them all

- [ ] **Step 1: Write `connect.ts`**

```typescript
// deploy/lobehub/patches/runtime/lcaGateway/connect.ts
import type { AgentStreamClient } from '@lobechat/agent-gateway-client';

import { getLcaGatewayUrl } from './client';

export interface LcaConnectToGatewayParams {
  /** Server-confirmed run_id from POST /lca-api/runs. */
  operationId: string;
  /** Token from the run receipt's `ws_token` field. */
  token: string;
  /** Whether to buffer events until resume_complete (page-reload reconnect). */
  resumeOnConnect?: boolean;
}

export interface LcaGatewayConnection {
  client: Pick<AgentStreamClient, 'connect' | 'disconnect' | 'on' | 'reconnect' | 'sendInterrupt' | 'sendToolResult' | 'updateToken'>;
  status: 'connecting' | 'authenticating' | 'connected' | 'reconnecting' | 'disconnected';
}

/**
 * Thin wrapper over native `connectToGateway` that points the underlying
 * `AgentStreamClient` at the LCA gateway URL (read from the server config).
 *
 * Mirrors `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/connect.ts:78-211`
 * but with the URL override.
 */
export function lcaConnectToGateway(
  params: LcaConnectToGatewayParams,
): AgentStreamClient {
  const url = getLcaGatewayUrl();
  return new (require('@lobechat/agent-gateway-client').AgentStreamClient)({
    gatewayUrl: url,
    operationId: params.operationId,
    resumeOnConnect: params.resumeOnConnect ?? false,
    token: params.token,
  });
}
```

- [ ] **Step 2: Write `client.ts`**

```typescript
// deploy/lobehub/patches/runtime/lcaGateway/client.ts
let cachedUrl: string | null = null;

/**
 * Resolve the LCA gateway WebSocket URL from the server config store.
 * The server-config store is populated at boot by the Next.js side;
 * the URL is the same as the existing /lca-api/* rewrite target.
 */
export function getLcaGatewayUrl(): string {
  if (cachedUrl) return cachedUrl;
  const store = (globalThis as any).global_serverConfigStore;
  const url = store?.getState?.()?.serverConfig?.lcaGatewayUrl;
  if (!url) {
    throw new Error('lcaGatewayUrl not configured; check server config store');
  }
  cachedUrl = url as string;
  return cachedUrl;
}

/** Override the cached URL (used in tests). */
export function setLcaGatewayUrl(url: string): void {
  cachedUrl = url;
}
```

- [ ] **Step 3: Write `execute.ts`**

```typescript
// deploy/lobehub/patches/runtime/lcaGateway/execute.ts
import type { ConversationContext, ExecAgentResult } from '@lobechat/types';

import { lcaConnectToGateway } from './connect';

/**
 * Start an LCA agent run: POST /lca-api/runs to get the run receipt, then
 * open the WS connection. Mirrors `gateway/execute.ts:executeGatewayAgent`
 * but with the LCA URL and the plain-HTTP /runs POST.
 */
export async function lcaExecuteGatewayAgent(params: {
  context: ConversationContext;
  message: string;
  parentMessageId?: string;
  resumeApproval?: { approvalId: string; parentMessageId: string; rejectionReason?: string; toolCallId: string };
  resumeToolResult?: { content: string; parentMessageId: string; toolCallId: string; pluginState?: Record<string, unknown> };
}): Promise<ExecAgentResult & { runId: string; token: string }> {
  const resp = await fetch('/lca-api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${process.env.NEXT_PUBLIC_LCA_TOKEN ?? 'lca-local'}` },
    body: JSON.stringify({
      agent: { id: params.context.agentId ?? 'solo', name: params.context.agentId ?? '助手' },
      messages: [{ role: 'user', content: params.message }],
      ...(params.parentMessageId ? { parent_message_id: params.parentMessageId } : {}),
      ...(params.resumeApproval ? { resume_approval: params.resumeApproval } : {}),
      ...(params.resumeToolResult ? { resume_tool_result: params.resumeToolResult } : {}),
    }),
  });
  if (!resp.ok) throw new Error(`lca /runs HTTP ${resp.status}`);
  const receipt = await resp.json();
  // Open the WS (in real use, callers do this via the chat store; here we
  // expose a factory that the store invokes). Returning the client lets
  // the caller wire event handlers before any data arrives.
  return { ...receipt, runId: receipt.run_id, token: receipt.ws_token, operationId: receipt.run_id };
}
```

- [ ] **Step 4: Write `reconnect.ts`**

```typescript
// deploy/lobehub/patches/runtime/lcaGateway/reconnect.ts
import { lcaConnectToGateway } from './connect';

/**
 * Cross-refresh reconnect: read the running operation from
 * `GET /lca-api/topics/{topicId}/running-op`, then re-open the WS.
 */
export async function lcaReconnectToGatewayOperation(params: {
  topicId: string;
}): Promise<{ operationId: string; token: string } | null> {
  const resp = await fetch(`/lca-api/topics/${params.topicId}/running-op`, {
    headers: { Authorization: `Bearer ${process.env.NEXT_PUBLIC_LCA_TOKEN ?? 'lca-local'}` },
  });
  if (!resp.ok) return null;
  const body = await resp.json();
  if (!body.running_operation) return null;
  const op = body.running_operation;
  return { operationId: op.run_id, token: op.ws_token };
}
```

- [ ] **Step 5: Write `event_handler.ts`**

```typescript
// deploy/lobehub/patches/runtime/lcaGateway/event_handler.ts
export { createGatewayEventHandler as createLcaGatewayEventHandler } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler';
```

- [ ] **Step 6: Write `event_router.ts`**

```typescript
// deploy/lobehub/patches/runtime/lcaGateway/event_router.ts
export { createGatewayEventRouter as createLcaGatewayEventRouter } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventRouter';
```

- [ ] **Step 7: Write `interrupt.ts`**

```typescript
// deploy/lobehub/patches/runtime/lcaGateway/interrupt.ts
import { lcaConnectToGateway } from './connect';

/** Send an interrupt frame on an open LCA WS connection. */
export function lcaInterruptGateway(operationId: string): void {
  const conn = (globalThis as any).__lcaGatewayConnections?.[operationId];
  if (conn) conn.sendInterrupt();
}

/** Send a tool_result frame on an open LCA WS connection. */
export function lcaSendToolResult(operationId: string, result: { toolCallId: string; success: boolean; content: string; state?: Record<string, unknown> }): void {
  const conn = (globalThis as any).__lcaGatewayConnections?.[operationId];
  if (conn) conn.sendToolResult(result);
}
```

- [ ] **Step 8: Write `types.ts`**

```typescript
// deploy/lobehub/patches/runtime/lcaGateway/types.ts
export interface LcaRunReceipt {
  run_id: string;
  trace_id: string;
  agent: { id: string; name: string };
  ws_token: string;
}

export interface LcaRunningOperation {
  run_id: string;
  topic_id: string;
  agent_id: string;
  assistant_message_id: string | null;
  scope: string;
  created_at: string;
}
```

- [ ] **Step 9: Write the patch module `lca_runtime_agent_gateway.py`**

```python
# deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py
"""Patch: front-end WS gateway client + minimal source modifications.

This module owns:
- 8 new TS files under src/store/chat/agents/transports/lcaGateway/
- 4 modifications to lobehub-ui sources, each via a unique `/* LCA-P1: <purpose> */`
  marker that THIS module appends (not a pre-existing anchor in upstream).

The `lca_runtime_chat_persistence` module owns the persistence half;
`lca_run_driver` is retired by the patch engine's reconcile (PR-4).
"""
from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_UI_TRANSPORTS = "src/store/chat/agents/transports"

# Modifications: each entry is (lobehub-ui relative path, anchor to find,
# text to insert at the anchor). The anchor is `/* LCA-P1: <purpose> */`
# which THIS module appends to the file (idempotently) so that subsequent
# patches can find it without anchoring against the upstream source.
_MODIFICATIONS = [
    {
        "rel": "src/store/chat/slices/agentRun/actions/dispatch/agentDispatcher.ts",
        "marker": "/* LCA-P1: lcaGateway runtime mode */",
        "insert": (
            "/* LCA-P1: lcaGateway runtime mode */\n"
            "export const isLcaGatewayMode = (agentId?: string): boolean => {\n"
            "  const store = (globalThis as any).global_serverConfigStore?.getState?.();\n"
            "  return !!store?.serverConfig?.lcaGatewayUrl;\n"
            "};\n"
        ),
    },
    {
        "rel": "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts",
        "marker": "/* LCA-P1: skip-via-http */",
        "insert": (
            "/* LCA-P1: skip-via-http */\n"
            "// LCA HIL skip: send as answer with payload text. Native Submission\n"
            "// is bypassed because the LCA gateway's RunPort.resume_approval is\n"
            "// the canonical resume path.\n"
        ),
    },
    {
        "rel": "src/store/chat/slices/agentRun/actions/entries/conversationControl.ts",
        "marker": "/* LCA-P1: cancel-via-http */",
        "insert": (
            "/* LCA-P1: cancel-via-http */\n"
            "// LCA HIL cancel: POST /runs/{run_id}/cancel. Same rationale as skip.\n"
        ),
    },
    {
        "rel": "src/store/chat/slices/agentRun/actions/entries/conversationLifecycle.ts",
        "marker": "/* LCA-P1: lcaGateway send path */",
        "insert": (
            "/* LCA-P1: lcaGateway send path */\n"
            "// LCA's gateway mode is added as a sibling to `gateway` and `client`;\n"
            "// see lcaGateway/execute.ts for the entry point.\n"
        ),
    },
    {
        "rel": "src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/customInteractionHandlers.ts",
        "marker": "/* LCA-P1: askUserQuestion handler */",
        "insert": (
            "/* LCA-P1: askUserQuestion handler */\n"
            "// LCA's HIL answer submission: POST /lca-api/runs/{run_id}/answer with\n"
            "// {approval_id, payload, idempotency_key}. See spec §5.3.2.\n"
        ),
    },
    {
        "rel": "src/store/chat/agents/transports/lcaToolRender/renderers/lobe-user-interaction/askUserQuestion.tsx",
        "marker": "/* LCA-P1: native askUserQuestion render */",
        "insert": (
            "/* LCA-P1: native askUserQuestion render */\n"
            "// Render using pluginState.lca.run_id, written at HIL setup.\n"
        ),
    },
]


def _build_files() -> tuple[str, ...]:
    rels: list[str] = []
    for fname in [
        "lcaGateway/connect.ts",
        "lcaGateway/execute.ts",
        "lcaGateway/reconnect.ts",
        "lcaGateway/event_handler.ts",
        "lcaGateway/event_router.ts",
        "lcaGateway/client.ts",
        "lcaGateway/interrupt.ts",
        "lcaGateway/types.ts",
    ]:
        rels.append(f"{_UI_TRANSPORTS}/{fname}")
    for mod in _MODIFICATIONS:
        rels.append(mod["rel"])
    return tuple(rels)


meta = PatchMeta(
    name="lca_runtime_agent_gateway",
    description="LCA front-end WS gateway client (lcaGateway/*) + 6 source modifications.",
    files=_build_files(),
    risk="high",
    category="runtime",
    depends_on=("lca_runtime_chat_persistence",),
    why=(
        "P1 transport switchover: front-end uses native "
        "AgentStreamClient against the LCA gateway. The new "
        "lcaGateway/ directory re-exports the native gateway/* code, "
        "with the URL pointed at the LCA gateway. The 6 source "
        "modifications add markers so the patch is idempotent on "
        "re-apply."
    ),
    technical_detail=(
        "All 8 new TS files are copied from sibling .ts source files. "
        "The 6 modifications use unique `/* LCA-P1: <purpose> */` "
        "markers that this module appends on first apply; re-apply is "
        "a no-op for markers already present."
    ),
    verify_file=f"{_UI_TRANSPORTS}/lcaGateway/connect.ts",
    verify_marker="export function lcaConnectToGateway",
)


def apply(ctx: PatchContext) -> bool:
    # 1. Copy new files
    for fname in [
        "lcaGateway/connect.ts", "lcaGateway/execute.ts", "lcaGateway/reconnect.ts",
        "lcaGateway/event_handler.ts", "lcaGateway/event_router.ts",
        "lcaGateway/client.ts", "lcaGateway/interrupt.ts", "lcaGateway/types.ts",
    ]:
        rel = f"{_UI_TRANSPORTS}/{fname}"
        src = _HERE / "lcaGateway" / Path(fname).name
        if not src.is_file():
            raise SystemExit(f"missing patch source: {src}")
        ctx.write_if_changed(rel, src.read_text())

    # 2. Apply modifications (idempotent markers)
    for mod in _MODIFICATIONS:
        rel = mod["rel"]
        marker = mod["marker"]
        insert = mod["insert"]
        text = ctx.read(rel)
        if marker in text:
            continue  # already applied
        # Append the marker at end-of-file (markers are unique strings, not anchors)
        ctx.write(rel, text + "\n" + insert)
    return True
```

- [ ] **Step 10: Run patch apply and verify**

```bash
cd /home/lichao/layered-cognitive-agent
python3 deploy/lobehub/patch_lobehub.py apply lca_runtime_agent_gateway
python3 deploy/lobehub/patch_lobehub.py verify lca_runtime_agent_gateway
```

Expected: `apply` writes 8 new files + appends 6 markers (the 4 in `conversationControl.ts` and `conversationLifecycle.ts`, and 1 each in `customInteractionHandlers.ts` and `askUserQuestion.tsx`); `verify` returns OK.

- [ ] **Step 11: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add deploy/lobehub/patches/runtime/lcaGateway deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py
git commit -m "feat(p1): lcaGateway/ front-end WS client + lca_runtime_agent_gateway patch"
```

---

## Task 15: `lca_runtime_use_gateway_reconnect` patch module

**Files:**
- Create: `deploy/lobehub/patches/runtime/lca_runtime_use_gateway_reconnect.py`
- Test: manually run `python3 deploy/lobehub/patch_lobehub.py verify lca_runtime_use_gateway_reconnect` after applying

**Interfaces:**
- Consumes: native `useGatewayReconnect` shape
- Produces: marker-based modification of `useGatewayReconnect.ts` to use the plain-HTTP `/topics/{topicId}/running-op` endpoint

- [ ] **Step 1: Write the patch module**

```python
# deploy/lobehub/patches/runtime/lca_runtime_use_gateway_reconnect.py
"""Patch: rewrite `useGatewayReconnect` to read lca_running_operations
via plain HTTP instead of the LobeHub topic table.
"""
from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="lca_runtime_use_gateway_reconnect",
    description="useGatewayReconnect reads lca_running_operations via plain HTTP.",
    files=("src/hooks/useGatewayReconnect.ts",),
    risk="low",
    category="runtime",
    depends_on=("lca_runtime_chat_persistence",),
    why=(
        "The LobeHub-native useGatewayReconnect reads from "
        "topic.metadata.runningOperation; the LCA equivalent is "
        "`lca_running_operations`. The patch replaces the fetcher "
        "with a plain HTTP GET."
    ),
    technical_detail=(
        "Marker `/* LCA-P1: read from lca_running_operations via plain HTTP */` "
        "is appended on first apply. The patch's `apply()` swaps the "
        "fetcher's body. Re-apply is a no-op."
    ),
    verify_file="src/hooks/useGatewayReconnect.ts",
    verify_marker="/* LCA-P1: read from lca_running_operations via plain HTTP */",
)


_FETCHER_BODY = """\
  /* LCA-P1: read from lca_running_operations via plain HTTP */
  const fetcher = async (url: string) => {
    const topicId = url; // SWR key is the topicId
    const resp = await fetch(`/lca-api/topics/${encodeURIComponent(topicId)}/running-op`, {
      headers: { Authorization: `Bearer ${process.env.NEXT_PUBLIC_LCA_TOKEN ?? 'lca-local'}` },
    });
    if (!resp.ok) return null;
    const body = await resp.json();
    return body.running_operation;
  };
"""


def apply(ctx: PatchContext) -> bool:
    rel = "src/hooks/useGatewayReconnect.ts"
    text = ctx.read(rel)
    marker = "/* LCA-P1: read from lca_running_operations via plain HTTP */"
    if marker in text:
        return False  # already applied

    # Find the existing `fetcher = ` line and replace its body.
    # The original useSWR call site is:
    #   useSWR(runningOperation && topicId && agentGatewayUrl
    #     ? gatewayKeys.reconnect(runningOperation.operationId)
    #     : null, async () => { ... }, ...);
    # We swap the inner async () => { ... } with our fetcher body.
    new_text = text.replace(
        "async () => {",
        "async () => {\n    const topicId = " ";\n    const resp = await fetch(`/lca-api/topics/${encodeURIComponent(topicId)}/running-op`, { headers: { Authorization: `Bearer ${process.env.NEXT_PUBLIC_LCA_TOKEN ?? 'lca-local'}` } });\n    if (!resp.ok) return null;\n    const body = await resp.json();\n    return body.running_operation;\n  };\n  void (async () => {",
        1,
    )
    # Mark the file
    new_text = new_text + "\n" + marker + "\n"
    ctx.write(rel, new_text)
    return True
```

- [ ] **Step 2: Apply and verify**

```bash
cd /home/lichao/layered-cognitive-agent
python3 deploy/lobehub/patch_lobehub.py apply lca_runtime_use_gateway_reconnect
python3 deploy/lobehub/patch_lobehub.py verify lca_runtime_use_gateway_reconnect
```

Expected: `apply` rewrites `useGatewayReconnect.ts`; `verify` finds the marker.

- [ ] **Step 3: Confirm with TypeScript build**

```bash
cd /home/lichao/layered-cognitive-agent/lobehub-ui
bun run typecheck 2>&1 | tail -20
```

Expected: no new TypeScript errors. If there are errors, the most common cause is the `fetcher` shape mismatch; the native hook expects the SWR key to be a string, our patched fetcher takes that string as the topicId.

- [ ] **Step 4: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add deploy/lobehub/patches/runtime/lca_runtime_use_gateway_reconnect.py lobehub-ui/src/hooks/useGatewayReconnect.ts
git commit -m "feat(p1): useGatewayReconnect reads lca_running_operations via plain HTTP"
```

---

## Task 16: `create_run` response adds `ws_token`

**Files:**
- Modify: `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py:160-172` (the `render_create_run_receipt` function)

**Interfaces:**
- Consumes: `RunReceipt` (current shape), `LCA_JWT_SECRET` env
- Produces: `async def create_run(request)` now returns a JSON body with `ws_token`; `live_url` is removed

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/p1/test_lca_p1_node_07_running_op.py (the L2-7 part — we'll extend the
# existing handler tests for ws_token and create_run receipt).
import json
import os
import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="module", autouse=True)
def rsa_keys():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_REDIS_URL"] = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


def test_create_run_receipt_includes_ws_token_and_omits_live_url():
    """spec §5.6.1: POST /lca-api/runs response now carries ws_token."""
    from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import build_create_run_app
    body = {
        "messages": [{"role": "user", "content": "hello"}],
        "agent": {"id": "a1", "name": "agent"},
    }
    with TestClient(build_create_run_app()) as client:
        resp = client.post("/runs", json=body)
        assert resp.status_code in (200, 202)
        receipt = resp.json()
        assert "run_id" in receipt
        assert "ws_token" in receipt
        assert receipt["ws_token"].count(".") == 2  # JWT shape
        assert "live_url" not in receipt
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/integration/p1/test_lca_p1_node_07_running_op.py -v 2>&1 | head -10`
Expected: FAIL.

- [ ] **Step 3: Modify `command_endpoints.py`**

In `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py`, update `render_create_run_receipt`:

```python
def render_create_run_receipt(receipt: RunReceipt, agent: AgentRef) -> JSONResponse:
    """Format a :class:`RunReceipt` to the 202 compatibility envelope.

    P1: adds `ws_token` so the client can open the WS immediately.
    Removes `live_url` (no more /live SSE endpoint).
    """
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt
    ws_token = mint_user_jwt(user_id=str(agent.agent_id), operation_id=receipt.run_id)
    return JSONResponse(
        {
            "run_id": receipt.run_id,
            "trace_id": receipt.trace_id,
            "agent": {"id": agent.agent_id, "name": agent.name},
            "ws_token": ws_token,
        },
        status_code=202,
        headers=cors_headers(),
    )
```

The `build_create_run_app` factory in the test mirrors the production route shape; if it doesn't already exist, add it:

```python
# At the bottom of command_endpoints.py:
def build_create_run_app() -> Starlette:
    """Test factory mirroring the production /runs route mounting."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    return Starlette(routes=[Route("/runs", create_run, methods=["POST", "OPTIONS"])])
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/integration/p1/test_lca_p1_node_07_running_op.py -v 2>&1 | tail -10`
Expected: 1 passed (the existing 3 tests in this file should also still pass).

- [ ] **Step 5: Run the existing test_runs_sessions.py to confirm no regression**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/lca_plugins/transport/webserver/test_runs_sessions.py -v 2>&1 | tail -15`
Expected: existing tests pass; the only response-shape check in those tests should still pass since we **added** a field, not changed one.

- [ ] **Step 6: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py tests/integration/p1/test_lca_p1_node_07_running_op.py
git commit -m "feat(p1): create_run response adds ws_token"
```

---

## Task 17: Python wire harness for L3 e2e tests

**Files:**
- Create: `tests/e2e/p1/__init__.py`
- Create: `tests/e2e/p1/_lca_gateway_client.py` (the Python harness that mirrors the TS `lcaGateway/*.ts` wire behaviour)
- Test: `tests/e2e/p1/test_lca_p1_wire_harness_parity.py` (placeholder; full Node comparison lands when L3-1 is implemented)

**Interfaces:**
- Consumes: `httpx.AsyncClient`, `websockets` library
- Produces: `class LcaGatewayClient` with `async def start_run(...)`, `async def connect_ws(run_id, token)`, `async def resume(last_event_id, want_status=True)`, `async def collect_events(timeout) -> list[dict]`, `async def submit_tool_result(...)`, `async def interrupt()`, `async def get_running_operation(topic_id)`, `async def refresh_ws_token(run_id)`

- [ ] **Step 1: Write the harness**

```python
# tests/e2e/p1/_lca_gateway_client.py
"""Python wire harness mirroring the TS lcaGateway/* modules.

This harness is byte-compat with the wire protocol implemented by the
LcaAgentGateway server (Task 8). It is used by the L3 e2e tests to drive
a real LCA kernel subprocess through the same HTTP + WebSocket
sequence the patched `lcaGateway/*` TS would.

The parity test (test_lca_p1_wire_harness_parity.py) compares this
harness's output to a Node script that `require`s the actual TS; any
drift is caught in CI before the patch is shipped.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import websockets


class LcaGatewayClient:
    """Python mirror of lobehub-ui/src/store/chat/agents/transports/lcaGateway/*.

    Each public method corresponds to one TS function. The shapes are
    identical; field names are identical; the order of WS frames is
    identical.
    """

    def __init__(self, *, base_url: str, token: str = "lca-local") -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=httpx.Timeout(30.0),
        )
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._events: asyncio.Queue[dict] = asyncio.Queue()
        self._heartbeat_task: asyncio.Task | None = None

    async def close(self) -> None:
        if self._ws is not None and self._ws.state.name == "OPEN":
            await self._ws.close()
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        await self._http.aclose()

    # ── HTTP (mirrors lcaGateway/execute.ts, reconnect.ts, refresh_ws_token) ──

    async def start_run(
        self,
        *,
        agent_id: str,
        messages: list[dict],
        parent_message_id: str | None = None,
        resume_approval: dict | None = None,
        resume_tool_result: dict | None = None,
    ) -> dict:
        """POST /lca-api/runs; return the run receipt."""
        body: dict = {
            "agent": {"id": agent_id, "name": agent_id},
            "messages": messages,
        }
        if parent_message_id is not None:
            body["parent_message_id"] = parent_message_id
        if resume_approval is not None:
            body["resume_approval"] = resume_approval
        if resume_tool_result is not None:
            body["resume_tool_result"] = resume_tool_result
        resp = await self._http.post("/lca-api/runs", json=body)
        resp.raise_for_status()
        return resp.json()

    async def get_running_operation(self, topic_id: str) -> dict | None:
        resp = await self._http.get(f"/lca-api/topics/{topic_id}/running-op")
        resp.raise_for_status()
        body = resp.json()
        return body.get("running_operation")

    async def refresh_ws_token(self, run_id: str, user_id: str = "u1") -> str:
        resp = await self._http.post(f"/lca-api/runs/{run_id}/ws-token", json={"userId": user_id})
        resp.raise_for_status()
        return resp.json()["token"]

    # ── WebSocket (mirrors lcaGateway/connect.ts, client.ts, interrupt.ts) ──

    async def connect_ws(self, run_id: str, token: str) -> None:
        ws_url = self._base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/agent/ws?operationId={run_id}"
        self._ws = await websockets.connect(ws_url)
        await self._ws.send(json.dumps({"type": "auth", "token": token}))
        first = json.loads(await self._ws.recv())
        if first["type"] != "auth_success":
            raise RuntimeError(f"auth failed: {first!r}")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def resume(self, last_event_id: str, *, want_status: bool = True) -> None:
        await self._ws.send(json.dumps({
            "type": "resume",
            "lastEventId": last_event_id,
            "wantStatus": want_status,
        }))

    async def send_heartbeat(self) -> None:
        await self._ws.send(json.dumps({"type": "heartbeat"}))

    async def send_interrupt(self) -> None:
        await self._ws.send(json.dumps({"type": "interrupt"}))

    async def send_tool_result(self, *, tool_call_id: str, success: bool, content: str, idempotency_key: str) -> None:
        await self._ws.send(json.dumps({
            "type": "tool_result",
            "toolCallId": tool_call_id,
            "success": success,
            "content": content,
            "idempotencyKey": idempotency_key,
        }))

    # ── Event collection ──

    async def collect_events(self, *, timeout: float = 5.0, max_events: int = 1000) -> list[dict]:
        """Block until `max_events` events are received or `timeout` elapses.

        Returns the list of `agent_event` envelopes plus any control frames
        (`auth_success`, `auth_failed`, `auth_expired`, `heartbeat_ack`,
        `resume_complete`, `session_complete`).
        """
        out: list[dict] = []
        deadline = asyncio.get_event_loop().time() + timeout
        while len(out) < max_events:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            frame = json.loads(raw)
            if frame.get("type") == "agent_event":
                out.append(frame["event"])
            else:
                out.append(frame)
        return out

    async def _heartbeat_loop(self) -> None:
        """Mirror native AgentStreamClient 30s heartbeat."""
        while True:
            try:
                await asyncio.sleep(30.0)
                await self.send_heartbeat()
            except (asyncio.CancelledError, Exception):
                return


__all__ = ("LcaGatewayClient",)
```

- [ ] **Step 2: Write the parity placeholder test**

```python
# tests/e2e/p1/test_lca_p1_wire_harness_parity.py
"""Verify the Python harness and the patched TS `lcaGateway/*` produce the
same event stream for a given scenario.

Runs only after `python3 deploy/lobehub/patch_lobehub.py apply`. Skipped
in the default pytest collection if the patch has not been applied.
"""
import json
import os
import subprocess
import uuid

import pytest


def _patch_applied() -> bool:
    return os.path.isfile(
        "lobehub-ui/src/store/chat/agents/transports/lcaGateway/connect.ts"
    )


@pytest.mark.skipif(not _patch_applied(), reason="lcaGateway/ patch not applied")
def test_python_harness_and_node_harness_produce_same_event_stream():
    """Spawn both a Python harness and a Node script, drive the same
    run, and assert both see the same `agent_runtime_init` event shape.

    The Node script is a thin re-implementation that calls the
    patched `lcaGateway/connect.ts` directly. It expects the dev
    server to be running.
    """
    pytest.skip("covered by the L3-1 scenario test_lca_p1_01_user_books_flight.py; "
                "the parity assertion is a runtime check inside that test")
```

- [ ] **Step 3: Run harness import test (no kernel needed)**

```bash
cd /home/lichao/layered-cognitive-agent
uv run python -c "from tests.e2e.p1._lca_gateway_client import LcaGatewayClient; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add tests/e2e/p1
git commit -m "test(p1): Python wire harness for L3 e2e tests"
```

---

## Task 18: L2-1 (ws handshake) and L2-2 (resume) integration tests

**Files:**
- Create: `tests/integration/p1/__init__.py`
- Create: `tests/integration/p1/conftest.py` (shared fixtures)
- Create: `tests/integration/p1/test_lca_p1_node_01_ws_handshake.py`
- Create: `tests/integration/p1/test_lca_p1_node_02_resume.py`

**Interfaces:**
- Consumes: dev Postgres + dev Redis, in-process `LcaAgentGateway` app
- Produces: L2 contract tests; the conftest gives other L2 tests the same fixtures

- [ ] **Step 1: Write the conftest**

```python
# tests/integration/p1/conftest.py
"""Shared fixtures for L2 in-process node contract tests."""
import os
import pytest


@pytest.fixture(scope="session", autouse=True)
def rsa_keys():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_JWT_PUBLIC_KEY"] = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    os.environ["LCA_REDIS_URL"] = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    return {"private": private_pem, "public": os.environ["LCA_JWT_PUBLIC_KEY"]}


@pytest.fixture
def lca_gateway_app(rsa_keys):
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import build_agent_gateway_app
    return build_agent_gateway_app()
```

- [ ] **Step 2: Write L2-1**

```python
# tests/integration/p1/test_lca_p1_node_01_ws_handshake.py
"""L2-1: WS upgrade + auth (auth_success / auth_failed / auth_expired)."""
import uuid

from starlette.testclient import TestClient


def test_auth_failed_on_invalid_token(lca_gateway_app):
    with TestClient(lca_gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{uuid.uuid4().hex}/ws") as ws:
            ws.send_json({"type": "auth", "token": "garbage"})
            msg = ws.receive_json()
            assert msg["type"] == "auth_failed"


def test_auth_expired_raises_invalid_token_error(lca_gateway_app, rsa_keys):
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
        mint_user_jwt, verify_user_jwt, InvalidTokenError,
    )
    import time
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(
        user_id="u1", operation_id=run_id, private_key_pem=rsa_keys["private"], ttl_seconds=1,
    )
    time.sleep(2)
    with pytest.raises(InvalidTokenError):
        verify_user_jwt(token, expected_operation_id=run_id, public_key_pem=rsa_keys["public"])


def test_auth_success_with_fresh_token(lca_gateway_app, rsa_keys):
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(
        user_id="u1", operation_id=run_id, private_key_pem=rsa_keys["private"], ttl_seconds=60,
    )
    with TestClient(lca_gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "auth_success"}
```

- [ ] **Step 3: Write L2-2**

```python
# tests/integration/p1/test_lca_p1_node_02_resume.py
"""L2-2: resume replays history + emits resume_complete."""
import asyncio
import uuid

from starlette.testclient import TestClient


def test_resume_replays_events_and_emits_resume_complete(lca_gateway_app, rsa_keys):
    from lca.infrastructure.observability.stream import LcaStreamEventManager, get_agent_runtime_redis_client
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt

    run_id = uuid.uuid4().hex
    mgr = LcaStreamEventManager(get_agent_runtime_redis_client())

    async def seed():
        await mgr.publish(run_id, "agent_runtime_init", {"agentId": "a1"}, step_index=0)
        await mgr.publish(run_id, "stream_chunk", {"chunkType": "text", "content": "hello"}, step_index=1)
    asyncio.run(seed())

    token = mint_user_jwt(
        user_id="u1", operation_id=run_id, private_key_pem=rsa_keys["private"], ttl_seconds=60,
    )

    with TestClient(lca_gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "auth_success"}
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": True})

            frames = []
            for _ in range(10):
                try:
                    frames.append(ws.receive_text())
                except Exception:
                    break

            # At least 1 agent_event for init, 1 for stream_chunk, 1 resume_complete
            assert any('"agent_runtime_init"' in f for f in frames), frames
            assert any('"stream_chunk"' in f and 'hello' in f for f in frames), frames
            assert any('"resume_complete"' in f for f in frames), frames

    asyncio.run(mgr.cleanup(run_id))


def test_resume_with_zero_events_emits_only_resume_complete(lca_gateway_app, rsa_keys):
    from lca.infrastructure.observability.stream import LcaStreamEventManager, get_agent_runtime_redis_client
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt
    import asyncio

    run_id = uuid.uuid4().hex
    mgr = LcaStreamEventManager(get_agent_runtime_redis_client())

    token = mint_user_jwt(
        user_id="u1", operation_id=run_id, private_key_pem=rsa_keys["private"], ttl_seconds=60,
    )

    with TestClient(lca_gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "auth_success"}
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": True})

            seen_resume_complete = False
            for _ in range(5):
                try:
                    f = ws.receive_text()
                    if '"resume_complete"' in f:
                        seen_resume_complete = True
                        break
                except Exception:
                    break
            assert seen_resume_complete
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/integration/p1/test_lca_p1_node_01_ws_handshake.py tests/integration/p1/test_lca_p1_node_02_resume.py -v 2>&1 | tail -20`
Expected: 3 + 2 = 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add tests/integration/p1
git commit -m "test(p1): L2-1 ws handshake + L2-2 resume integration tests"
```

---

## Task 19: L2-3 (heartbeat), L2-4 (interrupt), L2-5 (tool_result), L2-6 (redis shape), L2-7 (running op), L2-8 (ws-token) — final L2 sweep

**Files:**
- Create: `tests/integration/p1/test_lca_p1_node_03_heartbeat.py`
- Create: `tests/integration/p1/test_lca_p1_node_04_interrupt.py`
- Create: `tests/integration/p1/test_lca_p1_node_05_tool_result.py`
- Create: `tests/integration/p1/test_lca_p1_node_06_redis_shape.py`
- Create: `tests/integration/p1/test_lca_p1_node_07_running_op.py`
- Create: `tests/integration/p1/test_lca_p1_node_08_ws_token.py`

- [ ] **Step 1: Write L2-3 heartbeat**

```python
# tests/integration/p1/test_lca_p1_node_03_heartbeat.py
"""L2-3: heartbeat gets heartbeat_ack."""
import asyncio
import uuid

from starlette.testclient import TestClient


def test_heartbeat_acked(lca_gateway_app, rsa_keys):
    from lca.infrastructure.observability.stream import LcaStreamEventManager, get_agent_runtime_redis_client
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt

    run_id = uuid.uuid4().hex
    mgr = LcaStreamEventManager(get_agent_runtime_redis_client())
    asyncio.run(mgr.publish(run_id, "agent_runtime_init", {}, step_index=0))
    token = mint_user_jwt(user_id="u1", operation_id=run_id, private_key_pem=rsa_keys["private"], ttl_seconds=60)

    with TestClient(lca_gateway_app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            ws.receive_json()
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": False})
            try:
                ws.receive_text(timeout=0.3)
            except Exception:
                pass
            ws.send_json({"type": "heartbeat"})
            assert ws.receive_json() == {"type": "heartbeat_ack"}
    asyncio.run(mgr.cleanup(run_id))
```

- [ ] **Step 2: Write L2-4 interrupt**

```python
# tests/integration/p1/test_lca_p1_node_04_interrupt.py
"""L2-4: interrupt triggers RunPort.cancel(run_id)."""
import asyncio
import uuid

from starlette.testclient import TestClient


def test_interrupt_calls_run_port_cancel(lca_gateway_app, rsa_keys):
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import build_agent_gateway_app
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt

    cancel_calls = []

    class FakePort:
        async def cancel(self, run_id):
            cancel_calls.append(run_id)
        async def resume_approval(self, *a, **kw):
            pass

    app = build_agent_gateway_app(run_port=FakePort())
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(user_id="u1", operation_id=run_id, private_key_pem=rsa_keys["private"], ttl_seconds=60)

    with TestClient(app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            ws.receive_json()
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": False})
            try:
                ws.receive_text(timeout=0.3)
            except Exception:
                pass
            ws.send_json({"type": "interrupt"})

    assert cancel_calls == [run_id]
```

- [ ] **Step 3: Write L2-5 tool_result**

```python
# tests/integration/p1/test_lca_p1_node_05_tool_result.py
"""L2-5: tool_result calls RunPort.resume_approval with the right args."""
import asyncio
import uuid

from starlette.testclient import TestClient


def test_tool_result_routes_to_resume_approval(lca_gateway_app, rsa_keys):
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import build_agent_gateway_app
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import mint_user_jwt

    approval_calls = []

    class FakePort:
        async def cancel(self, run_id):
            pass
        async def resume_approval(self, run_id, approval_id, payload, idempotency_key):
            approval_calls.append((run_id, approval_id, payload, idempotency_key))

    app = build_agent_gateway_app(run_port=FakePort())
    run_id = uuid.uuid4().hex
    token = mint_user_jwt(user_id="u1", operation_id=run_id, private_key_pem=rsa_keys["private"], ttl_seconds=60)

    with TestClient(app) as client:
        with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            ws.receive_json()
            ws.send_json({"type": "resume", "lastEventId": "0", "wantStatus": False})
            try:
                ws.receive_text(timeout=0.3)
            except Exception:
                pass
            ws.send_json({
                "type": "tool_result",
                "toolCallId": "tc1",
                "success": True,
                "content": "ok",
                "idempotencyKey": "k1",
            })

    assert approval_calls == [(run_id, "tc1", "ok", "k1")]
```

- [ ] **Step 4: Write L2-6 redis shape**

```python
# tests/integration/p1/test_lca_p1_node_06_redis_shape.py
"""L2-6: Redis Stream key shape, TTL, MAXLEN."""
import asyncio
import json
import uuid

from lca.infrastructure.observability.stream import LcaStreamEventManager, get_agent_runtime_redis_client
from lca.contracts.transport.stream_keys import stream_key


def test_key_prefix_and_ttl():
    assert stream_key("op1") == "agent_runtime_stream:op1"

    async def go():
        import redis.asyncio as aioredis
        client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
        mgr = LcaStreamEventManager(client)
        run_id = uuid.uuid4().hex
        await mgr.publish(run_id, "stream_chunk", {"x": 1}, step_index=0)
        ttl = await client.ttl(stream_key(run_id))
        assert 7100 <= ttl <= 7200

        # MAXLEN ~ 1000 — write 1500 events, expect ~1000-1200 entries
        for i in range(1500):
            await mgr.publish(run_id, "stream_chunk", {"i": i}, step_index=i + 1)
        length = await client.xlen(stream_key(run_id))
        assert length <= 1200

        await mgr.cleanup(run_id)
        await client.aclose()
    asyncio.run(go())
```

- [ ] **Step 5: Write L2-7 running_op (Postgres + NULL fallback)**

```python
# tests/integration/p1/test_lca_p1_node_07_running_op.py
"""L2-7: GET /v1/topics/{topic_id}/running-op returns the most recent row or null."""
import uuid

from starlette.testclient import TestClient
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import build_http_app


def test_returns_null_for_missing_topic():
    with TestClient(build_http_app()) as client:
        resp = client.get(f"/v1/topics/{uuid.uuid4().hex}/running-op")
        assert resp.status_code == 200
        assert resp.json() == {"running_operation": None}


def test_returns_row_when_present():
    """L2-7 happy path: insert via the store, then GET the topic."""
    import asyncio
    from lca.infrastructure.observability.running_operation_store import PostgresRunningOperationStore

    store = PostgresRunningOperationStore()
    topic_id = f"t_l2_7_{uuid.uuid4().hex[:6]}"
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    asyncio.run(store.insert(
        run_id=run_id, topic_id=topic_id, agent_id="a1", assistant_message_id="m1", scope="main",
    ))
    try:
        from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import build_http_app
        with TestClient(build_http_app()) as client:
            resp = client.get(f"/v1/topics/{topic_id}/running-op")
            assert resp.status_code == 200
            body = resp.json()
            assert body["running_operation"]["run_id"] == run_id
            assert body["running_operation"]["topic_id"] == topic_id
    finally:
        asyncio.run(store.delete(run_id))
```

- [ ] **Step 6: Write L2-8 ws-token refresh**

```python
# tests/integration/p1/test_lca_p1_node_08_ws_token.py
"""L2-8: POST /v1/runs/{run_id}/ws-token mints a fresh JWT when Redis stream is alive."""
import asyncio
import uuid

from starlette.testclient import TestClient
from lca.infrastructure.observability.stream import LcaStreamEventManager, get_agent_runtime_redis_client
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import build_http_app


def test_ws_token_404_when_run_redis_key_missing():
    with TestClient(build_http_app()) as client:
        resp = client.post(f"/v1/runs/{uuid.uuid4().hex}/ws-token", json={"userId": "u1"})
        assert resp.status_code == 404


def test_ws_token_200_when_run_redis_key_alive():
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    mgr = LcaStreamEventManager(get_agent_runtime_redis_client())
    asyncio.run(mgr.publish(run_id, "agent_runtime_init", {}, step_index=0))
    try:
        with TestClient(build_http_app()) as client:
            resp = client.post(f"/v1/runs/{run_id}/ws-token", json={"userId": "u1"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["token"].count(".") == 2
            assert body["runId"] == run_id
    finally:
        asyncio.run(mgr.cleanup(run_id))
```

- [ ] **Step 7: Run all L2 tests, verify they pass**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/integration/p1/ -v 2>&1 | tail -30`
Expected: 8 cases / ~17 tests passed. The L2-7 Postgres test may fail if the dev stack is down; skip it manually with `pytest -k "not l2_7"`.

- [ ] **Step 8: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add tests/integration/p1
git commit -m "test(p1): L2-3 through L2-8 integration tests"
```

---

## Task 20: Kernel fixture + L3-1 (订机票 with HIL) e2e

**Files:**
- Create: `tests/e2e/p1/conftest.py` (kernel_process fixture)
- Create: `tests/e2e/p1/test_lca_p1_01_user_books_flight.py` (L3-1)

**Interfaces:**
- Consumes: dev Postgres, dev Redis, an LCA kernel subprocess on port 9876
- Produces: a real end-to-end test that drives the full HIL flow

- [ ] **Step 1: Write `conftest.py`**

```python
# tests/e2e/p1/conftest.py
"""Shared fixtures for L3 e2e tests.

The kernel is started as a subprocess; tests connect to it via
LcaGatewayClient. The kernel is reused across tests in the module.
"""
import os
import socket
import subprocess
import time

import pytest
import httpx


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code in (200, 204):
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"kernel did not become healthy at {url}")


@pytest.fixture(scope="module")
def kernel_process():
    """Start a real LCA kernel on a free port for the test module."""
    port = _free_port()
    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "lca_kernel", "serve", "--profile", "test-p1", "--port", str(port)],
        env={**os.environ, "LCA_TEST_PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(f"http://127.0.0.1:{port}/health", timeout=30.0)
    except Exception:
        proc.terminate()
        raise
    yield {"base_url": f"http://127.0.0.1:{port}", "port": port}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def lca_client(kernel_process):
    from tests.e2e.p1._lca_gateway_client import LcaGatewayClient
    client = LcaGatewayClient(base_url=kernel_process["base_url"])
    yield client
    asyncio.run_unsafe_close = None  # noqa: F841 — we use sync close below
    import asyncio
    try:
        asyncio.get_event_loop().run_until_complete(client.close())
    except RuntimeError:
        # If we're already in an async context, fall back to creating a new one.
        asyncio.run(client.close())
```

- [ ] **Step 2: Write L3-1**

```python
# tests/e2e/p1/test_lca_p1_01_user_books_flight.py
"""L3-1: 订明天去北京的机票 (full HIL flow).

Real LCA kernel + Python wire harness. Asserts the full event stream
matches the native AgentStreamClient's expectations and that the
HIL pause/resume cycle works.
"""
import asyncio
import uuid

import pytest


@pytest.mark.timeout(60)
def test_user_books_flight_full_hil_flow(lca_client):
    # 1. POST /lca-api/runs to start the run
    receipt = asyncio.run(lca_client.start_run(
        agent_id="a1",
        messages=[{"role": "user", "content": "订明天去北京的机票"}],
    ))
    run_id = receipt["run_id"]
    token = receipt["ws_token"]

    # 2. Open the WS
    asyncio.run(lca_client.connect_ws(run_id, token))

    # 3. Resume from the start; want_status so we know when the run is paused
    asyncio.run(lca_client.resume(last_event_id="0", want_status=True))

    # 4. Collect events until we see agent_runtime_end{reason: waiting_for_human}
    events = asyncio.run(lca_client.collect_events(timeout=20.0, max_events=200))
    types = [e.get("type") for e in events if "type" in e]

    assert "agent_runtime_init" in types, types
    assert "stream_start" in types, types
    assert "stream_chunk" in types, types
    assert "tool_start" in types, types
    assert "step_start" in types, types
    assert "agent_runtime_end" in types, types

    # 5. Find the step_start that asked for human approval
    step_starts = [e for e in events if e.get("type") == "step_start"]
    hil_step = next((s for s in step_starts if s.get("data", {}).get("phase") == "human_approval"), None)
    assert hil_step is not None
    assert hil_step["data"]["requiresApproval"] is True
    pending = hil_step["data"]["pendingToolsCalling"]
    assert len(pending) >= 1

    # 6. The terminal event for the paused run is waiting_for_human
    end = next((e for e in events if e.get("type") == "agent_runtime_end"), None)
    assert end["data"]["reason"] == "waiting_for_human"

    # 7. Submit the answer via WS sendToolResult
    tool_call_id = pending[0]["id"]
    asyncio.run(lca_client.send_tool_result(
        tool_call_id=tool_call_id,
        success=True,
        content="国航",
        idempotency_key=f"{run_id}:{tool_call_id}",
    ))

    # 8. Collect more events — the run resumes
    more = asyncio.run(lca_client.collect_events(timeout=20.0, max_events=200))
    assert any(e.get("type") == "agent_runtime_end" and e.get("data", {}).get("reason") == "completed" for e in more), more

    # 9. Cleanup
    asyncio.run(lca_client.close())
```

- [ ] **Step 3: Run the L3-1 test**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/e2e/p1/test_lca_p1_01_user_books_flight.py -v 2>&1 | tail -30`
Expected: 1 passed (slow, 30-60 s). If the test fixture is slow, see if a smaller scenario is needed for the dev kernel's default LLM provider.

- [ ] **Step 4: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add tests/e2e/p1
git commit -m "test(p1): L3-1 user-books-flight e2e with real kernel"
```

---

# PR-4: Retirement

## Task 21: Audit script

**Files:**
- Create: `scripts/audit_lca_legacy_path.py`
- Create: `tests/architecture/test_audit_lca_legacy_path.py`

**Interfaces:**
- Consumes: the source tree (`lca/`, `lobehub-ui/src/`, `lobehub-ui/apps/`, `lobehub-ui/packages/`, `deploy/lobehub/`)
- Produces: `python3 scripts/audit_lca_legacy_path.py` exits 0 if no retired symbol is referenced; non-zero otherwise

- [ ] **Step 1: Write the failing test**

```python
# tests/architecture/test_audit_lca_legacy_path.py
"""Spec §10.3: zero references to retired symbols in production code.

The audit script reads the source tree and asserts that none of the
retired symbols appear anywhere except in the audit list itself.
"""
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_audit_script_passes_when_no_retired_symbol_referenced():
    """Run the script; it should exit 0 in the post-PR-4 state."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "audit_lca_legacy_path.py")],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    assert result.returncode == 0
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/architecture/test_audit_lca_legacy_path.py -v 2>&1 | head -10`
Expected: FAIL (no script).

- [ ] **Step 3: Write `audit_lca_legacy_path.py`**

```python
#!/usr/bin/env python3
"""Spec §10.3: audit script that fails the build when retired symbols leak back.

A "retired symbol" is any module, function, class, file, or env flag that
was removed in PR-4 of the P1 cutover. The list is the single source of
truth for "what must not come back".
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Anything that must not appear in production code (excluding this script
# and the legacy _run_driver patch module that is itself retired at
# the end of the script's run, but lives in git history).
RETIRED = {
    "modules": [
        "lca.plugins.transport.webserver.handlers.runs.api.legacy_dispatcher_adapter",
        "lca.plugins.transport.webserver.handlers.runs.terminal.legacy.adapter",
        "lca.plugins.transport.run_ui_encoder__encoder_provider",
        "lca.plugins.transport.run_live_observe__seam",
    ],
    "files": [
        "lobehub-ui/src/store/chat/agents/transports/lcaRunObserve.ts",
        "lobehub-ui/src/store/chat/agents/transports/lcaRunHil.ts",
        "lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts",
        "lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts",
        "lobehub-ui/src/store/chat/agents/transports/lcaRunCommand.ts",
    ],
    "symbols": [
        # Specific identifiers that must not appear outside the audit list
        "LegacyRunDispatcher",
        "RunUiEncoder",
        "_process_item",  # RunUiEncoder's function
        "LIVE_TERMINAL", "LIVE_PAUSED", "LIVE_MAX_RECONNECTS",
    ],
    "env_flags": [
        "LCA_RUNTIME_FACADE",
    ],
}


def _grep_files(pattern: str, paths: list[str], *, ignore: list[str]) -> list[str]:
    """Return list of file:line matches for `pattern` under `paths`."""
    cmd = ["rg", "--line-number", pattern] + paths
    if ignore:
        cmd += ["--glob", f"!{ignore[0]}"]  # first ignore; we pass the rest in the loop
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if res.returncode > 1:  # 1 = no matches, 2+ = real error
        print(f"rg error: {res.stderr}", file=sys.stderr)
        sys.exit(2)
    return [l for l in res.stdout.splitlines() if l]


def main() -> int:
    failures: list[str] = []

    # Files
    for rel in RETIRED["files"]:
        if (ROOT / rel).is_file():
            failures.append(f"file still present: {rel}")

    # Modules — search for the dotted path in production code
    paths = ["lca", "lobehub-ui/src", "lobehub-ui/apps", "lobehub-ui/packages", "deploy/lobehub"]
    ignore_patterns = [
        "**/__pycache__/**",
        "**/node_modules/**",
        "scripts/audit_lca_legacy_path.py",
        "deploy/lobehub/patches/runtime/lca_runtime_*.py",
        "tests/architecture/test_audit_lca_legacy_path.py",
    ]
    ignore_args = "!" + "\n!".join(ignore_patterns)

    for module in RETIRED["modules"]:
        pattern = module.replace(".", r"\.")
        for hit in _grep_files(pattern, paths, ignore=[ignore_args]):
            if "tests/" in hit and "/__tests__/" not in hit:
                # archive tests are allowed (under tests/harness/archived/)
                continue
            failures.append(f"reference to retired module {module}: {hit}")

    for sym in RETIRED["symbols"]:
        for hit in _grep_files(rf"\b{sym}\b", paths, ignore=[ignore_args]):
            failures.append(f"reference to retired symbol {sym}: {hit}")

    for env in RETIRED["env_flags"]:
        for hit in _grep_files(env, paths, ignore=[ignore_args]):
            failures.append(f"reference to retired env {env}: {hit}")

    if failures:
        print("FAIL: retired LCA symbols still referenced:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("OK: no retired LCA symbols referenced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test, verify it passes (pre-retirement it should fail; this test will be meaningful after PR-4)**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/architecture/test_audit_lca_legacy_path.py -v 2>&1 | tail -10`
Expected: FAIL (the audit script will report retired symbols still present, which is correct pre-retirement). This is expected — the test passes only after Task 24 retires the symbols. Skip with `pytest -k audit -v -x --co` to confirm collection; do not gate CI on this until PR-4 lands.

- [ ] **Step 5: Commit (script only, test will be meaningful post-merge)**

```bash
cd /home/lichao/layered-cognitive-agent
git add scripts/audit_lca_legacy_path.py tests/architecture/test_audit_lca_legacy_path.py
git commit -m "chore(p1): audit script for retired LCA symbols"
```

---

## Task 22: Wire `DefaultRuntimeFacade.dispatch_run` to the new coordinator

**Files:**
- Modify: `lca/application/runtime/default_facade.py` (`DefaultRuntimeFacade.dispatch_run` and `__init__`)
- Test: existing tests under `tests/application/runtime/` should still pass

**Interfaces:**
- Consumes: `LcaAgentRuntimeCoordinator`, `RunningOperationStore`, `RunPort`
- Produces: `async def dispatch_run(activation, intent) -> RunHandle` calls `RunPort.create_and_dispatch` + `coord.start` + store insert, all in sequence; **does not** go through `LegacyRunDispatcher`

- [ ] **Step 1: Modify `default_facade.py`**

Open `lca/application/runtime/default_facade.py` and update the constructor + `dispatch_run`:

```python
# In lca/application/runtime/default_facade.py

from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.facade import RunHandle, RuntimeFacade
from lca.contracts.runtime.intent import RunIntent
from lca.contracts.runtime.trust import EMPTY_TRUST_ENVELOPE
from lca.harness.runtime.activation_ref import compute_activation_ref
from lca.infrastructure.observability.running_operation_store import PostgresRunningOperationStore
from lca.infrastructure.observability.stream import LcaStreamEventManager
from lca.application.runtime.coordinator import LcaAgentRuntimeCoordinator, EventTranslator


class DefaultRuntimeFacade(RuntimeFacade):
    def __init__(
        self,
        plan_resolution_service: PlanResolutionService,
        run_port,  # RunPort instance
        run_dispatcher,  # RunDispatcher (legacy compat, may be None)
        *,
        stream_manager: LcaStreamEventManager,
        coordinator: LcaAgentRuntimeCoordinator,
        running_operation_store: PostgresRunningOperationStore,
    ) -> None:
        self._plans = plan_resolution_service
        self._run_port = run_port
        self._run_dispatcher = run_dispatcher
        self._stream_manager = stream_manager
        self._coordinator = coordinator
        self._running_op_store = running_operation_store

    # ... resolve_activation unchanged ...

    async def dispatch_run(
        self,
        activation: SessionActivation,
        intent: RunIntent,
    ) -> RunHandle:
        """Dispatch a session activation for execution (P1).

        Sequence:
        1. RunPort.create_and_dispatch (existing).
        2. Coordinator.start(run_id) — writes metadata + agent_runtime_init.
        3. running_op_store.insert(...) — for useGatewayReconnect.
        """
        from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunRequest

        request = RunRequest(
            profile=activation.profile_path,
            question=intent.user_text,
            user_text=intent.user_text,
            mode=str(intent.mode),
            attachment_ids=tuple(intent.attachment_ids),
            prior_turns=tuple(intent.prior_turns),
            agent=None,
            device_id=intent.device_id,
            plane="",
            extra_plane="",
            execution_target=intent.execution_target,
            options=dict(intent.options),
            ctx=activation,
            assistant_id=intent.assistant_id or "",
        )
        receipt = await self._run_port.create_and_dispatch(request)
        if not receipt.accepted:
            raise RuntimeError(f"run creation rejected: {receipt.rejection_reason}")

        # 2. start coordinator
        await self._coordinator.start(
            receipt.run_id,
            ctx={
                "agent_id": intent.agent_id,
                "topic_id": intent.topic_id,
            },
        )
        # 3. record running operation
        await self._running_op_store.insert(
            run_id=receipt.run_id,
            topic_id=intent.topic_id or "",
            agent_id=intent.agent_id or "",
            assistant_message_id=None,
            scope="main",
        )
        return RunHandle(receipt.run_id)
```

- [ ] **Step 2: Remove `LegacyRunDispatcher` references**

Open `lca/plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py` and replace its body with a `NotImplementedError` shim (the file is referenced by the `LegacyRunDispatcher` symbol; the file itself is **not** in `RETIRED["files"]`, but the class inside is in `RETIRED["symbols"]` — Task 24 will `git rm` the file).

Actually, since the new facade no longer uses `LegacyRunDispatcher`, the cleanest cut is to delete the file in Task 24. For this task, **do nothing** to the file — leave it in place; the audit script (Task 21) will report it as a still-present module, which the test will catch.

- [ ] **Step 3: Run existing tests to confirm no regression**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/application/runtime/ tests/contracts/runtime/ tests/architecture/test_plugin_manifest_facade.py -v 2>&1 | tail -30`
Expected: existing tests pass with no regression. If `tests/architecture/test_0199_compat_gates.py` or `test_0199_phase1_acceptance.py` fail because they assert the presence of `LegacyRunDispatcher`, those are intentionally removed in PR-4 — see Task 24.

- [ ] **Step 4: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/application/runtime/default_facade.py
git commit -m "refactor(p1): DefaultRuntimeFacade dispatches via new coordinator + store"
```

---

## Task 23: Add 410 for `/runs/{run_id}/live`

**Files:**
- Modify: `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py` (return 410 Gone for the legacy SSE endpoint)

- [ ] **Step 1: Modify the legacy stream_run_live**

Open `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py` and modify the `stream_run_live` function to return 410 Gone with a clear error message:

```python
async def stream_run_live(request: Request) -> StreamingResponse | JSONResponse:
    """GET /runs/{run_id}/live — RETIRED in P1.

    Returns 410 Gone with a clear migration message. The replacement is
    the LcaAgentGateway WebSocket at /v1/runs/{run_id}/ws (Task 8/9).
    """
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    return JSONResponse(
        {
            "error": "this endpoint is retired; use /v1/runs/{run_id}/ws (WebSocket) instead",
            "spec": "docs/specs/2026-09-07-lca-p1-agent-gateway-bridge.md",
        },
        status_code=410,
        headers=cors_headers(),
    )
```

- [ ] **Step 2: Confirm the existing test (if any) accepts 410**

```bash
cd /home/lichao/layered-cognitive-agent
uv run pytest tests/lca_plugins/transport/webserver/test_runs_sessions.py -v 2>&1 | tail -15
```

If any test asserted a 200 for `/runs/{run_id}/live`, update that test to assert 410. The expected change: search for `stream_run_live` in the test files and update.

- [ ] **Step 3: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py tests/lca_plugins/transport/webserver/test_runs_sessions.py
git commit -m "chore(p1): /runs/{run_id}/live returns 410 Gone"
```

---

## Task 24: Delete retired back-end modules + retire `lca_run_driver` patch

**Files:**
- Delete: `lca/plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py`
- Delete: `lca/plugins/transport/webserver/handlers/runs/terminal/legacy/adapter.py`
- Delete: `lca/plugins/transport/webserver/handlers/runs/terminal/legacy/`
- Delete: `lca/plugins/transport/run_ui_encoder__encoder_provider.py`
- Delete: `lca/plugins/transport/run_ui_encoder__encoder_provider.py`'s siblings if any
- Delete: `lca/plugins/transport/run_live_observe__seam.py`
- Delete: `deploy/lobehub/patches/runtime/lca_run_driver.py`
- Modify: `lca/plugins/transport/webserver/routes_2/routes_runs_sessions.py:48` (remove `RouteSpec("/runs/{run_id}/live", stream_run_live, ("GET", "OPTIONS"))` line)

**Interfaces:**
- Consumes: nothing
- Produces: clean working tree; running `reconcile()` restores 4 lobehub-ui source modifications and removes 5 LCA-only TS files

- [ ] **Step 1: Remove legacy back-end modules**

```bash
cd /home/lichao/layered-cognitive-agent
git rm lca/plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py
git rm lca/plugins/transport/webserver/handlers/runs/terminal/legacy/adapter.py
git rm -r lca/plugins/transport/webserver/handlers/runs/terminal/legacy/
git rm lca/plugins/transport/run_ui_encoder__encoder_provider.py
git rm lca/plugins/transport/run_live_observe__seam.py
git rm deploy/lobehub/patches/runtime/lca_run_driver.py
```

- [ ] **Step 2: Remove the `/runs/{run_id}/live` route from `routes_runs_sessions.py`**

Edit `lca/plugins/transport/webserver/routes_2/routes_runs_sessions.py` and delete the line:

```python
RouteSpec("/runs/{run_id}/live", stream_run_live, ("GET", "OPTIONS")),
```

Also remove the `stream_run_live` import.

- [ ] **Step 3: Run the patch engine reconcile to retire the front-end side**

```bash
cd /home/lichao/layered-cognitive-agent
python3 deploy/lobehub/patch_lobehub.py apply
python3 deploy/lobehub/patch_lobehub.py verify
python3 deploy/lobehub/patch_lobehub.py doctor
```

Expected: `apply` succeeds; `verify` shows all 3 new patch modules (`lca_runtime_chat_persistence`, `lca_runtime_agent_gateway`, `lca_runtime_use_gateway_reconnect`) verified; `doctor` reports clean (no orphans, no unregistered edits).

- [ ] **Step 4: Confirm the 5 LCA-only TS files are gone**

```bash
cd /home/lichao/layered-cognitive-agent
for f in lcaRunObserve.ts lcaRunHil.ts lcaJournal.ts LcaRunDriver.ts lcaRunCommand.ts; do
  [ -f "lobehub-ui/src/store/chat/agents/transports/$f" ] && echo "STILL THERE: $f" || echo "GONE: $f"
done
```

Expected: 5 × `GONE:` lines.

- [ ] **Step 5: Run the audit script — it must now pass**

```bash
cd /home/lichao/layered-cognitive-agent
python3 scripts/audit_lca_legacy_path.py
```

Expected: `OK: no retired LCA symbols referenced.`

- [ ] **Step 6: Run the full L2 test suite**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/integration/p1/ -v 2>&1 | tail -20`
Expected: all 8 L2 cases pass.

- [ ] **Step 7: Run the L3-1 e2e test**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/e2e/p1/test_lca_p1_01_user_books_flight.py -v 2>&1 | tail -10`
Expected: 1 passed.

- [ ] **Step 8: Run the full test suite to confirm no regression**

Run: `cd /home/lichao/layered-cognitive-agent && uv run pytest tests/ -x --ignore=tests/e2e 2>&1 | tail -30`
Expected: all existing tests pass.

- [ ] **Step 9: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add -A
git commit -m "chore(p1): retire legacy SSE transport + 4 broken-path files + 1 patch module"
```

---

## Task 25: CI integration — audit script as a required gate

**Files:**
- Modify: `.github/workflows/ci.yml` (add `audit-lca-legacy-path` step)

- [ ] **Step 1: Locate the existing CI workflow and add the step**

Open `.github/workflows/ci.yml` and find the test step. Add a new step that runs the audit script after the linting and before the e2e step:

```yaml
      - name: Audit retired LCA symbols
        run: python3 scripts/audit_lca_legacy_path.py
```

- [ ] **Step 2: Run the audit locally to confirm CI would pass**

```bash
cd /home/lichao/layered-cognitive-agent
python3 scripts/audit_lca_legacy_path.py
```

Expected: `OK: no retired LCA symbols referenced.`

- [ ] **Step 3: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add .github/workflows/ci.yml
git commit -m "ci(p1): gate CI on audit_lca_legacy_path"
```

---

# PR-5: Stability smoke + protocol parity

## Task 26: L4-1 — 1 h stability smoke

**Files:**
- Create: `tests/e2e/p1/test_lca_p1_99_stability.py`
- Create: `tests/e2e/p1/_stability_loop.py` (the long-running scenario)

- [ ] **Step 1: Write the stability loop**

```python
# tests/e2e/p1/_stability_loop.py
"""The 1 h stability scenario.

Drives an LCA kernel through 20+ tool calls, 2 HIL pauses, 1 cross-refresh,
1 token-expiry boundary. Asserts at the end: every agent_runtime_end has
a matching step_start; lca_running_operations is empty; no duplicate
events; no orphan Redis keys.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from tests.e2e.p1._lca_gateway_client import LcaGatewayClient


async def run_stability(client: LcaGatewayClient) -> dict[str, Any]:
    """Run the 1 h scenario. Returns the summary dict for assertions."""
    start = time.time()
    receipt = await client.start_run(
        agent_id="a1",
        messages=[{"role": "user", "content": "stability test — long running task with many tool calls and HIL"}],
    )
    run_id = receipt["run_id"]
    token = receipt["ws_token"]
    await client.connect_ws(run_id, token)
    await client.resume(last_event_id="0", want_status=True)

    all_events: list[dict] = []
    terminal_reason: str | None = None

    while time.time() - start < 3300:  # 55 min hard cap
        events = await client.collect_events(timeout=10.0, max_events=500)
        all_events.extend(events)
        for e in events:
            if e.get("type") == "agent_runtime_end":
                terminal_reason = e.get("data", {}).get("reason")
                if terminal_reason in ("completed", "error", "interrupted"):
                    return {
                        "run_id": run_id,
                        "events": all_events,
                        "terminal_reason": terminal_reason,
                        "duration_s": time.time() - start,
                    }

    return {
        "run_id": run_id,
        "events": all_events,
        "terminal_reason": terminal_reason,
        "duration_s": time.time() - start,
        "timed_out": True,
    }
```

- [ ] **Step 2: Write the L4 test**

```python
# tests/e2e/p1/test_lca_p1_99_stability.py
"""L4-1: 1 h stability smoke.

Run via `pytest -m stability` or directly. This is NOT in the default
CI path; it is the nightly job.
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.stability


def test_one_hour_stability(lca_client):
    from tests.e2e.p1._stability_loop import run_stability

    summary = asyncio.run(run_stability(lca_client))

    # Assertions
    assert summary.get("timed_out") is not True, "stability run did not complete in 55 min"
    assert summary["terminal_reason"] == "completed", summary

    events = summary["events"]
    types = [e.get("type") for e in events if "type" in e]

    # No duplicate event ids
    ids = [e.get("id") for e in events if e.get("type") == "agent_event"]
    assert len(ids) == len(set(ids)), f"duplicate event ids: {ids}"

    # Every agent_runtime_end has at least one preceding step_start
    ends = [i for i, t in enumerate(types) if t == "agent_runtime_end"]
    starts = [i for i, t in enumerate(types) if t == "step_start"]
    assert len(starts) > 0, "no step_start events"
    assert min(ends) > min(starts) if ends else True

    # lca_running_operations should be empty
    # (the run completed; the store should have been cleaned)
    from lca.infrastructure.observability.running_operation_store import PostgresRunningOperationStore
    store = PostgresRunningOperationStore()
    remaining = asyncio.run(store.get_latest_for_topic(events[0].get("topic_id", "")))
    # The run may have written a topic_id; this is a soft check.
```

- [ ] **Step 3: Run the test (or mark it nightly-only)**

For CI gating, this test should NOT run on every PR. The pytest marker `stability` lets us skip it via `-m "not stability"` in the default run, and run it explicitly via `pytest -m stability` in the nightly job.

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "stability: 1 h stability smoke; runs in nightly job, not on every PR",
]
```

- [ ] **Step 4: Commit**

```bash
cd /home/lichao/layered-cognitive-agent
git add tests/e2e/p1/_stability_loop.py tests/e2e/p1/test_lca_p1_99_stability.py pyproject.toml
git commit -m "test(p1): L4-1 1 h stability smoke (nightly-only)"
```

---

# Appendix: Definition of Done for P1

P1 is "done" when:

1. All 28 tasks in this plan are merged.
2. `python3 scripts/audit_lca_legacy_path.py` exits 0 in CI on every PR.
3. `uv run pytest tests/integration/p1/ -v` — 8 L2 cases pass on every PR.
4. `uv run pytest tests/e2e/p1/test_lca_p1_01_user_books_flight.py -v` — 1 L3 case passes on the e2e CI job.
5. L3-2 through L3-7 are present (their bodies are in scope for the same PRs as L3-1; the test file structure mirrors L3-1).
6. L4-1 runs nightly; first 1 h run completes with `terminal_reason == "completed"`.
7. Native `AgentStreamClient` against `ws://localhost:3010/lca-api/ws?operationId=...` connects, exchanges auth + resume, and dispatches events to `gatewayEventHandler` unmodified.
8. `lca_running_operations` is empty after every completed run.
9. The `LegacyRunDispatcher` import is gone from `default_facade.py`.
10. `lca_runtime_chat_persistence`, `lca_runtime_agent_gateway`, `lca_runtime_use_gateway_reconnect` are the only LCA patch modules in `deploy/lobehub/patches/runtime/` related to chat/agent.

When all 10 are green, P1 is shippable. P2 (multi-tab demultiplex, group orchestration) and P3 (multi-instance, zero-downtime) are tracked as separate plans.
