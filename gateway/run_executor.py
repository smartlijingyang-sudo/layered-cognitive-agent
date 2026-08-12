"""后台 run 执行器 — 组装 hub（SSE + jsonl）并驱动 Team/Agent。

EventStream 替代旧 EventBus + GatewayCollector。
JSONL 落盘从 projector 变为普通 asyncio consumer。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog

from gateway.event_stream import EventStream
from gateway.llm_resolver import LLMResolver, ProductionLLMResolver
from gateway.mode_catalog import DEFAULT_MODE, SOLO_MODE_KEY
from gateway.run_registry import RunRegistry, RunSession, RunStatus
from gateway.team_factory import build_runnable_team, build_solo_agent
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY, ConversationTurn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.file_store import get_default_file_store
from lca.layer0_infra.observability import ObservabilityHub
from lca.layer0_infra.observability.policy import AttributePolicy
from lca.layer0_infra.observability.settings import ObservabilitySettings
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime
from lca.layer0_infra.search.scope import search_run_scope
from lca.layer0_infra.tools.run_attachment_scope import run_attachment_scope
from lca.layer0_infra.tools.run_finalizer import finalize_run, run_id_scope
from lca.layer0_infra.workspace import run_workspace_scope
from lca.layer4_app.api import Agent, Team

_log = structlog.get_logger(__name__)

_default_llm_resolver: LLMResolver = ProductionLLMResolver()

# Track JSONL consumer tasks to prevent GC of dangling coroutines (RUF006).
_jsonl_tasks: set[asyncio.Task[None]] = set()

# Active ObservabilityHub instances keyed by run_id.
# Set by execute_run, consumed by _finalize_run (including HIL resume via _resume_run).
_active_hubs: dict[str, ObservabilityHub] = {}


def get_llm_resolver() -> LLMResolver:
    return _default_llm_resolver


def set_llm_resolver(resolver: LLMResolver) -> None:
    global _default_llm_resolver
    _default_llm_resolver = resolver


def llm_status() -> dict[str, bool]:
    return {"llm_available": get_llm_resolver().is_available()}


# ── EventStream JournalProjector 桥 ──────────────────────────


class _EventStreamProjector(JournalProjector):
    """Journal → EventStream 桥接投影器。

    不过滤事件——所有 StampedEvent 都发布到 EventStream。
    过滤在 TimelineProjection 层（SSE consumer 侧）执行。
    JSONL consumer 也订阅 EventStream，需要完整事件。
    """

    def __init__(self, stream: EventStream) -> None:
        self._stream = stream

    def on_event(self, stamped: StampedEvent) -> None:
        self._stream.publish(stamped)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self._stream.close()


def _create_hub_for_session(session: RunSession) -> ObservabilityHub:
    """创建绑定到 session.stream 的 ObservabilityHub。

    不含 JsonlJournalProjector——JSONL 落盘由 _jsonl_consumer 后台 task 负责。
    """
    resolved = ObservabilitySettings().verbosity
    return ObservabilityHub(
        [],
        policy=AttributePolicy(resolved),
        journal_projectors=[_EventStreamProjector(session.stream)],
    )


# ── JSONL consumer ────────────────────────────────────────


async def _jsonl_consumer(queue: asyncio.Queue[StampedEvent | None], path: Path) -> None:
    """JSONL 落盘 — 一个普通 consumer，不是 projector。

    queue 已在调用前同步注册，不会丢失任何事件。
    错误处理：如果 write 失败，记录 error 日志但不 raise。
    """
    import aiofiles

    from lca.layer0_infra.observability.journal.journal_io import stamped_to_record

    try:
        async with aiofiles.open(path, "a") as f:
            while True:
                stamped = await queue.get()
                if stamped is None:
                    break
                line = json.dumps(stamped_to_record(stamped), default=str)
                await f.write(line + "\n")
    except Exception:
        _log.exception("jsonl_consumer_failed", path=str(path))


# ── Run 执行 ─────────────────────────────────────────────


async def execute_run(
    registry: RunRegistry,
    *,
    run_id: str,
    question: str,
    mode: str = DEFAULT_MODE,
) -> None:
    """在后台 task 中执行一次 team run，事件经 EventStream 广播。"""
    session = registry.get(run_id)
    if session is None:
        return
    session.status = RunStatus.RUNNING

    hub = _create_hub_for_session(session)
    _active_hubs[session.run_id] = hub
    workspace_ref: list[Any] = [None]
    success = False
    try:
        with (
            run_id_scope(session.run_id),
            run_attachment_scope(session.attachment_ids),
            run_workspace_scope(session.run_id) as workspace,
            search_run_scope(),
        ):
            workspace_ref[0] = workspace
            sandbox = resolve_sandbox()
            if sandbox is not None:
                try:
                    await bind_sandbox_runtime(
                        session.run_id,
                        sandbox,
                        get_default_file_store(),
                        session.attachment_ids,
                    )
                except Exception as exc:
                    _log.warning(
                        "sandbox_runtime_bind_failed",
                        run_id=session.run_id,
                        error=str(exc),
                    )
            llm = get_llm_resolver().resolve(mode=mode)
            runnable: Agent | Team
            if mode == SOLO_MODE_KEY:
                runnable = build_solo_agent(llm, observability=hub)
            else:
                runnable = await build_runnable_team(
                    question,
                    llm,
                    observability=hub,
                    trace_id=session.trace_id,
                    run_id=session.run_id,
                )
            run_ctx = _run_context_for_session(session)
            if isinstance(runnable, Agent):
                result = await runnable.run(question, run_ctx)
            else:
                result = await runnable.run(question)
            if result.status == TaskStatus.INPUT_REQUIRED:
                session.status = RunStatus.WAITING_INPUT
                session.snapshot = result.extra.get("state_snapshot")
                session.runnable = runnable
                session.approval_request = result.extra.get("approval_request")
                _log.info(
                    "run_paused_for_input",
                    run_id=session.run_id,
                    approval_type=session.approval_request.get("type")
                    if session.approval_request
                    else None,
                )
                return
            success = True
    except asyncio.CancelledError:
        session.cancel_requested = True
        raise
    except Exception as exc:
        session.error = f"{type(exc).__name__}: {exc}"
    finally:
        if session.status == RunStatus.WAITING_INPUT:
            registry.mark_paused(session)
        else:
            await _finalize_run(session, registry, hub, workspace_ref[0], success)


async def _finalize_run(
    session: RunSession,
    registry: RunRegistry,
    hub: ObservabilityHub | None,
    workspace: Any,
    success: bool,
) -> None:
    """统一的 run 终结逻辑。

    调用顺序由嵌套 finally 保证（不可乱）：
      1. artifact closure safety net（可失败，不影响后续）
      2. finalize_run（workspace 收尾；可失败，不影响后续）
      3. hub.close（关闭 journal + OTel；hub 为 None 时跳过）
      4. stream.close（发送 sentinel，解除所有 subscriber 阻塞）
      5. status 更新 + error 记录
      6. inflight dedup 清理
    """
    try:
        if hub is not None:
            _emit_artifact_closure_if_needed(workspace, session, hub)
        await finalize_run(session.run_id)
    except Exception:
        _log.exception("finalize_run_pre_close_failed", run_id=session.run_id)
    finally:
        try:
            if hub is not None:
                hub.close()
        finally:
            try:
                session.close_stream()
            finally:
                if session.cancel_requested:
                    session.status = RunStatus.CANCELED
                elif session.error:
                    session.status = RunStatus.FAILED
                elif success:
                    session.status = RunStatus.COMPLETED
                _active_hubs.pop(session.run_id, None)
                registry.clear_inflight(session.run_id)


def _emit_artifact_closure_if_needed(
    workspace: Any, session: RunSession, hub: ObservabilityHub
) -> None:
    """Emit artifact closure text if run produced files but didn't finish cleanly."""
    if workspace is None:
        return
    artifacts = workspace.artifacts.snapshot().artifacts
    if not artifacts:
        return
    closure = workspace.artifacts.closure_text()
    if not closure:
        return
    from lca.contracts.atoms.enums import StreamChannel
    from lca.contracts.models.observability.journal import StepTextDelta

    try:
        hub.journal.record(
            StepTextDelta(
                step=-1,
                text_delta="\n\n" + closure,
                seq=0,
                channel=StreamChannel.ANSWER.value,
            )
        )
        _log.info(
            "artifact_closure_emitted",
            run_id=session.run_id,
            artifact_count=len(artifacts),
            status=session.status.value,
        )
    except Exception:
        _log.warning(
            "artifact_closure_emit_failed",
            run_id=session.run_id,
            exc_info=True,
        )


def _run_context_for_session(session: RunSession) -> RunContext | None:
    if not session.prior_turns:
        return None
    return RunContext(
        extra={
            PRIOR_CONVERSATION_WM_KEY: [
                {"role": t.role, "content": t.content} for t in session.prior_turns
            ]
        }
    )


def create_run_session(
    registry: RunRegistry,
    *,
    question: str,
    user_text: str,
    mode: str = DEFAULT_MODE,
    attachment_ids: Sequence[str] = (),
    prior_turns: Sequence[ConversationTurn] = (),
) -> RunSession:
    """登记新 run 并装配 EventStream（SSE 广播 + JSONL 落盘）。"""
    run_id = new_id("run")
    trace_id = new_id("trace")
    jsonl_path = registry.jsonl_path_for(run_id)
    cleaned_ids = tuple(str(i).strip() for i in attachment_ids if str(i).strip())

    stream = EventStream()

    # 同步注册 JSONL consumer queue —— 在任何 publish 发生前完成注册
    from gateway.event_stream import _MAX_QUEUE

    jsonl_queue: asyncio.Queue[StampedEvent | None] = asyncio.Queue(_MAX_QUEUE)
    stream.register_subscriber(jsonl_queue)

    session = RunSession(
        run_id=run_id,
        trace_id=trace_id,
        jsonl_path=jsonl_path,
        stream=stream,
        question=question,
        user_text=user_text,
        mode=mode,
        prior_turns=tuple(prior_turns),
        attachment_ids=cleaned_ids,
    )
    registry.put(session)

    # 注册完成后再启动消费循环，保证不丢事件
    _jsonl_task = asyncio.create_task(_jsonl_consumer(jsonl_queue, jsonl_path))
    _jsonl_tasks.add(_jsonl_task)
    _jsonl_task.add_done_callback(_jsonl_tasks.discard)
    return session


def schedule_run(
    registry: RunRegistry,
    session: RunSession,
) -> asyncio.Task[Any]:
    """fire-and-forget 后台执行；task 强引用存入 session 以支持取消与 GC 安全。"""
    task = asyncio.create_task(
        execute_run(
            registry,
            run_id=session.run_id,
            question=session.question,
            mode=session.mode,
        )
    )
    session.task = task
    return task
