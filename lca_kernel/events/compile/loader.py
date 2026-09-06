"""Load observability compile yaml into typed DTOs (ADR-0198)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.observability.compile.plan import (
    BindingRule,
    EventClosureSpec,
    FieldExtractSpec,
    LayerMergePolicy,
    OutputArtifactSpec,
    ProjectionSpec,
)

_VALID_LAYERS = frozenset(
    {
        "L0_run_envelope",
        "L1_step_boundary",
        "L2_model_visible",
        "L3_evidence",
        "L4_phase_summary",
        "L5_invocation_span",
    }
)
_VALID_MERGE = frozenset({"replace", "replace_richer", "fill_empty_only", "deny_overwrite"})
_VALID_PROJECTION_KIND = frozenset(
    {"fold_reducer", "incremental_fold", "render_template", "metrics_reducer"}
)
_VALID_OUTPUT_FORMAT = frozenset({"ndjson", "json", "markdown", "dot"})


def _req_str(mapping: Mapping[str, Any], key: str, *, ctx: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{ctx}: missing or empty {key!r}")
    return value.strip()


def _opt_str(mapping: Mapping[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"expected string for {key!r}, got {type(value).__name__}")
    text = value.strip()
    return text or None


def load_global_policies(path: Path) -> tuple[LayerMergePolicy, ...]:
    if not path.is_file():
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("layer_merge_policies") or []
    if not isinstance(entries, list):
        raise ValueError(f"{path}: layer_merge_policies must be a list")
    out: list[LayerMergePolicy] = []
    for i, entry in enumerate(entries):
        ctx = f"{path} layer_merge_policies[{i}]"
        if not isinstance(entry, Mapping):
            raise ValueError(f"{ctx}: must be a mapping")
        source = _req_str(entry, "source_layer", ctx=ctx)
        target = _req_str(entry, "target_layer", ctx=ctx)
        strategy = _req_str(entry, "strategy", ctx=ctx)
        if source not in _VALID_LAYERS:
            raise ValueError(f"{ctx}: unknown source_layer {source!r}")
        if target not in _VALID_LAYERS:
            raise ValueError(f"{ctx}: unknown target_layer {target!r}")
        if strategy not in _VALID_MERGE:
            raise ValueError(f"{ctx}: unknown strategy {strategy!r}")
        out.append(
            LayerMergePolicy(
                source_layer=source,  # type: ignore[arg-type]
                target_layer=target,  # type: ignore[arg-type]
                strategy=strategy,  # type: ignore[arg-type]
            )
        )
    return tuple(out)


def load_closure_catalog(path: Path) -> tuple[EventClosureSpec, ...]:
    if not path.is_file():
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("events") or []
    if not isinstance(entries, list):
        raise ValueError(f"{path}: events must be a list")
    out: list[EventClosureSpec] = []
    for i, entry in enumerate(entries):
        ctx = f"{path} events[{i}]"
        if not isinstance(entry, Mapping):
            raise ValueError(f"{ctx}: must be a mapping")
        ep = _req_str(entry, "execution_point", ctx=ctx)
        layer = _req_str(entry, "layer", ctx=ctx)
        if layer not in _VALID_LAYERS:
            raise ValueError(f"{ctx}: unknown layer {layer!r}")
        durable = bool(entry.get("durable", False))
        producer = _req_str(entry, "producer_seam", ctx=ctx)
        consumers_raw = entry.get("consumers") or []
        if not isinstance(consumers_raw, list):
            raise ValueError(f"{ctx}: consumers must be a list")
        consumers = tuple(str(c).strip() for c in consumers_raw if str(c).strip())
        required_raw = entry.get("required_fields") or []
        if not isinstance(required_raw, list):
            raise ValueError(f"{ctx}: required_fields must be a list")
        required = tuple(str(f).strip() for f in required_raw if str(f).strip())
        out.append(
            EventClosureSpec(
                execution_point=ep,
                layer=layer,  # type: ignore[arg-type]
                durable=durable,
                producer_seam=producer,
                consumers=consumers,
                required_fields=required,
            )
        )
    return tuple(out)


def load_projection_registry(path: Path) -> tuple[ProjectionSpec, ...]:
    if not path.is_file():
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("projections") or []
    if not isinstance(entries, list):
        raise ValueError(f"{path}: projections must be a list")
    out: list[ProjectionSpec] = []
    for i, entry in enumerate(entries):
        ctx = f"{path} projections[{i}]"
        if not isinstance(entry, Mapping):
            raise ValueError(f"{ctx}: must be a mapping")
        projection_id = _req_str(entry, "id", ctx=ctx)
        kind = _req_str(entry, "kind", ctx=ctx)
        if kind not in _VALID_PROJECTION_KIND:
            raise ValueError(f"{ctx}: unknown kind {kind!r}")
        plugin_id = _req_str(entry, "plugin_id", ctx=ctx)
        state_schema = _req_str(entry, "state_schema", ctx=ctx)
        bindings_ref = _req_str(entry, "bindings_ref", ctx=ctx)
        include_raw = entry.get("input_include") or []
        if not isinstance(include_raw, list):
            raise ValueError(f"{ctx}: input_include must be a list")
        include = tuple(str(x).strip() for x in include_raw if str(x).strip())
        out.append(
            ProjectionSpec(
                projection_id=projection_id,
                kind=kind,  # type: ignore[arg-type]
                plugin_id=plugin_id,
                state_schema=state_schema,
                bindings_ref=bindings_ref,
                input_include=include,
            )
        )
    return tuple(out)


def load_binding_rules(path: Path) -> tuple[tuple, str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    projection_id = _req_str(raw, "projection_id", ctx=str(path))
    entries = raw.get("rules") or []
    if not isinstance(entries, list):
        raise ValueError(f"{path}: rules must be a list")
    out: list[BindingRule] = []
    for i, entry in enumerate(entries):
        ctx = f"{path} rules[{i}]"
        if not isinstance(entry, Mapping):
            raise ValueError(f"{ctx}: must be a mapping")
        rule_id = _req_str(entry, "id", ctx=ctx)
        match = entry.get("match")
        if not isinstance(match, Mapping):
            raise ValueError(f"{ctx}: match must be a mapping")
        ep = _req_str(match, "execution_point", ctx=f"{ctx}.match")
        when_kind = _opt_str(match, "when_objective_kind")
        target_field = _req_str(entry, "target_field", ctx=ctx)
        merge = _req_str(entry, "merge", ctx=ctx)
        if merge not in _VALID_MERGE:
            raise ValueError(f"{ctx}: unknown merge {merge!r}")
        precedence_raw = entry.get("precedence", 0)
        if not isinstance(precedence_raw, int):
            raise ValueError(f"{ctx}: precedence must be int")
        extract_raw = entry.get("extract")
        if not isinstance(extract_raw, Mapping):
            raise ValueError(f"{ctx}: extract must be a mapping")
        extracts: list[FieldExtractSpec] = []
        for target_field_name, source in extract_raw.items():
            if not isinstance(target_field_name, str) or not isinstance(source, str):
                raise ValueError(f"{ctx}: extract keys/values must be strings")
            extracts.append(FieldExtractSpec(target_field=target_field_name, source=source.strip()))
        out.append(
            BindingRule(
                rule_id=rule_id,
                execution_point=ep,
                target_field=target_field,
                extracts=tuple(extracts),
                merge=merge,  # type: ignore[arg-type]
                precedence=precedence_raw,
                when_objective_kind=when_kind,
            )
        )
    return tuple(out), projection_id


def load_output_artifacts(path: Path) -> tuple[OutputArtifactSpec, ...]:
    if not path.is_file():
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("artifacts") or []
    if not isinstance(entries, list):
        raise ValueError(f"{path}: artifacts must be a list")
    out: list[OutputArtifactSpec] = []
    for i, entry in enumerate(entries):
        ctx = f"{path} artifacts[{i}]"
        if not isinstance(entry, Mapping):
            raise ValueError(f"{ctx}: must be a mapping")
        artifact_id = _req_str(entry, "id", ctx=ctx)
        path_pattern = _req_str(entry, "path_pattern", ctx=ctx)
        fmt = _req_str(entry, "format", ctx=ctx)
        if fmt not in _VALID_OUTPUT_FORMAT:
            raise ValueError(f"{ctx}: unknown format {fmt!r}")
        schema = _req_str(entry, "schema", ctx=ctx)
        source = _req_str(entry, "source_projection", ctx=ctx)
        durable = bool(entry.get("durable_ssot", False))
        out.append(
            OutputArtifactSpec(
                artifact_id=artifact_id,
                path_pattern=path_pattern,
                format=fmt,  # type: ignore[arg-type]
                schema=schema,
                source_projection=source,
                durable_ssot=durable,
            )
        )
    return tuple(out)


def load_bindings_for_config_dir(config_dir: Path) -> dict[str, tuple[BindingRule, ...]]:
    bindings_dir = config_dir / "projections" / "bindings"
    out: dict[str, tuple[BindingRule, ...]] = {}
    if not bindings_dir.is_dir():
        return out
    for path in sorted(bindings_dir.glob("*.yaml")):
        rules, projection_id = load_binding_rules(path)
        out[projection_id] = rules
    return out


__all__ = [
    "load_binding_rules",
    "load_bindings_for_config_dir",
    "load_closure_catalog",
    "load_global_policies",
    "load_output_artifacts",
    "load_projection_registry",
]
