"""Plugin tree diagnostic renderer (for `lca-ops debug tree`)."""
from __future__ import annotations

from typing import Any


def _state_value(state: Any) -> str:
    """Render a state (string or enum) as a plain label."""
    if state is None:
        return ""
    value = getattr(state, "value", None)
    if value is not None:
        return str(value)
    return str(state)


def render_tree(
    ctx: Any, *, show_listeners: bool = True, show_effects: bool = True
) -> str:
    """Render a cordis Context (or host) as a human-readable plugin tree.

    Walks either ``ctx.own_bindings`` (cordis Context shape) or
    ``ctx.handles`` (legacy Host shape).  Plugins render their id,
    state, provides, inject, and effect count when available.
    """
    lines: list[str] = ["Plugin Tree (cordis)", "=" * 60]

    handles = getattr(ctx, "handles", None)
    if isinstance(handles, dict):
        # Legacy Host API: dict[entry_id, Handle]
        total = len(handles)
        lines.append(f"  total plugins: {total}")
        if not handles:
            lines.append("  (empty — no plugins loaded)")
        else:
            lines.append("")
            for handle_id in sorted(handles):
                handle = handles[handle_id]
                state = _state_value(getattr(handle, "state", None))
                spec = getattr(handle, "spec", None)
                provides = getattr(spec, "provides", None) if spec else None
                injected = getattr(handle, "injected", None)
                effects = getattr(handle, "effects", ())
                lines.append(f"  - {handle_id}")
                lines.append(f"    state: {state}")
                if provides:
                    lines.append(f"    provides: {', '.join(provides)}")
                if injected:
                    lines.append(f"    inject: {', '.join(injected)}")
                if show_effects and effects is not None:
                    lines.append(f"    effects: {len(effects)}")
        return "\n".join(lines)

    bindings = getattr(ctx, "own_bindings", {}) or {}
    if bindings:
        lines.append(f"  Services ({len(bindings)}):")
        for name in sorted(bindings):
            value = bindings[name]
            value_repr = type(value).__name__
            lines.append(f"    - {name}: {value_repr}")
    else:
        lines.append("  (empty — no plugins loaded)")

    if show_listeners and hasattr(ctx, "events"):
        events = ctx.events
        listener_counts = {}
        for name in dir(events):
            n = len(getattr(events, "_listeners", {}).get(name, []))
            if n > 0:
                listener_counts[name] = n
        if listener_counts:
            lines.append("")
            lines.append("  Event listeners:")
            for name, count in sorted(listener_counts.items()):
                lines.append(f"    - {name}: {count} listener(s)")

    return "\n".join(lines)
