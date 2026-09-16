"""Post-restart health report — runs three checks after the kernel
supervisor reports ready, so the agent (and operator) gets one
verdict that covers the surface a boot can silently break.

Why this lives here
-------------------
``lca-ops kernel-restart`` was a one-liner ("SIGTERM → spawn → ready
probe passed"). That contract hid three classes of silent failure:

1. profile resolve / plan lift broken since the last restart
2. plugin fiber spawn failures that did not abort boot
3. ``/health`` returning a 200 with an unhealthy ``plugin.missing``
   list or ``fiber_count=0``

ADR-0119 keeps the supervisor minimal; this report is the supervising
read-only companion that tells the user what actually came up. The
report is opt-out via ``LCA_KERNEL_RESTART_QUIET=1`` for CI but always
runs in normal use.

Three phases
------------
- **boot_check** — re-run :func:`kernel_check` logic (profile resolve +
  plan lift). Pure validator, no subprocess.
- **fiber_report** — read the kernel's latest stderr and tally
  ``boot.pending_event`` lines by layer/status. Fail if any fiber
  spawned with ``status != ok``.
- **health_probe** — GET ``/health`` and verify ``status=ok`` and every
  plugin is registered.

Each phase contributes ``findings``. The report fails loud if any
finding is ``severity=error``. The supervisor's own readiness probe is
a precondition: if the kernel never came up, the report refuses to
guess and prints the supervisor's ``last_event`` instead.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

# boot.pending_event lines are emitted on stdout (structlog → root logger
# → sys.stdout when lca_kernel serve runs under the supervisor). The
# supervisor captures them in ``/tmp/lca-kernel.stdout.log``. The
# supervisor truncates this file on each ``start()`` call, so the file
# only contains events from the current run — no PID-based slicing
# needed. The legacy per-PID stderr files are written by the standalone
# ``lca_kernel serve`` path (no supervisor in front) and are not used by
# the supervisor-managed flow.
_STDOUT_LOGFILE = "/tmp/lca-kernel.stdout.log"  # noqa: S108 — supervisor-owned log path
_STDERR_LOGFILE = "/tmp/lca-kernel.stderr.log"  # noqa: S108 — supervisor-owned log path
_STDERR_GLOB = "/tmp/lca-kernel.stderr.*.log"  # noqa: S108 — supervisor-owned log dir

# Single boot.pending_event line, captured into groups.
_BOOT_EVENT_RE = re.compile(
    r"boot\.pending_event\s+duration_ms=(?P<duration_ms>\S+)\s+"
    r"event_type=(?P<event_type>\S+)\s+"
    r"kind=(?P<kind>\S+)\s+"
    r"layer=(?P<layer>\S+)\s+"
    r"plugin_id=(?P<plugin_id>\S+)\s+"
    r"status=(?P<status>\S+)"
)


@dataclass
class Finding:
    """One observation from a post-restart check."""

    phase: str
    severity: str  # "info" | "warning" | "error"
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PhaseResult:
    """Aggregate for one of boot_check / fiber_report / health_probe."""

    phase: str
    ok: bool
    duration_ms: int
    findings: list[Finding]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
        }


@dataclass
class RestartReport:
    """Top-level verdict for one restart."""

    ok: bool
    profile: str
    phases: list[PhaseResult]
    findings: list[Finding]
    duration_ms: int
    supervisor_state: str
    supervisor_last_event: str
    next_command: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "profile": self.profile,
            "duration_ms": self.duration_ms,
            "supervisor_state": self.supervisor_state,
            "supervisor_last_event": self.supervisor_last_event,
            "phases": [p.to_dict() for p in self.phases],
            "findings": [f.to_dict() for f in self.findings],
            "next_command": self.next_command,
        }


def _latest_kernel_stderr() -> Path | None:
    """Return the supervisor's stdout log, or None if missing.

    The supervisor truncates ``/tmp/lca-kernel.stdout.log`` on every
    ``start()``, so its contents are always one boot's events. Fall back
    to the legacy per-PID stderr files only when the supervisor-managed
    log does not exist (standalone ``lca_kernel serve`` flow, where
    boot.pending_event still lands on stderr).
    """
    stdout_path = Path(_STDOUT_LOGFILE)
    if stdout_path.exists():
        return stdout_path
    candidates = sorted(
        Path("/tmp").glob("lca-kernel.stderr.*.log"),  # noqa: S108 — supervisor-owned log dir
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _run_boot_check(profile: Path, findings: list[Finding]) -> PhaseResult:
    """Phase 1: profile resolve + plan lift validators.

    Mirrors :func:`lca.infrastructure.cli.commands.kernel.kernel.kernel_check`
    so the report agrees with the standalone ``kernel_check`` command.
    Wraps the validator calls in try/except so a profile that fails to
    resolve still produces a structured finding rather than a traceback.
    """
    start = time.monotonic()
    checks: list[dict[str, Any]] = []
    first_failure: dict[str, Any] | None = None

    try:
        from lca.harness.profile.resolve.resolve import resolve_profile

        resolve_profile(profile)
        checks.append({"name": "resolve", "ok": True})
    except Exception as exc:
        entry = {
            "name": "resolve",
            "ok": False,
            "error": exc.__class__.__name__,
            "reason": str(exc),
        }
        checks.append(entry)
        first_failure = entry
        findings.append(
            Finding(
                phase="boot_check",
                severity="error",
                code="profile.resolve_failed",
                message=f"profile resolve failed: {exc.__class__.__name__}",
                detail={"reason": str(exc), "profile": str(profile)},
            )
        )

    if first_failure is None:
        try:
            from lca.contracts.protocols.graph.errors import PlanLiftError
            from lca_kernel.boot.plan_validation import validate_profile_plans

            resolved = resolve_profile(profile)
            validate_profile_plans(resolved)
            checks.append({"name": "plan_lift", "ok": True})
        except PlanLiftError as exc:
            checks.append(
                {
                    "name": "plan_lift",
                    "ok": False,
                    "error": exc.__class__.__name__,
                    "reason": exc.reason,
                    "plan_id": exc.plan_id,
                    "node_id": exc.node_id,
                    "edge_id": exc.edge_id,
                    "port_name": exc.port_name,
                }
            )
            first_failure = checks[-1]
            findings.append(
                Finding(
                    phase="boot_check",
                    severity="error",
                    code="plan.lift_failed",
                    message=f"plan lift failed: {exc.reason}",
                    detail={k: v for k, v in first_failure.items() if k != "ok"},
                )
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "plan_lift",
                    "ok": False,
                    "error": exc.__class__.__name__,
                    "reason": str(exc),
                }
            )
            first_failure = checks[-1]
            findings.append(
                Finding(
                    phase="boot_check",
                    severity="error",
                    code="plan.lift_failed",
                    message=f"plan lift failed: {exc.__class__.__name__}",
                    detail={"reason": str(exc), "profile": str(profile)},
                )
            )

    duration_ms = int((time.monotonic() - start) * 1000)
    ok = first_failure is None
    if ok:
        findings.append(
            Finding(
                phase="boot_check",
                severity="info",
                code="profile.validated",
                message=f"profile validated ({len(checks)} checks passed)",
                detail={"checks": checks},
            )
        )
    return PhaseResult(
        phase="boot_check",
        ok=ok,
        duration_ms=duration_ms,
        findings=[f for f in findings if f.phase == "boot_check"],
        summary={"checks": checks, "ok": ok},
    )


def _parse_boot_pending_events(text: str) -> list[dict[str, Any]]:
    """Parse every ``boot.pending_event`` line from kernel stderr."""
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = _BOOT_EVENT_RE.search(line)
        if not m:
            continue
        out.append(m.groupdict())
    return out


def _run_fiber_report(findings: list[Finding]) -> PhaseResult:
    """Phase 2: tally plugin fiber spawn events for THIS boot.

    The supervisor truncates its stdout log on every ``start()``, so the
    file already contains exactly one boot's worth of
    ``boot.pending_event`` lines — no slicing needed. A fiber
    ``status != ok`` is an error; a missing log is also an error (the
    report cannot verify the boot surface otherwise).

    The supervisor's readiness probe fires on ``Application startup
    complete`` (uvicorn), which lands before the kernel's last
    ``boot.pending_event`` has flushed to disk. We poll the file for up
    to :data:`_FIBER_POLL_TIMEOUT_S` waiting for the count to stabilise,
    so the report reflects what actually came up rather than a snapshot
    taken mid-flush.
    """
    start = time.monotonic()
    target = _latest_kernel_stderr()
    if target is None:
        findings.append(
            Finding(
                phase="fiber_report",
                severity="error",
                code="fiber.no_stderr",
                message="no kernel stdout/stderr log found under /tmp",
                detail={"checked": [_STDOUT_LOGFILE, _STDERR_GLOB]},
            )
        )
        return PhaseResult(
            phase="fiber_report",
            ok=False,
            duration_ms=int((time.monotonic() - start) * 1000),
            findings=[f for f in findings if f.phase == "fiber_report"],
            summary={"log": None, "ok": False, "total": 0},
        )

    entries = _wait_for_boot_events(target)
    status_counter: Counter[str] = Counter()
    layer_counter: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    for entry in entries:
        status_counter[entry["status"]] += 1
        layer_counter[entry["layer"]] += 1
        if entry["status"] != "ok":
            failures.append(entry)

    duration_ms = int((time.monotonic() - start) * 1000)
    ok = not failures
    if not entries:
        findings.append(
            Finding(
                phase="fiber_report",
                severity="warning",
                code="fiber.no_events",
                message=(
                    f"no boot.pending_event lines in {target.name} "
                    f"after {_FIBER_POLL_TIMEOUT_S}s; stdout may have been "
                    "truncated before kernel wrote"
                ),
                detail={"log": str(target)},
            )
        )
        return PhaseResult(
            phase="fiber_report",
            ok=False,
            duration_ms=duration_ms,
            findings=[f for f in findings if f.phase == "fiber_report"],
            summary={
                "log": str(target),
                "total": 0,
                "by_status": dict(status_counter),
                "by_layer": dict(layer_counter),
            },
        )

    if failures:
        findings.append(
            Finding(
                phase="fiber_report",
                severity="error",
                code="fiber.failures",
                message=(
                    f"{len(failures)}/{len(entries)} plugin fibers failed to spawn"
                ),
                detail={
                    "log": str(target),
                    "failures": failures,
                },
            )
        )
    else:
        findings.append(
            Finding(
                phase="fiber_report",
                severity="info",
                code="fiber.ok",
                message=f"all {len(entries)} plugin fibers spawned ok",
                detail={"by_layer": dict(layer_counter)},
            )
        )
    return PhaseResult(
        phase="fiber_report",
        ok=ok,
        duration_ms=duration_ms,
        findings=[f for f in findings if f.phase == "fiber_report"],
        summary={
            "log": str(target),
            "total": len(entries),
            "ok": len(entries) - len(failures),
            "fail": len(failures),
            "by_status": dict(status_counter),
            "by_layer": dict(layer_counter),
        },
    )


# How long to keep polling the supervisor's stdout file for new boot
# events after readiness. Long enough to absorb the typical
# boot.pending_event tail (a few hundred events at ~ms each), short
# enough that a wedged writer fails loud instead of hanging the report.
_FIBER_POLL_TIMEOUT_S = 5.0
_FIBER_POLL_INTERVAL_S = 0.2
_FIBER_SAMPLE_COUNT = 2  # consecutive identical counts => stream is drained


def _wait_for_boot_events(path: Path) -> list[dict[str, Any]]:
    """Poll ``path`` until the boot.pending_event count is stable.

    Returns the parsed entries after the count holds steady for
    :data:`_FIBER_SAMPLE_COUNT` consecutive polls, or after the deadline.
    Stability means the writer has flushed everything it was going to
    send before the readiness probe fired; one extra sample protects
    against a writer that flushes two batches back-to-back.
    """
    deadline = time.monotonic() + _FIBER_POLL_TIMEOUT_S
    last_count = -1
    stable_runs = 0
    entries: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        text = path.read_text(encoding="utf-8", errors="replace")
        entries = _parse_boot_pending_events(text)
        if len(entries) == last_count and entries:
            stable_runs += 1
            if stable_runs >= _FIBER_SAMPLE_COUNT:
                return entries
        else:
            stable_runs = 0
            last_count = len(entries)
        time.sleep(_FIBER_POLL_INTERVAL_S)
    return entries


def _run_health_probe(host: str, port: int, findings: list[Finding]) -> PhaseResult:
    """Phase 3: GET /health and verify the kernel's own check."""
    start = time.monotonic()
    url = f"http://{host}:{port}/health"
    body: dict[str, Any] | None = None
    error: str | None = None
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:  # noqa: S310 — URL is operator-supplied loopback host:port for /health
            raw = resp.read().decode("utf-8")
            body = cast("dict[str, Any]", json.loads(raw))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        error = f"{exc.__class__.__name__}: {exc}"

    duration_ms = int((time.monotonic() - start) * 1000)
    if error is not None:
        findings.append(
            Finding(
                phase="health_probe",
                severity="error",
                code="health.unreachable",
                message=f"GET /health failed: {error}",
                detail={"url": url},
            )
        )
        return PhaseResult(
            phase="health_probe",
            ok=False,
            duration_ms=duration_ms,
            findings=[f for f in findings if f.phase == "health_probe"],
            summary={"url": url, "ok": False, "error": error},
        )

    status = body.get("status") if body else None
    plugin = (body or {}).get("plugin", {}) or {}
    registered = plugin.get("registered")
    expected = plugin.get("expected")
    missing = plugin.get("missing") or []
    fiber_count = plugin.get("fiber_count")
    ok = (
        status == "ok"
        and registered == expected
        and not missing
        and isinstance(fiber_count, int)
        and fiber_count > 0
    )
    if ok:
        findings.append(
            Finding(
                phase="health_probe",
                severity="info",
                code="health.ok",
                message=(
                    f"/health ok (plugin {registered}/{expected}, "
                    f"fiber_count={fiber_count})"
                ),
                detail={"url": url, "body": body},
            )
        )
    else:
        findings.append(
            Finding(
                phase="health_probe",
                severity="error",
                code="health.unhealthy",
                message=(
                    f"/health returned status={status!r} plugin="
                    f"{registered}/{expected} missing={missing} "
                    f"fiber_count={fiber_count}"
                ),
                detail={"url": url, "body": body},
            )
        )
    return PhaseResult(
        phase="health_probe",
        ok=ok,
        duration_ms=duration_ms,
        findings=[f for f in findings if f.phase == "health_probe"],
        summary={
            "url": url,
            "status": status,
            "plugin_registered": registered,
            "plugin_expected": expected,
            "plugin_missing": missing,
            "fiber_count": fiber_count,
            "ok": ok,
        },
    )


def run_restart_report(
    *,
    profile: Path,
    host: str,
    port: int,
    supervisor_state: str,
    supervisor_last_event: str,
) -> RestartReport:
    """Run all three phases and assemble the final verdict.

    Skips individual phases if the kernel never came up — without
    :data:`ok` on ``/health``, fiber and health phases would only
    produce noise. Reports the supervisor's ``last_event`` instead so
    the operator sees why the kernel is not running.
    """
    start = time.monotonic()
    findings: list[Finding] = []
    phases: list[PhaseResult] = []

    # Phase 1 always runs (no kernel process required).
    boot_check = _run_boot_check(profile, findings)
    phases.append(boot_check)

    # Phases 2 & 3 require the kernel to actually be up.
    # Compare against ProgramState.RUNNING.value (lowercase, see
    # ``lca/infrastructure/cli/services/kernel/supervisor.py``) so this
    # stays in lockstep with the supervisor's enum, not a hand-typed string.
    try:
        from lca.infrastructure.cli.services.kernel.supervisor import (
            ProgramState,
        )

        running_value = ProgramState.RUNNING.value
    except ImportError:  # pragma: no cover — defensive
        running_value = "running"
    if supervisor_state != running_value:
        for phase_name in ("fiber_report", "health_probe"):
            findings.append(
                Finding(
                    phase=phase_name,
                    severity="error",
                    code="kernel.not_running",
                    message=(
                        f"supervisor state={supervisor_state!r} "
                        f"({supervisor_last_event}); skipping {phase_name}"
                    ),
                )
            )
            phases.append(
                PhaseResult(
                    phase=phase_name,
                    ok=False,
                    duration_ms=0,
                    findings=[
                        f for f in findings if f.phase == phase_name
                    ],
                    summary={"skipped": True, "reason": supervisor_last_event},
                )
            )
        next_command = (
            "./scripts/lca-ops kernel-supervisor logs --name lca_kernel_dev"
        )
    else:
        fiber_report = _run_fiber_report(findings)
        phases.append(fiber_report)
        health_probe = _run_health_probe(host, port, findings)
        phases.append(health_probe)
        next_command = None

    ok = all(p.ok for p in phases)
    duration_ms = int((time.monotonic() - start) * 1000)
    return RestartReport(
        ok=ok,
        profile=str(profile),
        phases=phases,
        findings=findings,
        duration_ms=duration_ms,
        supervisor_state=supervisor_state,
        supervisor_last_event=supervisor_last_event,
        next_command=next_command,
    )


def render_text(report: RestartReport) -> str:
    """Human-readable summary, one block per phase + a findings recap."""
    lines: list[str] = []
    verdict = "READY" if report.ok else "FAILED"
    lines.append(f"=== post-restart report · verdict={verdict} ===")
    lines.append(
        f"profile={report.profile} supervisor={report.supervisor_state} "
        f"({report.supervisor_last_event}) duration={report.duration_ms}ms"
    )
    for phase in report.phases:
        marker = "OK  " if phase.ok else "FAIL"
        lines.append(
            f"[{marker}] {phase.phase:<14} {phase.duration_ms:>5}ms  "
            f"{_format_summary(phase.summary)}"
        )
    errs = [f for f in report.findings if f.severity == "error"]
    warns = [f for f in report.findings if f.severity == "warning"]
    if errs:
        lines.append(f"\nfindings ({len(errs)} error, {len(warns)} warning):")
        for f in errs + warns:
            lines.append(f"  [{f.severity:<7}] {f.code}: {f.message}")
    if report.next_command:
        lines.append(f"\nnext_command: {report.next_command}")
    return "\n".join(lines)


def _format_summary(summary: dict[str, Any]) -> str:
    """Compact one-liner per phase summary, for the text verdict table."""
    if not summary:
        return ""
    if "checks" in summary:
        return "checks=" + ",".join(
            f"{c['name']}={c['ok']}" for c in summary["checks"]
        )
    if "by_layer" in summary:
        layers = ",".join(f"{k}={v}" for k, v in sorted(summary["by_layer"].items()))
        return f"total={summary.get('total', 0)} fail={summary.get('fail', 0)} layers=[{layers}]"
    if "url" in summary:
        if "error" in summary:
            return f"{summary['url']} error={summary['error']}"
        return (
            f"{summary['url']} status={summary.get('status')} "
            f"plugin={summary.get('plugin_registered')}/{summary.get('plugin_expected')} "
            f"missing={summary.get('plugin_missing')} "
            f"fiber_count={summary.get('fiber_count')}"
        )
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)


def should_quiet() -> bool:
    """LCA_KERNEL_RESTART_QUIET=1 → no human-readable banner (CI only)."""
    return os.environ.get("LCA_KERNEL_RESTART_QUIET") == "1"
