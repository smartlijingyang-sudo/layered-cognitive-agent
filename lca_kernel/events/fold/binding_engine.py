"""Config-driven field binding for journal fold (ADR-0198 P1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

from lca.contracts.models.observability.journal.step import (
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.contracts.observability.compile.plan import (
    BindingRule,
    CompiledObservabilityPlan,
    MergeStrategy,
)
from lca_kernel.events.compile.compiler import compiled_observability_plan
from lca_kernel.events.fold.merge import merge_dataclass

_PROJECTION_ID = "journal.step_tree"


def extract_from_payload(payload: Mapping[str, Any], source: str) -> Any:
    """Extract one value; ``payload.a|payload.b`` tries alternates left-to-right."""
    for alt in source.split("|"):
        path = alt.strip()
        if not path.startswith("payload."):
            continue
        parts = path.split(".")[1:]
        cur: Any = payload
        for part in parts:
            if not isinstance(cur, Mapping):
                cur = None
                break
            cur = cur.get(part)
        if cur is None:
            continue
        if isinstance(cur, str) and not cur.strip():
            continue
        if isinstance(cur, (list, tuple, dict)) and len(cur) == 0:
            continue
        return cur
    return None


def extract_mapping(payload: Mapping[str, Any], rule: BindingRule) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in rule.extracts:
        value = extract_from_payload(payload, spec.source)
        if value is not None:
            out[spec.target_field] = value
    return out


def match_rules(
    rules: tuple[BindingRule, ...],
    execution_point: str,
    payload: Mapping[str, Any],
) -> tuple[BindingRule, ...]:
    matched: list[BindingRule] = []
    for rule in rules:
        if rule.execution_point != execution_point:
            continue
        if rule.when_objective_kind is not None and str(
            payload.get("objective_kind") or ""
        ) != rule.when_objective_kind:
            continue
        matched.append(rule)
    return tuple(sorted(matched, key=lambda r: r.precedence))


def merge_strategy_for_rules(rules: tuple[BindingRule, ...]) -> MergeStrategy:
    if not rules:
        return "replace"
    return max(rules, key=lambda r: r.precedence).merge


class JournalBindingEngine:
    """Apply compiled binding rules to journal fold frames."""

    def __init__(self, plan: CompiledObservabilityPlan | None = None) -> None:
        compiled = plan or compiled_observability_plan()
        self._rules = compiled.bindings_by_projection.get(_PROJECTION_ID, ())

    def merge_for_ep(self, execution_point: str, payload: Mapping[str, Any] | None = None) -> MergeStrategy:
        payload = payload or {}
        return merge_strategy_for_rules(match_rules(self._rules, execution_point, payload))

    def apply_tool_call(
        self,
        existing: ToolCallRecord | None,
        payload: Mapping[str, Any],
        execution_point: str,
    ) -> ToolCallRecord:
        rules = match_rules(self._rules, execution_point, payload)
        strategy = merge_strategy_for_rules(rules)
        extracted = {}
        for rule in rules:
            extracted.update(extract_mapping(payload, rule))
        incoming = ToolCallRecord(
            invocation_id=str(extracted.get("invocation_id") or ""),
            name=str(extracted.get("name") or ""),
            arguments=dict(extracted["arguments"]) if isinstance(extracted.get("arguments"), dict) else {},
            arguments_summary=str(extracted.get("arguments_summary") or ""),
        )
        result = merge_dataclass(existing, incoming, strategy)
        return cast("ToolCallRecord", result)

    def apply_tool_result(
        self,
        existing: ToolResult | None,
        payload: Mapping[str, Any],
        execution_point: str,
        *,
        ok_default: bool = True,
    ) -> ToolResult:
        rules = match_rules(self._rules, execution_point, payload)
        strategy = merge_strategy_for_rules(rules)
        extracted = {}
        for rule in rules:
            extracted.update(extract_mapping(payload, rule))
        files_raw = extracted.get("files_created") or ()
        files_tuple = (
            tuple(str(f) for f in files_raw) if isinstance(files_raw, (list, tuple)) else ()
        )
        incoming = ToolResult(
            ok=bool(extracted.get("ok")) if "ok" in extracted else ok_default,
            latency_ms=int(extracted.get("latency_ms") or 0),
            stdout_head=str(extracted.get("stdout_head") or "")[:2000],
            stdout_chars_total=int(extracted.get("stdout_chars_total") or 0),
            stdout_truncated=bool(extracted.get("stdout_truncated") or False),
            stderr=str(extracted.get("stderr") or "")[:2000],
            files_created=files_tuple,
            error=extracted.get("error"),
            delta_summary=str(extracted.get("delta_summary") or ""),
        )
        result = merge_dataclass(existing, incoming, strategy)
        return cast("ToolResult", result)

    def apply_thinking_patch(
        self,
        existing: ThinkingTrace | None,
        payload: Mapping[str, Any],
        execution_point: str,
        *,
        frame_model: str = "",
    ) -> ThinkingTrace | None:
        rules = match_rules(self._rules, execution_point, payload)
        if not rules:
            return existing
        strategy = merge_strategy_for_rules(rules)
        extracted: dict[str, Any] = {}
        for rule in rules:
            extracted.update(extract_mapping(payload, rule))

        if execution_point == "llm.request.header":
            model = str(extracted.get("model") or frame_model or "unknown")
            if existing is None:
                return ThinkingTrace(model=model, latency_ms=0, reasoning="", decision="respond")
            if strategy == "fill_empty_only" and existing.model and existing.model != "unknown":
                return existing
            return replace(existing, model=model)

        if execution_point == "phase.think.fold":
            model = str(extracted.get("model") or "")
            if not model:
                return existing
            if existing is None:
                return ThinkingTrace(model=model, latency_ms=0, reasoning="", decision="respond")
            if existing.model and existing.model != "unknown":
                return existing
            return replace(existing, model=model)

        if execution_point == "llm.call.end":
            model = str(extracted.get("model") or frame_model or "unknown")
            latency_ms = int(extracted.get("latency_ms") or 0)
            prompt_tokens = extracted.get("prompt_tokens")
            completion_tokens = extracted.get("completion_tokens")
            base = existing or ThinkingTrace(
                model=model,
                latency_ms=latency_ms,
                reasoning="",
                decision="respond",
            )
            return replace(
                base,
                model=model or base.model,
                latency_ms=latency_ms or base.latency_ms,
                prompt_tokens=int(prompt_tokens)
                if isinstance(prompt_tokens, (int, float))
                else base.prompt_tokens,
                completion_tokens=int(completion_tokens)
                if isinstance(completion_tokens, (int, float))
                else base.completion_tokens,
            )

        return existing


def header_model_from_payload(payload: Mapping[str, Any]) -> str:
    """Resolve model name from hook or cursor header payload shapes."""
    direct = extract_from_payload(payload, "payload.model")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    config = payload.get("config")
    if isinstance(config, Mapping):
        for key in ("model", "model_id"):
            val = config.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


__all__ = [
    "JournalBindingEngine",
    "extract_from_payload",
    "header_model_from_payload",
    "match_rules",
    "merge_strategy_for_rules",
]
