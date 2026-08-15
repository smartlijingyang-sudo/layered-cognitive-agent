"""Console output — human (rich) or agent (JSON).

One interface, two modes:
- Human mode: beautiful rich output with colors, icons, tables
- JSON mode: structured JSON for agent consumption

Design: Console is injected into commands, never global.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.table import Table

from lca.layer0_infra.ops.service import HealthCheck, ServiceState, ServiceStatus


@dataclass
class ConsoleConfig:
    """Console configuration."""

    json_mode: bool = False
    quiet: bool = False


class Console:
    """Unified output interface.

    Injected into commands and services. Never use print() directly.
    """

    def __init__(self, config: ConsoleConfig | None = None) -> None:
        self._config = config or ConsoleConfig()
        self._rich = RichConsole() if not self._config.json_mode else None
        self._json_output: list[dict[str, Any]] = []

    # ── Service Status ────────────────────────────────────────────────

    def service_state(self, name: str, state: ServiceState) -> None:
        """Display a service's current state."""
        if self._config.json_mode:
            self._json_output.append(
                {
                    "service": name,
                    "status": state.status.value,
                    "pid": state.pid,
                    "port": state.port,
                    "detail": state.detail,
                    "why": state.why,
                    "next_action": state.next_action,
                    "checks": [asdict(c) for c in state.checks],
                }
            )
            return

        if self._config.quiet:
            return

        icon = self._status_icon(state.status)
        detail_parts = []
        if state.pid:
            detail_parts.append(f"pid {state.pid}")
        if state.port:
            detail_parts.append(f":{state.port}")
        if state.detail:
            detail_parts.append(state.detail)

        detail_str = f" — {', '.join(detail_parts)}" if detail_parts else ""
        self._rich.print(f"{icon} [bold]{name}[/bold]{detail_str}")

        for check in state.checks:
            mark = "[green]✓[/green]" if check.ok else "[red]✗[/red]"
            self._rich.print(f"    {mark} {check.name}: {check.detail}")

        if state.why:
            self._rich.print(f"    [dim]{state.why}[/dim]")
        if state.next_action:
            self._rich.print(f"    next: [bold]{state.next_action}[/bold]")

    # ── Step Logging ──────────────────────────────────────────────────

    def step(self, message: str) -> None:
        """Log a step execution."""
        if self._config.json_mode:
            self._json_output.append({"step": message})
            return

        if self._config.quiet:
            return

        self._rich.print(f"[cyan]→[/cyan] {message}")

    # ── Verdict ───────────────────────────────────────────────────────

    def verdict(self, ok: bool, detail: str = "") -> None:
        """Display final verdict."""
        if self._config.json_mode:
            self._json_output.append({"verdict": "ready" if ok else "failed", "detail": detail})
            self._flush_json()
            return

        if ok:
            self._rich.print(f"\n[green]✅ ready[/green] {detail}")
        else:
            self._rich.print(f"\n[red]❌ failed[/red] {detail}")

    # ── Messages ──────────────────────────────────────────────────────

    def info(self, message: str) -> None:
        """Informational message."""
        if self._config.json_mode:
            self._json_output.append({"level": "info", "message": message})
            return

        if not self._config.quiet:
            self._rich.print(f"[blue]ℹ[/blue] {message}")

    def success(self, message: str) -> None:
        """Success message."""
        if self._config.json_mode:
            self._json_output.append({"level": "success", "message": message})
            return

        if not self._config.quiet:
            self._rich.print(f"[green]✓[/green] {message}")

    def warning(self, message: str) -> None:
        """Warning message."""
        if self._config.json_mode:
            self._json_output.append({"level": "warning", "message": message})
            return

        if not self._config.quiet:
            self._rich.print(f"[yellow]⚠[/yellow] {message}")

    def error(self, message: str) -> None:
        """Error message."""
        if self._config.json_mode:
            self._json_output.append({"level": "error", "message": message})
            self._flush_json()
            return

        self._rich.print(f"[red]✗[/red] {message}")

    # ── Tables ────────────────────────────────────────────────────────

    def table(self, title: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
        """Display a table."""
        if self._config.json_mode:
            self._json_output.append({"table": {"title": title, "rows": rows}})
            return

        if self._config.quiet:
            return

        table = Table(title=title, show_header=True, header_style="bold cyan")
        for col in columns:
            table.add_column(col)

        for row in rows:
            table.add_row(*[str(row.get(col, "")) for col in columns])

        self._rich.print(table)

    # ── Panel ─────────────────────────────────────────────────────────

    def next_steps(self, actions: list[str]) -> None:
        """Tell the operator exactly what to run next."""
        if not actions:
            return
        if self._config.json_mode:
            self._json_output.append({"next_steps": actions})
            return
        if self._config.quiet:
            return
        self._rich.print("\n[bold]下一步[/bold]")
        if len(actions) == 1:
            self._rich.print(f"  运行: [cyan]{actions[0]}[/cyan]")
            return
        for action in actions:
            self._rich.print(f"  [cyan]{action}[/cyan]")

    def panel(self, title: str, content: str) -> None:
        """Display a panel."""
        if self._config.json_mode:
            self._json_output.append({"panel": {"title": title, "content": content}})
            return

        if self._config.quiet:
            return

        self._rich.print(Panel(content, title=title, border_style="cyan"))

    # ── Health Checks ─────────────────────────────────────────────────

    def health_checks(self, checks: list[HealthCheck]) -> None:
        """Display a list of health checks."""
        if self._config.json_mode:
            self._json_output.append({"checks": [asdict(c) for c in checks]})
            return

        if self._config.quiet:
            return

        for check in checks:
            icon = "[green]✓[/green]" if check.ok else "[red]✗[/red]"
            detail = f" — {check.detail}" if check.detail else ""
            self._rich.print(f"  {icon} {check.name}{detail}")

    # ── Flush ─────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Flush JSON output (called at end of command)."""
        if self._config.json_mode:
            self._flush_json()

    # ── Internals ─────────────────────────────────────────────────────

    @staticmethod
    def _status_icon(status: ServiceStatus) -> str:
        """Map status to icon."""
        icons = {
            ServiceStatus.RUNNING: "[green]●[/green]",
            ServiceStatus.STOPPED: "[red]○[/red]",
            ServiceStatus.DEGRADED: "[yellow]◐[/yellow]",
            ServiceStatus.UNKNOWN: "[dim]?[/dim]",
        }
        return icons.get(status, "?")

    def _flush_json(self) -> None:
        """Output accumulated JSON and reset."""
        if self._json_output:
            print(json.dumps(self._json_output, indent=2))
            self._json_output.clear()
