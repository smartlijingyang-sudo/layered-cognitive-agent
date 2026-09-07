"""``lca-ops doctor profile`` — Doctor facade CLI entry (ADR-0199 §5.3 / P2-08).

Per ADR-0199 §5.3 this CLI is one of three canonical doctor consumers
(CLI / CI / web). It runs the DoctorFacade (compile dry-run + plugin
shape + capability cardinality + phase graph) against a profile path
and prints the DoctorReport.

Exit codes:
  0 — Doctor found zero errors
  1 — Doctor found ≥1 errors (CI fail-closed)
  2 — Invalid input (profile path missing / unreadable)

Per I-HPC-7 the doctor is read-only: no K3 boot, no journal writes,
no network. The CLI is a pure projection of :class:`DoctorFacade`
output.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from lca.contracts.diagnostics.doctor import DoctorReport
from lca.harness.diagnostics.doctor.facade import DoctorFacade


def register(app: typer.Typer) -> None:
    """Register the ``doctor`` subcommand on the CLI app."""
    doctor_app = typer.Typer(
        help="Read-only doctor (compile dry-run + plugin shape + capability + phase graph).",
        no_args_is_help=True,
    )
    doctor_app.command(name="profile", help=_doctor_profile.__doc__ or "")(_doctor_profile)
    app.add_typer(doctor_app, name="doctor")


def _doctor_profile(
    profile_path: str = typer.Argument(
        ...,
        help="Path to the profile YAML (e.g. profiles/web-standard.yaml).",
    ),
    ci: bool = typer.Option(
        False,
        "--ci",
        help="CI mode: exit 1 on any error finding (fail-closed).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit the DoctorReport as machine-readable JSON instead of human text.",
    ),
    skip_plugin_shape: bool = typer.Option(
        False,
        "--skip-plugin-shape",
        help="Disable the DOC-PS-* pass (profile-independent, may be slow on large plugin trees).",
    ),
    skip_capability: bool = typer.Option(
        False,
        "--skip-capability",
        help="Disable the DOC-CAP-* pass.",
    ),
    skip_phase_graph: bool = typer.Option(
        False,
        "--skip-phase-graph",
        help="Disable the DOC-PG-* pass.",
    ),
) -> None:
    """Run the Doctor facade on a profile and print the report."""
    path = Path(profile_path)
    if not path.exists():
        typer.echo(f"profile not found: {path}", err=True)
        raise SystemExit(2)

    facade = DoctorFacade()
    report = facade.doctor_profile(
        path,
        include_plugin_shape=not skip_plugin_shape,
        include_capability_cardinality=not skip_capability,
        include_phase_graph=not skip_phase_graph,
    )

    if json_output:
        typer.echo(json.dumps(report.to_jsonable(), indent=2, ensure_ascii=False))
    else:
        _print_human(report)

    # Exit code: 1 if CI mode + any errors, else 0.
    if ci and report.has_errors():
        raise SystemExit(1)


def _print_human(report: DoctorReport) -> None:
    """Human-readable report rendering (default CLI output)."""
    lines: list[str] = []
    lines.append(f"profile: {report.subject}")
    if report.activation_ref:
        lines.append(f"activation_ref: {report.activation_ref}")
    lines.append("")
    lines.append(
        f"summary: {report.summary.total} findings "
        f"(errors={report.summary.errors}, warnings={report.summary.warnings}, "
        f"info={report.summary.info})"
    )
    lines.append("")

    if not report.findings:
        lines.append("(no findings)")
    else:
        for f in report.findings:
            lines.append(f"[{f.severity}] {f.code}  {f.message}")
            if f.plugin_id:
                lines.append(f"  plugin_id: {f.plugin_id}")
            lines.append(f"  remediation: {f.remediation}")
            lines.append("")

    typer.echo("\n".join(lines))


__all__ = ("register",)
