"""Project an :class:`Observation` onto model-visible ``surface/tool_result`` fields.

The tool result is a *fact* the executing boundary appends once
(ADR-0201 single append). ``derive_messages`` replays those rows into the
OpenAI ``role=tool`` messages the model reads, so the projection here
decides exactly what the model sees after a tool call.

ADR-0292 C1: external observations are wrapped in the external-content
fence — the model-visible rendering of ``Observation.content_origin``.
The fence is derived from the same mark (one source, two renderings);
internal observations pass through unfenced.

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
from lca.contracts.models.core.execution.external_content import (
    ContentOrigin,
    fence_external_content,
)


def observation_content(observation: Observation) -> str:
    """Stringify an Observation's payload for ``surface/tool_result``.

    ``Observation`` carries no ``content`` attribute — its model-visible
    data is ``payload``. Text payloads round-trip as-is; dict/list
    payloads JSON-encode with ``ensure_ascii=False`` so non-ASCII tool
    output stays readable to the model.

    ADR-0292 C1: payloads whose ``content_origin`` is
    :attr:`ContentOrigin.EXTERNAL` (the fail-closed default) are wrapped
    in the external-content fence; ``INTERNAL`` payloads pass through
    unchanged. ``getattr`` keeps duck-typed observations working.
    """
    payload = getattr(observation, "payload", None)
    if payload is None:
        text = ""
    elif isinstance(payload, str):
        text = payload
    elif isinstance(payload, (dict, list, tuple)):
        text = json.dumps(payload, ensure_ascii=False)
    else:
        text = str(payload)
    origin = getattr(observation, "content_origin", ContentOrigin.EXTERNAL)
    if origin is ContentOrigin.EXTERNAL:
        return fence_external_content(text)
    return text


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
