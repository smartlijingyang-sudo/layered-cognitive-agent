"""Agent 传输层 —— 进程内传输实现（对齐 A2A 异步任务模型）。

ADR-0049：``wait_result`` 在 deadline 到期时 **harvest** 成员 partial，
返回带 ``completion_quality`` 的 Observation，而不是 silent cancel + raise。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    COMPLETION_EMPTY,
    COMPLETION_FULL,
    COMPLETION_PARTIAL,
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
    OBS_COMPLETION_QUALITY,
)
from lca.contracts.models.core.budget import DEFAULT_TIMEOUT_HARVEST_GRACE_S
from lca.contracts.models.core.decision import AgentCard, Observation
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols import AgentTransport

AgentHandler = Callable[[str], Awaitable[Observation]]

_ERR_TIMEOUT = "delegate 超时"


def _fail_observation(error: str, *, failure_kind: str = FAILURE_KIND_EXECUTION) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error=error,
        extra={FAILURE_KIND: failure_kind},
    )


def _timeout_observation(*, payload: object = None) -> Observation:
    quality = COMPLETION_PARTIAL if payload else COMPLETION_EMPTY
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=payload,
        error=_ERR_TIMEOUT,
        extra={
            FAILURE_KIND: FAILURE_KIND_TRANSIENT,
            OBS_COMPLETION_QUALITY: quality,
        },
    )


def _tag_full_success(observation: Observation) -> Observation:
    if observation.success and OBS_COMPLETION_QUALITY not in (observation.extra or {}):
        extra = dict(observation.extra or {})
        extra[OBS_COMPLETION_QUALITY] = COMPLETION_FULL
        observation.extra = extra
    return observation


class InternalTransport(AgentTransport):
    """进程内 Agent 间通信传输实现。

    维护 ``_directory``（key → async handler），``send_task`` 通过
    ``asyncio.create_task`` 调度 handler。调用方优先用 ``wait_result``
    await Future；``poll_status`` / ``receive_result`` 保留以兼容统一协议。

    生命周期：调用 ``aclose()`` 取消所有未完成任务并释放资源。
    """

    protocol_name: str = "internal"

    def __init__(
        self,
        agent_directory: dict[str, AgentHandler] | None = None,
    ) -> None:
        self._directory: dict[str, AgentHandler] = dict(agent_directory or {})
        self._tasks: dict[str, asyncio.Future[Observation]] = {}

    def register_agent(self, key: str, handler: AgentHandler) -> None:
        """将一个 async handler 注册到 directory，key 通常为 agent_id 或 role。"""
        self._directory[key] = handler

    def _resolve_handler(self, agent_card: AgentCard | str) -> AgentHandler | None:
        if isinstance(agent_card, str):
            return self._directory.get(agent_card)
        if hasattr(agent_card, "agent_id"):
            handler = self._directory.get(agent_card.agent_id)
            if handler is not None:
                return handler
        if hasattr(agent_card, "role"):
            return self._directory.get(agent_card.role)
        return None

    async def send_task(
        self, agent_card: AgentCard | str, subtask: str, context_refs: list[str]
    ) -> str:
        del context_refs
        task_id = new_id("task")
        handler = self._resolve_handler(agent_card)

        if handler is None:
            loop = asyncio.get_running_loop()
            fut: asyncio.Future[Observation] = loop.create_future()
            fut.set_result(
                _fail_observation(
                    "agent not found in directory",
                    failure_kind=FAILURE_KIND_VALIDATION,
                )
            )
            self._tasks[task_id] = fut
            return task_id

        async def _safe_run() -> Observation:
            try:
                return _tag_full_success(await handler(subtask))
            except asyncio.CancelledError:
                # 成员 handler 应自行 catch 并返回 partial Observation；
                # 若仍冒泡，转为空超时结果，避免 Future 以 CancelledError 结束。
                return _timeout_observation()
            except Exception as exc:
                return _fail_observation(str(exc))

        self._tasks[task_id] = asyncio.create_task(_safe_run(), name=f"transport-{task_id}")
        return task_id

    async def poll_status(self, task_id: str) -> str:
        fut = self._tasks.get(task_id)
        if fut is None or not fut.done():
            return TaskStatus.WORKING
        try:
            obs = fut.result()
            return TaskStatus.COMPLETED if obs.success else TaskStatus.FAILED
        except Exception:
            return TaskStatus.FAILED

    async def receive_result(self, task_id: str) -> Observation:
        fut = self._tasks.get(task_id)
        if fut is None:
            return _fail_observation("task not found")
        if not fut.done():
            return _fail_observation("task still in progress")
        try:
            return fut.result()
        except Exception as exc:
            return _fail_observation(str(exc))

    async def wait_result(self, task_id: str, timeout_s: float | None = None) -> Observation:
        fut = self._tasks.get(task_id)
        if fut is None:
            return _fail_observation("task not found")
        if timeout_s is None:
            return await fut
        try:
            return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout_s)
        except asyncio.TimeoutError:
            return await self._harvest_on_timeout(task_id, fut)

    async def _harvest_on_timeout(
        self, task_id: str, fut: asyncio.Future[Observation]
    ) -> Observation:
        """deadline 到期：取消任务并收割 partial Observation。"""
        if not fut.done():
            fut.cancel()
        try:
            result = await asyncio.wait_for(fut, timeout=DEFAULT_TIMEOUT_HARVEST_GRACE_S)
            if isinstance(result, Observation):
                if result.success:
                    return result
                # 已是失败/partial：确保超时语义与 quality
                extra = dict(result.extra or {})
                extra.setdefault(FAILURE_KIND, FAILURE_KIND_TRANSIENT)
                if result.payload:
                    extra[OBS_COMPLETION_QUALITY] = COMPLETION_PARTIAL
                else:
                    extra.setdefault(OBS_COMPLETION_QUALITY, COMPLETION_EMPTY)
                result.extra = extra
                if not result.error:
                    result.error = _ERR_TIMEOUT
                return result
        except (TimeoutError, asyncio.CancelledError, asyncio.InvalidStateError):
            pass
        except Exception as exc:
            return _fail_observation(str(exc))
        finally:
            self._tasks.pop(task_id, None)
        return _timeout_observation()

    async def aclose(self) -> None:
        """取消所有未完成任务，清空 _tasks，释放资源。"""
        for _task_id, fut in list(self._tasks.items()):
            if not fut.done():
                fut.cancel()
        self._tasks.clear()
