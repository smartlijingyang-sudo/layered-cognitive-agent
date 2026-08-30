"""Boot report — plugin inventory + capability graph.

Emitted once at gateway startup and by ``lca-ops debug tree``. Walks the
cordis Context for entries, prints one row per plugin, then prints the
provide→consume edges of the resulting graph.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cordis import Context


@dataclass(frozen=True)
class BootReport:
    profile: str
    bundles: tuple[str, ...]
    plugins: tuple[PluginRow, ...]
    edges: tuple[Edge, ...]
    elapsed_ms: float

    def format(self, *, channel: str = "boot") -> str:
        lines: list[str] = []
        lines.append(f"[lca.{channel}] profile={self.profile}  bundles=[{', '.join(self.bundles)}]")
        lines.append(f"[lca.{channel}] ━━━ {len(self.plugins)} plugins ━━━")
        for row in self.plugins:
            lines.append(_format_row(row))
        lines.append(
            f"[lca.{channel}] ━━━ capability graph: "
            f"{len(self.plugins)} nodes / {len(self.edges)} edges ━━━"
        )
        for edge in self.edges:
            lines.append(f"[lca.{channel}]   {edge.from_id} → {edge.to_id}")
        lines.append(f"[lca.{channel}] ━━━ boot ok in {self.elapsed_ms:.1f}ms ━━━")
        return "\n".join(lines)


@dataclass(frozen=True)
class PluginRow:
    plugin_id: str
    name: str
    inject: tuple[str, ...]
    provides: tuple[str, ...]
    config_summary: str
    enabled: bool


@dataclass(frozen=True)
class Edge:
    from_id: str
    to_id: str


def build_report(
    ctx: Context,
    *,
    profile: str,
    bundles: list[str],
    entries: list[Any] | None = None,
    elapsed_ms: float = 0.0,
) -> BootReport:
    """Read the booted tree and synthesize a printable report."""
    plugins, edges = _collect(ctx, entries)
    return BootReport(
        profile=profile,
        bundles=tuple(bundles),
        plugins=tuple(plugins),
        edges=tuple(edges),
        elapsed_ms=elapsed_ms,
    )


def time_call(fn: Any, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """Run ``fn(*args, **kwargs)`` and return its result + elapsed milliseconds."""
    started = time.monotonic()
    result = fn(*args, **kwargs)
    return result, (time.monotonic() - started) * 1000.0


# ── Internal ──────────────────────────────────────────────


def _collect(
    ctx: Context,
    entries: list[Any] | None,
) -> tuple[list[PluginRow], list[Edge]]:
    rows: list[PluginRow] = []
    edges: list[Edge] = []

    raw = entries if entries is not None else _iter_entries(ctx)
    for entry in raw:
        plugin_id = str(getattr(entry, "id", "") or "")
        if not plugin_id:
            continue
        config = getattr(entry, "config", None) or {}
        enabled = not (
            getattr(entry, "disabled", False)
            or (isinstance(config, dict) and config.get("disabled"))
        )
        inject = _safe_tuple(_entry_inject(entry))
        provides = _safe_tuple(_entry_provides(entry))
        config_summary = _summarize_config(config)
        rows.append(
            PluginRow(
                plugin_id=plugin_id,
                name=str(getattr(entry, "name", "") or ""),
                inject=inject,
                provides=provides,
                config_summary=config_summary,
                enabled=enabled,
            )
        )
        if enabled:
            for dep in inject:
                edges.append(Edge(from_id=dep, to_id=plugin_id))

    return sorted(rows, key=lambda r: r.plugin_id), edges


def _iter_entries(ctx: Context) -> list[Any]:
    """Read booted plugins from the Profile boot-products seam."""
    from lca.harness.profile.boot_products import resolved_profile_from_scope

    resolved = resolved_profile_from_scope(ctx)
    if resolved is None:
        return []
    return [plugin for plugin in resolved.plugins if not plugin.disabled]


def _entry_inject(entry: Any) -> Any:
    definition = getattr(entry, "definition", None)
    if definition is not None:
        return getattr(definition, "requires", None)
    return getattr(entry, "inject", None)


def _entry_provides(entry: Any) -> Any:
    """Prefer Manifest provides; fall back to an explicit entry attribute."""
    definition = getattr(entry, "definition", None)
    if definition is not None:
        return getattr(definition, "provides", None)
    return getattr(entry, "provides", None)


def _safe_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def _summarize_config(config: Any) -> str:
    if not isinstance(config, dict) or not config:
        return ""
    parts: list[str] = []
    for key in sorted(config):
        val = config[key]
        parts.append(f"{key}: {_redact(key, val)}")
    return ", ".join(parts)


_SECRET_HINTS = ("api_key", "apikey", "password", "secret", "token")


def _redact(key: str, value: Any) -> str:
    lowered = key.lower()
    if any(hint in lowered for hint in _SECRET_HINTS):
        s = str(value)
        if len(s) <= 6:
            return "***"
        return f"{s[:3]}***{s[-3:]}"
    if isinstance(value, str):
        return value
    return repr(value)


def _format_row(row: PluginRow) -> str:
    mark = "✓" if row.enabled else "✗"
    inject = f"inject=[{', '.join(row.inject)}]" if row.inject else "inject=[]"
    provides = f"provides=[{', '.join(row.provides)}]" if row.provides else "provides=[]"
    cfg = f"  config={{{row.config_summary}}}" if row.config_summary else ""
    return f"[lca.boot] {mark} {row.plugin_id:<40s} {inject:<24s} {provides}{cfg}"
