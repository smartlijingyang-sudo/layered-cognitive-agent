"""Single transport send-and-wait path for member invocation."""

from __future__ import annotations

from lca.contracts.decision import Observation
from lca.contracts.lifecycle import AgentCard
from lca.contracts.protocols import AgentTransport
from lca.contracts.semantic_keys import OBS_TASK_ID
from lca.contracts.telemetry import ATTR_CALLEE_ROLE, ATTR_OK, ATTR_PROTOCOL, SpanName
from lca.layer0_infra.observability import span

_DEFAULT_TIMEOUT_S = 300.0


async def send_and_wait(
    transport: AgentTransport,
    agent_card: AgentCard | str,
    subtask: str,
    context_refs: list[str] | None = None,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Observation:
    """Send a subtask via *transport* and wait for the Observation result."""
    refs = list(context_refs or [])
    callee = (
        agent_card if isinstance(agent_card, str) else getattr(agent_card, "role", str(agent_card))
    )
    protocol = getattr(transport, "protocol_name", "unknown")

    with span(
        SpanName.TRANSPORT_REQUEST,
        **{ATTR_CALLEE_ROLE: callee, ATTR_PROTOCOL: protocol},
    ):
        task_id = await transport.send_task(agent_card, subtask, refs)

    with span(
        SpanName.TRANSPORT_RESPONSE,
        **{ATTR_CALLEE_ROLE: callee, ATTR_PROTOCOL: protocol, "task_id": task_id},
    ) as handle:
        wait = getattr(transport, "wait_result", None)
        if wait is not None and timeout_s > 0:
            waited = await wait(task_id, timeout_s)
            if not isinstance(waited, Observation):
                raise TypeError(f"wait_result must return Observation, got {type(waited).__name__}")
            observation = waited
        elif timeout_s <= 0:
            observation = Observation(
                observation_id=f"obs_{task_id}",
                success=False,
                payload=None,
                error=f"delegate 超时(deadline 已过期): task_id={task_id}",
            )
        else:
            observation = await transport.receive_result(task_id)
        handle.attributes[ATTR_OK] = observation.success
        extra = dict(observation.extra or {})
        extra[OBS_TASK_ID] = task_id
        observation.extra = extra
        return observation
