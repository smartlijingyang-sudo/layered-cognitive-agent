"""Plugin tree diagnostic renderer (``lca inspect tree``)."""

from __future__ import annotations

from typing import Any


def render_tree(host: Any, *, show_effects: bool = True) -> str:
    """Render a plugin host as a human-readable tree string.

    Args:
        host: ``PluginHost`` or ``ScopedPluginHost`` instance — anything
            exposing a ``handles: dict[str, PluginHandle]`` mapping.
        show_effects: When *True* (default), include per-plugin effect count.

    Returns:
        Multi-line string representation of the plugin tree.
    """
    lines: list[str] = ["Plugin Tree", "=" * 60]

    handles: dict[str, Any] = getattr(host, "handles", {}) or {}
    if not handles:
        lines.append("  (empty — no plugins loaded)")
        return "\n".join(lines)

    for entry_id, handle in sorted(handles.items()):
        state = getattr(handle, "state", "UNKNOWN")
        # state may be an enum (PluginState.ACTIVE) — pull .value when present
        state_str = getattr(state, "value", state)

        spec = getattr(handle, "spec", None)
        provides: tuple[str, ...] | None = getattr(spec, "provides", None) if spec else None
        injected: tuple[str, ...] = getattr(handle, "injected", ()) or ()
        effect_count: int = len(getattr(handle, "effects", []))

        lines.append(f"  {entry_id}")
        lines.append(f"    state:    {state_str}")
        if provides:
            lines.append(f"    provides: {', '.join(provides)}")
        if injected:
            lines.append(f"    inject:   {', '.join(injected)}")
        if show_effects:
            lines.append(f"    effects:  {effect_count}")

    lines.append("=" * 60)
    lines.append(f"  total plugins: {len(handles)}")
    return "\n".join(lines)
