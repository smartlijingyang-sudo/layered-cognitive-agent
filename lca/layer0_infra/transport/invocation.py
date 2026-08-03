"""Single transport send-and-wait path for member invocation.

Strategies, body DELEGATE/HANDOFF, and InternalTransport handlers all
converge on AgentTransport.send_task + wait/receive — this helper is the
shared Observation-level entry so no call site reimplements the wait loop.
"""

from __future__ import annotations

from lca.contracts.decision import Observation
from lca.contracts.lifecycle import AgentCard
from lca.contracts.protocols import AgentTransport
from lca.contracts.semantic_keys import OBS_TASK_ID

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
    task_id = await transport.send_task(agent_card, subtask, refs)
    observation: Observation
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
    # Always attach task_id for observability / Result bridging.
    extra = dict(observation.extra or {})
    extra[OBS_TASK_ID] = task_id
    observation.extra = extra
    return observation
