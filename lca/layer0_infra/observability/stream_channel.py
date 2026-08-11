"""LLM output stream channel classification (ADR-0051 Phase 2, LobeHub-aligned).

Decision JSON is never user-facing. Raw tokens use channel ``decision``;
user-visible streaming uses channel ``answer`` and is populated only by
``ResponseTextStreamExtractor`` (see ``response_text_stream.py``).
"""

from __future__ import annotations

from lca.contracts.atoms.enums import StreamChannel
from lca.layer0_infra.observability.response_text_stream import ResponseTextStreamExtractor

__all__ = ["ResponseTextStreamExtractor", "StreamChannel", "classify_output_channel"]


def classify_output_channel(accumulated: str) -> str:
    """Deprecated heuristic classifier — always returns ``decision``.

    Previously misclassified Decision JSON as ``answer`` once ``"respond"``
    appeared anywhere in the stream, leaking rationale/confidence to LobeHub.
    """
    del accumulated
    return StreamChannel.DECISION.value
