"""SessionCommandCarrier — HTTP-facing carrier (spec §3.4).

This module imports only harness command/projection/session contracts
plus the facade Protocol. It does not import LiveAgent or cognitive layers.

命名历史: 此 ``SessionCommandCarrier`` 与 ADR-0119 决定 4 之后的 ``kernel_serve``
LCA 后台进程 **无关**。它是 session spine (0090 / 0092) 的命令接收面,
``/v1/sessions/{id}/commands/*`` 端点背后的命令路由器。模块路径
``lca.harness.command.gateway`` 是历史命名,改它会破 4 处 import
+ 事件 ``emitter="lca.harness.command.gateway"`` wire schema 字段
(写进 JSONL journal)。完整命名空间历史映射看
``docs/adr/0119-followup-gateway-name-map.md``。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from lca.contracts.harness.act.command import (
    AgentRegistryFacade,
    ApprovalResumeCommand,
    CancelCommand,
    CommandReceipt,
    InjectCommand,
    MessageSendCommand,
    SessionCreateCommand,
    SteerCommand,
)
from lca.contracts.harness.state.projection import (
    ProjectionChange,
    ProjectionRegistry,
    ProjectionSnapshot,
)


class SessionCommandCarrier:
    """Validate → dispatch → return receipt / projection."""

    def __init__(
        self,
        agent_registry: AgentRegistryFacade,
        projection_registry: ProjectionRegistry,
    ) -> None:
        self._agent_registry = agent_registry
        self._projection_registry = projection_registry
        self._change_waiters: list[Callable[[ProjectionChange], None]] = []
        subscribe = getattr(projection_registry, "subscribe_changes", None)
        if callable(subscribe):
            subscribe(self._on_change)

    def _on_change(self, change: ProjectionChange) -> None:
        for waiter in list(self._change_waiters):
            waiter(change)

    async def handle_create_session(self, cmd: SessionCreateCommand) -> CommandReceipt:
        return await self._agent_registry.create_session(
            idempotency_key=cmd.idempotency_key,
            profile=cmd.profile,
            preset=cmd.preset,
            options=cmd.agent_options,
            session_id=cmd.session_id,
        )

    async def handle_send_message(self, cmd: MessageSendCommand) -> CommandReceipt:
        return await self._agent_registry.dispatch_message(
            session_id=cmd.session_id,
            idempotency_key=cmd.idempotency_key,
            content=cmd.content,
            role=cmd.role,
        )

    async def handle_cancel(self, cmd: CancelCommand) -> CommandReceipt:
        return await self._agent_registry.cancel(
            session_id=cmd.session_id,
            keep_inbox=cmd.keep_inbox,
        )

    async def handle_resume_approval(self, cmd: ApprovalResumeCommand) -> CommandReceipt:
        return await self._agent_registry.resume_approval(
            session_id=cmd.session_id,
            approval_id=cmd.approval_id,
            payload=cmd.payload,
            idempotency_key=cmd.idempotency_key,
        )

    async def handle_steer(self, cmd: SteerCommand) -> CommandReceipt:
        return await self._agent_registry.steer(
            session_id=cmd.session_id,
            content=cmd.content,
        )

    async def handle_inject(self, cmd: InjectCommand) -> CommandReceipt:
        return await self._agent_registry.inject(
            session_id=cmd.session_id,
            source=cmd.source,
            content=cmd.content,
        )

    async def get_snapshot(self, session_id: str, as_of_seq: int = -1) -> ProjectionSnapshot:
        snapshot = self._projection_registry.snapshot(session_id)
        if as_of_seq >= 0 and snapshot.as_of_seq > as_of_seq:
            raise ValueError(
                f"projection registry cannot serve historical snapshot at seq {as_of_seq}; "
                f"current seq is {snapshot.as_of_seq}"
            )
        return snapshot

    async def subscribe_changes(
        self, session_id: str, last_seq: int
    ) -> AsyncIterator[ProjectionChange]:
        from lca.harness.command.sse import SSEAligner

        aligner = SSEAligner(self._projection_registry)
        async for change in aligner.subscribe_with_reconnect(session_id, last_seq):
            yield change
