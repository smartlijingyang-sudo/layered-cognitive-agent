"""Plugin tree diagnostic renderer (for `lca-ops debug tree`)."""
from __future__ import annotations

from typing import Any


def render_tree(ctx: Any, *, show_listeners: bool = True) -> str:
    """Render a cordis Context's plugin tree as a human-readable string.

    Walks ``ctx.own_bindings`` (user-provided services) and the
    EventsService listener map (for `show_listeners=True`).
    """
    lines: list[str] = ["Plugin Tree (cordis)", "=" * 60]

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
