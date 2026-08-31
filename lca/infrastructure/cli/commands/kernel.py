"""Kernel lifecycle subcommands (ADR-0115).

Skeleton for ``lca-ops kernel {boot,serve,stop,compose}`` — the production
HMR / K8 / shutdown semantics arrive in ADR-0118. For now each subcommand
prints a "运行模式 OK" marker so the surface is wired and discoverable.

These commands intentionally do not import ``lca.cognition`` / ``lca.agent``
/ ``lca.runtime``; they stay at the ``lca-kernel`` public seam.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

import typer


def register(app: typer.Typer) -> None:
    """Register kernel subcommands on the typer app."""

    @app.command()
    def kernel_boot(
        profile_path: Path = typer.Argument(  # noqa: B008
            "profiles/web-standard.yaml",
            help="Profile YAML path to compile and boot",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="compile_profile only; skip the actual boot",
        ),
    ) -> None:
        """Boot a profile (no webserver transport)."""
        if dry_run:
            _kernel_compile_dry_run(profile_path)
            return
        _kernel_boot(profile_path)

    @app.command()
    def kernel_serve(
        profile_path: Path = typer.Argument(  # noqa: B008
            "profiles/web-standard.yaml",
            help="Profile YAML path to boot + serve via uvicorn",
        ),
        host: str = typer.Option("127.0.0.1", "--host", help="uvicorn host"),
        port: int = typer.Option(8765, "--port", help="uvicorn port"),
    ) -> None:
        """Boot kernel + webserver transport (uvicorn-style entry)."""
        typer.echo(f"运行模式 OK · kernel_serve profile={profile_path} host={host} port={port}")
        typer.echo(
            "  full HMR + K8 wiring lands in ADR-0118; for now run "
            "'uvicorn gateway.app:create_app --factory' instead."
        )

    @app.command()
    def kernel_stop() -> None:
        """Graceful shutdown of the running kernel."""
        typer.echo("运行模式 OK · kernel_stop (full shutdown via ADR-0118)")

    @app.command()
    def kernel_compose(
        profile_path: Path = typer.Argument(  # noqa: B008
            "profiles/web-standard.yaml",
            help="Profile YAML path to compile and dump",
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit canonical JSON"),
    ) -> None:
        """Dump CompiledRunPlan as YAML/JSON for diff/audit."""
        plan = _kernel_compile_dry_run(profile_path, return_plan=True) or {}
        if as_json:
            typer.echo(json.dumps(plan, default=str, indent=2))
        else:
            typer.echo(f"compiled: profile={profile_path} keys={sorted(plan.keys())}")


def _kernel_compile_dry_run(
    profile_path: Path,
    *,
    return_plan: bool = False,
) -> dict[str, object] | None:
    """Compile a profile without booting — for ``--dry-run`` / ``compose``."""
    from lca.harness.profile.resolve import resolve_profile
    from lca_kernel import compile_profile

    resolved = resolve_profile(profile_path)
    plan = compile_profile(resolved)
    serialized = _serialize_plan(plan)
    if return_plan:
        return serialized
    typer.echo(
        f"运行模式 OK · kernel_compile profile={profile_path} "
        f"plugins={serialized.get('plugin_count', '?')}"
    )
    return None


def _kernel_boot(profile_path: Path) -> None:
    """Compile + boot a profile. Prints a marker; full shutdown is ADR-0118."""
    from lca_kernel import run_kernel, stop_kernel

    ctx = run_kernel(profile_path)
    plugin_count = len(getattr(ctx, "_plugins", {}) or {})
    typer.echo(f"运行模式 OK · kernel_boot profile={profile_path} plugins={plugin_count}")
    typer.echo("  press Ctrl+C to stop (full HMR lands in ADR-0118)")
    try:
        # Block until SIGINT; production wiring replaces this with signal handlers.
        import signal

        signal.pause()
    except KeyboardInterrupt:
        typer.echo("kernel_stop starting…")
    finally:
        # stop_kernel may become a coroutine in future revisions; await if so.
        import asyncio

        result = stop_kernel(ctx)
        if asyncio.iscoroutine(result):
            asyncio.run(result)


def _serialize_plan(plan: object) -> dict[str, object]:
    """Coerce a CompiledRunPlan to a JSON-friendly dict."""
    if is_dataclass(plan) and not isinstance(plan, type):
        data = asdict(plan)
    elif isinstance(plan, dict):
        data = dict(plan)
    else:
        data = {"plan": str(plan)}
    if "plugins" in data and isinstance(data["plugins"], list):
        data["plugin_count"] = len(data["plugins"])
    elif "entries" in data and isinstance(data["entries"], list):
        data["plugin_count"] = len(data["entries"])
    else:
        data["plugin_count"] = data.get("plugin_count", 0)
    return data
