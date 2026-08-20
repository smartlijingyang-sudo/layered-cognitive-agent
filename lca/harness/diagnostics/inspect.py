"""Inspect a resolved plugin tree (``lca-ops inspect-tree``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cordis import Context


async def inspect_profile_tree(profile_path: Path | str) -> Context:
    """Boot a profile and return the resolved cordis.Context."""

    from lca.harness.profile.boot import boot_profile

    return await boot_profile(profile_path)


def format_plugin_tree(ctx: Context, *, profile: str) -> str:
    """Render a human-readable plugin tree dump from a cordis Context.

    Inspects the Context's fiber for entries and dumps them as a
    human-readable listing. The full implementation is deferred to Chunk 6
    (lca-ops debug tree); this stub returns a minimal summary.
    """
    lines = [
        f"Profile: {profile}",
        f"Plugin count: {sum(1 for k in dir(ctx) if not k.startswith('_'))}",
        "",
    ]
    lines.append("(Detailed plugin tree dump: see Chunk 6 lca-ops debug tree)")
    lines.append("")
    return "\n".join(lines)


def format_capability_graph(
    ctx_or_meta: Context | dict[str, Any] | None = None,
    *,
    profile: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the derived capability graph (PR12.G.2).

    Accepts either a single ``PluginMeta`` dict (test path) or a
    cordis ``Context`` (production ``inspect-tree`` path).  Aggregates
    implements / emitted_events / context_fields / capabilities /
    side_effects / policy_class fields.

    Output structure::

        {
            "name": str,
            "layer": str,
            "implements": list,
            "emitted_events": list,
            "context_fields": list,
            "capabilities": list,
            "side_effects": list,
            "policy_class": str,
        }
    """
    payload: dict[str, Any] = {}
    if isinstance(ctx_or_meta, dict):
        payload = dict(ctx_or_meta)
    elif meta is not None:
        payload = dict(meta)
    elif isinstance(ctx_or_meta, Context):
        plugins_meta = _collect_plugin_meta(ctx_or_meta)
        if plugins_meta:
            payload = dict(plugins_meta[0])
        else:
            legacy = _legacy_plugin_entries(ctx_or_meta)
            payload = legacy[0] if legacy else {}
    return _normalize_capability_dict(payload)


def format_capability_graph_from_legacy(
    legacy_obj: Any, *, profile: str = ""
) -> dict[str, Any]:
    """Adapt a legacy ``manifest`` (or any object with ``kind`` / ``seam_key``).

    Returns a graph-shape dict containing ``layer`` (from ``kind``) and
    ``seam_key`` (preserved verbatim) plus the standard capability fields.
    """
    payload = {
        "name": getattr(legacy_obj, "name", type(legacy_obj).__name__),
        "layer": getattr(legacy_obj, "kind", ""),
        "seam_key": getattr(legacy_obj, "seam_key", ""),
        "implements": [],
        "emitted_events": [],
        "context_fields": [],
        "capabilities": [],
        "side_effects": [],
        "policy_class": "",
    }
    return _normalize_capability_dict(payload)


def _normalize_capability_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure the graph dict carries the v3 PR12.G.2 standard keys."""
    return {
        "name": payload.get("name", ""),
        "layer": payload.get("layer", ""),
        "implements": list(payload.get("implements") or []),
        "emitted_events": list(payload.get("emitted_events") or []),
        "context_fields": list(payload.get("context_fields") or []),
        "capabilities": list(payload.get("capabilities") or []),
        "side_effects": list(payload.get("side_effects") or []),
        "policy_class": payload.get("policy_class", ""),
        # Legacy bridge: preserve seam_key when present so tests can
        # round-trip manifest objects (PR12.G.2 forward compatibility).
        **({"seam_key": payload["seam_key"]} if payload.get("seam_key") else {}),
    }


# ── Internal helpers ─────────────────────────────────────


def _collect_plugin_meta(ctx: Context) -> list[dict[str, Any]]:
    """Collect ``PluginMeta``-shaped payloads from registered plugins.

    Returns ``[]`` when no PluginMeta is found (legacy profile).
    """
    out: list[dict[str, Any]] = []
    try:
        for entry in _iter_plugin_entries(ctx):
            meta = getattr(entry, "meta", None)
            if isinstance(meta, dict) and meta:
                out.append(dict(meta))
    except Exception:  # noqa: BLE001
        return []
    return out


def _iter_plugin_entries(ctx: Context):
    """Yield plugin entries from the cordis Context, tolerating shape changes."""
    for attr in ("plugins", "_plugins", "entries"):
        items = getattr(ctx, attr, None)
        if items:
            yield from items
            return
    # Fallback: scan public attrs.
    for name in dir(ctx):
        if name.startswith("_"):
            continue
        value = getattr(ctx, name, None)
        if value is not None and not callable(value):
            yield value


def _legacy_plugin_entries(ctx: Context) -> list[dict[str, Any]]:
    """Legacy profile: derive a stub PluginMeta from cordis handle shapes."""
    plugins: list[dict[str, Any]] = []
    for entry in _iter_plugin_entries(ctx):
        name = getattr(entry, "name", None) or type(entry).__name__
        plugins.append(
            {
                "name": name,
                "implements": list(getattr(entry, "provides", []) or []),
                "emitted_events": list(getattr(entry, "emits", []) or []),
                "context_fields": [],
                "capabilities": [],
                "side_effects": list(getattr(entry, "effects", []) or []),
                "policy_class": "",
            }
        )
    return plugins


def _assemble_graph(
    *, profile: str, plugins: list[dict[str, Any]]
) -> dict[str, Any]:
    """Aggregate plugin payloads into a single capability graph."""
    totals = {
        "plugins": len(plugins),
        "events": sum(len(p.get("emitted_events", []) or []) for p in plugins),
        "side_effects": sum(len(p.get("side_effects", []) or []) for p in plugins),
        "capabilities": sum(len(p.get("capabilities", []) or []) for p in plugins),
    }
    return {"profile": profile, "plugins": plugins, "totals": totals}
