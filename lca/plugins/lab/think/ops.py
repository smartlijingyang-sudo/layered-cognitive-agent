from __future__ import annotations

"""Inlined lab adapter (PR-D).

Source: commit 0eb66079^:agent_lab/adapters/.py.
The lab plugin tree is the only consumer.

delete-when: lab plugin tree fuses with LCA production path.
"""

import asyncio
import importlib
import inspect
import uuid
from typing import Any

from lca.contracts.models.core.execution.decision import Decision, ToolCall


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    return {
        "decision_id": getattr(decision, "decision_id", ""),
        "action_type": getattr(decision, "action_type", ""),
        "rationale": getattr(decision, "rationale", "") or "",
        "confidence": float(getattr(decision, "confidence", 1.0) or 1.0),
        "tool_calls": [
            {
                "call_id": getattr(tc, "call_id", ""),
                "name": (getattr(tc, "tool_name", None) or getattr(tc, "name", "") or ""),
                "arguments": dict(getattr(tc, "arguments", {}) or {}),
            }
            for tc in (getattr(decision, "tool_calls", []) or [])
        ],
        "delegations": [
            getattr(d, "__dict__", d) for d in (getattr(decision, "delegations", []) or [])
        ],
        "response_text": getattr(decision, "response_text", None),
        "degraded_from": getattr(decision, "degraded_from", None),
        "extra": dict(getattr(decision, "extra", {}) or {}),
    }


def _decision_from_dict(d: dict[str, Any]) -> Decision:
    tool_calls = []
    for tc in d.get("tool_calls") or []:
        if isinstance(tc, dict):
            tool_calls.append(
                ToolCall(
                    call_id=str(tc.get("call_id") or ""),
                    tool_name=str(tc.get("name") or tc.get("tool_name") or ""),
                    arguments=dict(tc.get("arguments") or {}),
                )
            )
    return Decision(
        decision_id=str(d.get("decision_id") or f"dec_{uuid.uuid4().hex[:12]}"),
        action_type=str(d.get("action_type") or "respond"),
        rationale=str(d.get("rationale") or ""),
        confidence=float(d.get("confidence") or 1.0),
        tool_calls=tool_calls,
        response_text=d.get("response_text"),
        degraded_from=d.get("degraded_from"),
        extra=dict(d.get("extra") or {}),
    )


def _import_dotted(ref: str) -> Any:
    if ":" in ref:
        mod, _, attr = ref.partition(":")
        return getattr(importlib.import_module(mod), attr)
    return importlib.import_module(ref)


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    try:
        import nest_asyncio  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "async helper called inside a running event loop; "
            "install nest_asyncio or invoke outside a loop"
        ) from exc
    nest_asyncio.apply()
    return asyncio.run(coro)


def _call_maybe_async(fn: Any, *args: Any) -> Any:
    result = fn(*args)
    if inspect.isawaitable(result):
        return _run_async(result)
    return result


__all__ = [
    "_call_maybe_async",
    "_decision_from_dict",
    "_decision_to_dict",
    "_import_dotted",
    "_run_async",
]
