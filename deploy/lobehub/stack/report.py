"""Terminal report — same visual language as lca-host."""

from __future__ import annotations

from deploy.lobehub.stack.types import BoundSurface, Check, Section, StackReport, Status

_ICONS = {
    Status.OK: "✅",
    Status.MISSING: "❌",
    Status.WARN: "⚠️",
    Status.ERROR: "❌",
}
_CYAN = "\033[1;36m"
_GREEN = "\033[1;32m"
_RED = "\033[1;31m"
_YELLOW = "\033[1;33m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _color_for(status: Status) -> str:
    if status is Status.OK:
        return _GREEN
    if status is Status.WARN:
        return _YELLOW
    return _RED


def _check_line(check: Check) -> str:
    icon = _ICONS.get(check.status, "?")
    color = _color_for(check.status)
    detail = f" — {check.detail}" if check.detail else ""
    return f"  {icon} {check.name}{color}{detail}{_RESET}"


def _surface_block(surface: BoundSurface) -> list[str]:
    routes = "  ".join(
        f"{' '.join(route.methods)} {route.path}" for route in surface.routes
    ) or "(no matching live routes)"
    lines = [
        f"\n{_CYAN}[{surface.id}]{_RESET}  {surface.title}",
        f"  {_DIM}{surface.purpose}{_RESET}",
        f"  {routes}",
    ]
    if surface.probe_status is not None:
        icon = _ICONS.get(surface.probe_status, "?")
        color = _color_for(surface.probe_status)
        lines.append(f"  {icon} probe{color} — {surface.probe_detail}{_RESET}")
    elif not surface.classified:
        for route in surface.routes:
            lines.append(
                f"  {_ICONS[Status.WARN]} {route.path}  {' '.join(route.methods)}"
                f"{_YELLOW} — add a match in deploy/lobehub/stack.yaml{_RESET}"
            )
    elif not surface.routes:
        lines.append(f"  {_ICONS[Status.WARN]} no live routes matched this surface")
    else:
        lines.append(f"  {_ICONS[Status.OK]} {len(surface.routes)} live route(s)")
    return lines


def _process_lines(report: StackReport) -> list[str]:
    snap = report.process
    pid = f"pid={snap.pid}" if snap.pid else "pid=—"
    listen = f"{snap.bind}:{snap.port}" if snap.listening else f":{snap.port} closed"
    health = snap.health or {}
    llm = health.get("llm_available")
    runs = health.get("runs")
    devices = health.get("devices")
    health_bit = snap.health_error or health.get("status") or "—"
    status = Status.OK if snap.alive and snap.listening else Status.MISSING
    lines = [
        f"\n{_CYAN}[process]{_RESET}",
        _check_line(Check(name=pid, status=status, detail=listen)),
        _check_line(
            Check(
                name="public",
                status=Status.OK if snap.public_url else Status.WARN,
                detail=snap.public_url or "unresolved",
            )
        ),
        _check_line(
            Check(
                name="health",
                status=Status.OK if health else Status.WARN,
                detail=str(health_bit),
            )
        ),
    ]
    if llm is not None:
        lines.append(
            _check_line(
                Check(
                    name="llm",
                    status=Status.OK if llm else Status.WARN,
                    detail="available" if llm else "unavailable",
                )
            )
        )
    if runs is not None:
        lines.append(_check_line(Check(name="runs", status=Status.OK, detail=str(runs))))
    if devices is not None:
        lines.append(_check_line(Check(name="devices", status=Status.OK, detail=str(devices))))
    if snap.log_file:
        lines.append(_check_line(Check(name="log", status=Status.OK, detail=snap.log_file)))
    return lines


def _delta_lines(report: StackReport) -> list[str]:
    delta = report.delta
    if delta is None:
        return []
    prev = "—" if delta.previous_pid is None else str(delta.previous_pid)
    curr = "—" if delta.current_pid is None else str(delta.current_pid)
    lines = [
        f"\n{_CYAN}[this restart]{_RESET}",
        f"  reason          {delta.reason}",
        f"  pid             {prev} → {curr}",
    ]
    if delta.newer_files:
        lines.append(f"  loaded          {len(delta.newer_files)} file(s) newer than previous process")
        for rel in delta.newer_files[:20]:
            lines.append(f"    {rel}")
        extra = len(delta.newer_files) - 20
        if extra > 0:
            lines.append(f"    … +{extra} more")
    else:
        lines.append("  loaded          no watched files newer than previous process")
    return lines


def _section_lines(section: Section) -> list[str]:
    lines = [f"\n{_CYAN}[{section.title}]{_RESET}"]
    if not section.checks:
        lines.append(f"  {_DIM}(empty){_RESET}")
        return lines
    lines.extend(_check_line(check) for check in section.checks)
    return lines


def render_report(report: StackReport) -> str:
    verdict_ok = report.verdict == "ready"
    verdict_color = _GREEN if verdict_ok else _RED if report.verdict == "failed" else _YELLOW
    icon = "✅" if verdict_ok else "❌" if report.verdict == "failed" else "⚠️"
    lines = [
        f"{_CYAN}════════════════════════════════════════{_RESET}",
        f"{_CYAN}  {report.command}{_RESET}",
        f"{_CYAN}════════════════════════════════════════{_RESET}",
    ]
    lines.extend(_process_lines(report))
    for surface in report.surfaces:
        lines.extend(_surface_block(surface))
    for section in report.sections:
        lines.extend(_section_lines(section))
    lines.extend(_delta_lines(report))
    lines.append(f"\n{verdict_color}{icon} {report.verdict}{_RESET}")
    return "\n".join(lines) + "\n"


def banner(command: str, description: str) -> str:
    return (
        f"\n{_CYAN}═══ {command} ═══{_RESET}\n"
        f"{_DIM}{description}{_RESET}\n"
    )


def log(message: str) -> str:
    return f"{_CYAN}[lobehub-stack]{_RESET} {message}"
