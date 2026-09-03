"""Audit scanning commands (ADR-0074 PR-0) + ADR supervision status."""

from __future__ import annotations

import json
import subprocess
import sys

import typer

from lca.infrastructure.cli.commands._shared import audit_roots, resolve_repo_root


def register(app: typer.Typer) -> None:
    """Register audit commands on the typer app."""

    @app.command(name="audit-control-surface")
    def audit_control_surface_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Scan plugins / bundles / profiles for Control Slot references."""
        from lca.harness.diagnostics.audit_control_surface import (
            format_report,
            scan_control_surface,
        )

        roots = audit_roots("lca/plugins", "bundles", "profiles")
        findings = scan_control_surface(roots)
        report = format_report(findings, json_mode=json_mode)
        sys.stdout.write(report)
        total = sum(len(v) for v in findings.values())
        raise typer.Exit(0 if total == 0 else 1)

    @app.command(name="audit-state-writers")
    def audit_state_writers_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Scan layer1-3 for direct ``state.<attr> = ...`` writes outside reducer."""
        from lca.harness.diagnostics.audit_state_writers import (
            format_report,
            scan_state_writers,
        )

        roots = audit_roots(
            "lca/cognition",
            "lca/runtime",
            "lca/agent",
        )
        findings = scan_state_writers(roots)
        report = format_report(findings, json_mode=json_mode)
        sys.stdout.write(report)
        raise typer.Exit(0 if not findings else 1)

    @app.command(name="audit-direct-commands")
    def audit_direct_commands_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Scan Body code for direct sandbox/transport calls bypassing seams."""
        from lca.harness.diagnostics.audit_direct_commands import (
            format_report,
            scan_direct_commands,
        )

        roots = audit_roots("lca/cognition/body", "lca/plugins/body")
        findings = scan_direct_commands(roots)
        report = format_report(findings, json_mode=json_mode)
        sys.stdout.write(report)
        raise typer.Exit(0 if not findings else 1)

    @app.command(name="audit-hook-attach")
    def audit_hook_attach_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Scan layers for residual hook-mounting patterns."""
        from lca.harness.diagnostics.audit_hook_attach import (
            format_report,
            scan_hook_attach,
        )

        roots = audit_roots(
            "lca/cognition",
            "lca/runtime",
            "lca/agent",
            "lca/application",
        )
        findings = scan_hook_attach(roots)
        report = format_report(findings, json_mode=json_mode)
        sys.stdout.write(report)
        raise typer.Exit(0 if not findings else 1)

    @app.command(name="audit-plugin-shape")
    def audit_plugin_shape_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Scan ``lca/plugins/`` for single-Manifest convention violations.

        三维扫描:effects 缺失 + events/* 双形态残留 + 同 id 镜像。
        与 ``check_plugin_metadata`` 的 ADR-0110 contract 面正交。
        delete-when:missing_effects → Phase C 补齐;
        dual_form_residue → Phase B 清残留;duplicate_id → Phase C 镜像合并。
        """
        repo_root = resolve_repo_root()
        if json_mode:
            check_proc = subprocess.run(
                [sys.executable, "scripts/check_plugin_shape.py", "--json"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            sys.stdout.write(check_proc.stdout)
            if check_proc.stderr.strip():
                sys.stderr.write(check_proc.stderr)
        else:
            check_proc = subprocess.run(
                [sys.executable, "scripts/check_plugin_shape.py"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            sys.stdout.write(check_proc.stderr or check_proc.stdout)
        raise typer.Exit(check_proc.returncode)

    @app.command(name="status-adr-supervision")
    def status_adr_supervision_cmd(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Print ADR-0074 supervision status (0066/0067/0068/0069/0074)."""
        repo_root = resolve_repo_root()
        check_proc = subprocess.run(
            [sys.executable, "scripts/check_adr_supervision.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        check_rc = check_proc.returncode

        if json_mode:
            sys.stdout.write(
                json.dumps(
                    {
                        "check_rc": check_rc,
                        "check_stderr": check_proc.stderr.strip(),
                        "tracker": str(
                            repo_root / "docs" / "plans" / "adr-0074-plugin-everything-tracker.md"
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n"
            )
        else:
            if check_rc == 0:
                print("ADR supervision tracker: consistent ✅")
            elif check_rc == 2:
                print("ADR supervision tracker: file missing")
            else:
                print("ADR supervision tracker: inconsistencies; details:")
                for line in check_proc.stderr.splitlines():
                    print(f"  {line}")

            print()
            print("Historical migration baseline (PR-0 → ownership):")
            route_proc = subprocess.run(
                [sys.executable, "scripts/route_legacy_patterns.py"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if route_proc.returncode == 0:
                sys.stdout.write(route_proc.stdout)
            else:
                print(f"  (route_legacy_patterns failed: rc={route_proc.returncode})")

        raise typer.Exit(0 if check_rc == 0 else 1)
