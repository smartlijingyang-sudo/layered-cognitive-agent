"""Inspect a resolved plugin tree (``lca-ops inspect-tree``) — ADR-0061."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cordis import Context

from lca.harness.profile.boot_products import resolved_profile_from_scope
from lca.harness.profile.resolve import dump_resolved


async def inspect_profile_tree(profile_path: Path | str) -> Context:
    """Boot a profile and return the resolved cordis.Context."""

    from lca.harness.profile.boot import boot_profile

    return await boot_profile(profile_path)


def format_plugin_tree(ctx: Context, *, profile: str) -> str:
    """Render resolved Manifest rows: id, module, kind, layer, config sources."""
    resolved = resolved_profile_from_scope(ctx)
    lines = [f"Profile: {profile}"]
    if resolved is None:
        lines.append("no ResolvedProfile on context")
        return "\n".join(lines) + "\n"

    dumped = dump_resolved(resolved, redact=True)
    lines.append(f"manifest_hash: {dumped['manifest_hash']}")
    lines.append(f"plugins: {len(dumped['plugins'])}  dag_edges: {len(dumped['dag_edges'])}")
    lines.append("")
    for row in dumped["plugins"]:
        status = "disabled" if row["disabled"] else "active"
        lines.append(
            f"  {row['id']}  [{status}]  kind={row['kind']} layer={row['layer']}  "
            f"module={row['module']}"
        )
        if row["provides"]:
            lines.append(f"    provides: {', '.join(row['provides'])}")
        if row["requires"]:
            lines.append(f"    requires: {', '.join(row['requires'])}")
        if row["config_sources"]:
            src = ", ".join(f"{k}←{v}" for k, v in sorted(row["config_sources"].items())[:4])
            lines.append(f"    config_from: {src}")
    return "\n".join(lines) + "\n"


def format_capability_graph(
    ctx_or_meta: Context | dict[str, Any] | None = None,
    *,
    profile: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the derived capability graph (PR12.G.2 / ADR-0061 dump)."""
    payload: dict[str, Any] = {}
    if isinstance(ctx_or_meta, dict):
        payload = dict(ctx_or_meta)
    elif meta is not None:
        payload = dict(meta)
    elif isinstance(ctx_or_meta, Context):
        resolved = resolved_profile_from_scope(ctx_or_meta)
        if resolved is not None:
            dumped = dump_resolved(resolved, redact=True)
            return {
                "profile": profile or dumped["profile"],
                "manifest_hash": dumped["manifest_hash"],
                "nodes": [
                    {
                        "id": row["id"],
                        "kind": row["kind"],
                        "layer": row["layer"],
                        "provides": row["provides"],
                        "requires": row["requires"],
                        "disabled": row["disabled"],
                    }
                    for row in dumped["plugins"]
                ],
                "edges": [list(e) for e in dumped["dag_edges"]],
            }
        payload = {}
    return _normalize_capability_dict(payload)


def format_capability_graph_from_legacy(legacy_obj: Any, *, profile: str = "") -> dict[str, Any]:
    """Adapt a legacy ``manifest`` (or any object with ``kind`` / ``seam_key``)."""
    kind = getattr(legacy_obj, "kind", None) or ""
    seam_key = getattr(legacy_obj, "seam_key", None) or ""
    layer = getattr(legacy_obj, "layer", None) or kind
    graph = _normalize_capability_dict(
        {
            "name": str(getattr(legacy_obj, "name", "") or seam_key or kind),
            "layer": str(layer or ""),
            "implements": list(getattr(legacy_obj, "implements", []) or []),
            "capabilities": [seam_key] if seam_key else [],
            "side_effects": [],
            "policy_class": "",
            "profile": profile,
        }
    )
    graph["seam_key"] = seam_key
    graph["kind"] = kind
    return graph


def why_capability(ctx: Context, capability: str) -> str:
    """Explain who owns a capability and who requires it."""
    resolved = resolved_profile_from_scope(ctx)
    if resolved is None:
        return f"capability {capability!r}: no ResolvedProfile on context"
    owners = [
        p
        for p in resolved.plugins
        if capability in p.definition.provided_capability_keys and not p.disabled
    ]
    consumers = [
        p
        for p in resolved.plugins
        if capability in p.definition.required_capability_keys and not p.disabled
    ]
    lines = [f"capability: {capability}"]
    if not owners:
        lines.append("owner: MISSING")
    else:
        for owner in owners:
            lines.append(
                f"owner: {owner.id} ({owner.module}) kind={owner.definition.spec.kind.value} "
                f"layer={owner.definition.spec.layer}"
            )
    if consumers:
        lines.append("required by:")
        for consumer in consumers:
            lines.append(f"  - {consumer.id} @ {consumer.source}")
    else:
        lines.append("required by: (none in this profile)")
    return "\n".join(lines)


def why_plugin(ctx: Context, plugin_id: str) -> str:
    """Explain why a plugin was started (reverse dependency + source)."""
    resolved = resolved_profile_from_scope(ctx)
    if resolved is None:
        return f"plugin {plugin_id!r}: no ResolvedProfile on context"
    target = next((p for p in resolved.plugins if p.id == plugin_id), None)
    if target is None:
        return f"plugin {plugin_id!r}: not in resolved profile"
    dependents = [a for a, b in resolved.dag_edges if a == plugin_id]
    lines = [
        f"plugin: {plugin_id}",
        f"module: {target.module}",
        f"source: {target.source}",
        f"kind/layer: {target.definition.spec.kind.value}/{target.definition.spec.layer}",
        f"provides: {list(target.definition.provided_capability_keys)}",
        f"requires: {list(target.definition.required_capability_keys)}",
        f"test_suite: {target.definition.spec.verification.test_suite}",
        f"disabled: {target.disabled}",
        f"enables: {dependents or '(no dependents in DAG)'}",
    ]
    return "\n".join(lines)


def _normalize_capability_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(payload.get("name") or ""),
        "layer": str(payload.get("layer") or ""),
        "implements": list(payload.get("implements") or []),
        "emitted_events": list(payload.get("emitted_events") or []),
        "context_fields": list(payload.get("context_fields") or []),
        "capabilities": list(payload.get("capabilities") or []),
        "side_effects": list(payload.get("side_effects") or []),
        "policy_class": str(payload.get("policy_class") or ""),
        **{
            k: v
            for k, v in payload.items()
            if k
            not in {
                "name",
                "layer",
                "implements",
                "emitted_events",
                "context_fields",
                "capabilities",
                "side_effects",
                "policy_class",
            }
        },
    }
