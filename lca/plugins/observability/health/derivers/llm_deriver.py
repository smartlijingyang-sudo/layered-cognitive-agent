"""``LlmDeriver`` — observe the LLM message-loop closure (PR-1 / Task 1.3).

Status rules (spec §10.4):

    ok       every tool_call id emitted in a turn has a matching
             ``role=tool`` (or ``role=user`` with tool payload)
             message in the NEXT ``llm.request.header``.
    degraded some (but not all) tool_call ids match.
    failed   zero tool_call ids match.
    unknown  no ``llm.*`` events.

Implementation note: the brief originally describes the algorithm
against ``llm.call.end.outputs.llm_response.tool_calls``. The v1
producer instead emits tool_calls inside ``assistant`` role messages
of ``llm.request.header``. The deriver therefore reads tool_call ids
from assistant messages and matches them against ``role=tool`` /
``role=user`` (with tool payload) messages in the next
``llm.request.header``. This implements B-1 detection: tool results
the model never sees (``tool_calls`` ids that never appear as
``role=tool`` in any subsequent header) become ``failed``.
"""

from __future__ import annotations

from lca.contracts.observability.health import RunHealthCondition
from lca.plugins.observability.health.derivers._spine import (
    SpineEvent,
    filter_by_ep,
    make_evidence_ref,
    parse_observed_at,
)

LLM_REQUEST_HEADER_EP: str = "llm.request.header"
LLM_CALL_END_EP: str = "llm.call.end"

#: EPs that prove the LLM message loop ran.
_LLM_PROXY_EPS: frozenset[str] = frozenset({LLM_REQUEST_HEADER_EP, LLM_CALL_END_EP})


class LlmDeriver:
    """LLM message-loop health deriver."""

    def evaluate(self, events: list[SpineEvent]) -> list[RunHealthCondition]:
        """Return one condition describing LLM-loop closure health."""
        llm_events = [e for e in events if e["execution_point"] in _LLM_PROXY_EPS]
        if not llm_events:
            return [
                RunHealthCondition(
                    type="llm",
                    status="unknown",
                    reason="llm_no_events",
                    evidence_refs=(),
                    observed_at=0.0,
                )
            ]

        headers = filter_by_ep(events, LLM_REQUEST_HEADER_EP)
        # Collect every tool_call id emitted in any assistant message across
        # all headers, then match against the union of role=tool /
        # role=user-with-tool-payload ids from every header. This catches
        # tool_calls emitted in the LAST header (no subsequent header to
        # walk forward from) — they can still be matched if any header
        # in the run answers them.
        all_call_ids: list[str] = []
        for h in headers:
            all_call_ids.extend(_extract_tool_call_ids(h))
        all_response_ids: set[str] = set()
        for h in headers:
            all_response_ids.update(_extract_response_tool_call_ids(h))

        total = len(all_call_ids)
        matched = sum(1 for cid in all_call_ids if cid in all_response_ids)

        # Vacuous: no tool_calls across all turns -> ok (no holes to detect).
        if total == 0:
            return _emit("ok", "llm_no_tool_calls", llm_events)

        if matched == total:
            return _emit("ok", "llm_tool_messages_complete", llm_events)
        if matched == 0:
            return _emit("failed", "llm_tool_messages_missing", llm_events)
        return _emit("degraded", "llm_tool_messages_partial", llm_events)


def _extract_tool_call_ids(header: SpineEvent) -> list[str]:
    """Pull ``tool_calls[*].id`` from assistant messages of a header."""
    out: list[str] = []
    msgs = header["payload"].get("messages") or []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            if isinstance(tc, dict):
                cid = tc.get("id")
                if isinstance(cid, str):
                    out.append(cid)
    return out


def _extract_response_tool_call_ids(header: SpineEvent) -> set[str]:
    """Pull the set of tool_call_ids answered in a header.

    Counts both ``role=tool`` (canonical) and ``role=user`` with a
    tool payload (some producers wrap tool results in user role).
    """
    out: set[str] = set()
    msgs = header["payload"].get("messages") or []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "tool":
            cid = m.get("tool_call_id")
            if isinstance(cid, str):
                out.add(cid)
            continue
        if role == "user":
            # Some producers put tool_result dicts inside user content.
            content = m.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        cid = item.get("tool_call_id")
                        if isinstance(cid, str):
                            out.add(cid)
    return out


def _emit(
    status: str,
    reason: str,
    evidence_events: list[SpineEvent],
) -> list[RunHealthCondition]:
    evidence = tuple(make_evidence_ref(e) for e in evidence_events)
    observed_at = max(parse_observed_at(e["ts"]) for e in evidence_events)
    return [
        RunHealthCondition(
            type="llm",
            status=status,  # type: ignore[arg-type]
            reason=reason,
            evidence_refs=evidence,
            observed_at=observed_at,
        )
    ]


__all__ = [
    "LLM_CALL_END_EP",
    "LLM_REQUEST_HEADER_EP",
    "LlmDeriver",
]
