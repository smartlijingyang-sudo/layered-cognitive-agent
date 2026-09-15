"""Project an :class:`Observation` onto model-visible ``surface/tool_result`` fields.

The tool result is a *fact* the executing boundary appends once
(ADR-0201 single append). ``derive_messages`` replays those rows into the
OpenAI ``role=tool`` messages the model reads, so the projection here
decides exactly what the model sees after a tool call.

This lives beside the other body emit projections so both consumers share
one definition:

  - ``SimpleBody.dispatch_tool_call`` — the explicit single-call seam;
  - ``effect.execute`` — the declarative graph side-effect boundary, the
    path production actually runs.

Both must stringify identically; a second copy drifted before (one used
the nonexistent ``Observation.content``, which silently produced empty
results). Structured payloads JSON-encode so the model sees coherent text
rather than ``repr({...})``.
"""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.models.core.execution.decision import Observation


def observation_content(observation: Observation) -> str:
    """Stringify an Observation's payload for ``surface/tool_result``.

    ``Observation`` carries no ``content`` attribute — its model-visible
    data is ``payload``. Text payloads round-trip as-is; dict/list
    payloads JSON-encode with ``ensure_ascii=False`` so non-ASCII tool
    output stays readable to the model.
    """
    payload = getattr(observation, "payload", None)
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (dict, list, tuple)):
        return json.dumps(payload, ensure_ascii=False)
    return str(payload)


def observation_error(observation: Observation) -> dict[str, Any] | None:
    """Project an Observation error to the writer's ``ToolError`` TypedDict.

    Returns ``None`` for a successful Observation so the surface row is
    unambiguously a result rather than an error. Failure text always
    reaches the model: a swallowed error re-opens the retry loop because
    the model sees an unanswered tool call and tries again.
    """
    if getattr(observation, "success", True):
        return None
    err = getattr(observation, "error", None)
    if err is None:
        return {"kind": "execution", "message": "unknown", "retryable": False}
    return {
        "kind": "execution",
        "message": str(err),
        "retryable": False,
    }


__all__ = ["observation_content", "observation_error"]
