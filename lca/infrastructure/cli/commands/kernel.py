"""``lca-ops kernel`` subcommands — kernel-driven service entry points.

ADR-0115 + ADR-0117: kernel is the single seam that compiles a profile
into a running process. ``lca-ops kernel {boot,serve,stop,compose,inspect}``
drives that seam without importing transport frameworks — every
subcommand resolves to a call into :mod:`lca_kernel` only.

Subcommands
-----------
- ``boot`` — compile + run the kernel, block until SIGINT/SIGTERM.
- ``serve`` — compile + boot + run uvicorn with the kernel lifespan.
- ``stop`` — send SIGTERM to a previously-started ``serve`` process.
- ``compose`` — dump the compiled run plan (YAML or JSON).
- ``inspect`` — show boot trace + K8 HMR patch state.
"""

from __future__ import annotations

import asyncio
import json
import sys
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
        """Boot a profile and block until SIGINT/SIGTERM."""
        if dry_run:
            _compile_only(profile_path)
            return
        _boot_blocking(profile_path)

    @app.command(name="kernel_serve")
    def kernel_serve(
        profile_path: Path = typer.Argument(  # noqa: B008
            "profiles/web-standard.yaml",
            help="Profile YAML path the LCA kernel should boot",
        ),
        host: str = typer.Option("127.0.0.1", "--host", help="lca_kernel serve host"),
        port: int = typer.Option(8765, "--port", help="lca_kernel serve port"),
    ) -> None:
        """Print the command to start the LCA kernel (ADR-0119 决定 4).

        ``lca-ops`` 不再管理 LCA 进程 — LCA :8765 由 ``lca_kernel serve`` 自管,
        SIGTERM/SIGINT 由 K6 ``lca_kernel.lifecycle`` 守护。本子命令只打印
        启动命令供脚本化集成使用;要拉起进程请直接运行打印的命令,或跑
        ``./scripts/lca-ops heal`` 让 KernelServeService 自愈。

        命令:

            uv run python -m lca_kernel serve \\
                --profile <profile_path> --host <h> --port <p> --allow-unknown-env
        """
        typer.echo(f"运行模式 OK · kernel_serve profile={profile_path} host={host} port={port}")
        typer.echo("To start, run (in another shell):")
        typer.echo(
            f"  uv run python -m lca_kernel serve "
            f"--profile {profile_path} "
            f"--host {host} --port {port} --allow-unknown-env"
        )

    @app.command(name="kernel_compose")
    def kernel_compose(
        profile_path: Path = typer.Argument(  # noqa: B008
            "profiles/web-standard.yaml",
            help="Profile YAML path to compile and dump",
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit canonical JSON"),
    ) -> None:
        """Dump CompiledRunPlan as YAML/JSON for diff/audit."""
        from lca.harness.profile.resolve import resolve_profile
        from lca_kernel import compile_profile

        resolved = resolve_profile(profile_path)
        plan = compile_profile(resolved)
        serialized = _serialize_plan(plan)
        if as_json:
            typer.echo(json.dumps(serialized, default=str, indent=2))
        else:
            typer.echo(f"compiled: profile={profile_path} keys={sorted(serialized.keys())}")


def _compile_only(profile_path: Path) -> None:
    """Compile a profile without booting — for ``--dry-run`` / inspect."""
    from lca.harness.profile.resolve import resolve_profile
    from lca_kernel import compile_profile

    resolved = resolve_profile(profile_path)
    plan = compile_profile(resolved)
    serialized = _serialize_plan(plan)
    typer.echo(
        f"运行模式 OK · kernel_compile profile={profile_path} "
        f"plugins={serialized.get('plugin_count', '?')}"
    )


def _boot_blocking(profile_path: Path) -> None:
    """Compile + boot a profile; block until SIGINT/SIGTERM via kernel CM.

    The kernel lifespan installs signal handlers (K6) and exits with
    the signal's exit code on disposal. We just drive the CM on the
    main asyncio loop — no thread, no signal.pause() hack.
    """
    from lca_kernel import run_kernel_lifespan

    async def _run() -> None:
        async with run_kernel_lifespan(profile_path) as state:
            ctx = state["ctx"]
            plugin_count = len(getattr(ctx, "_plugins", {}) or {})
            typer.echo(f"运行模式 OK · kernel_boot profile={profile_path} plugins={plugin_count}")
            typer.echo("  press Ctrl+C to stop (SIGINT/SIGTERM)")
            await asyncio.Event().wait()  # block; SIGTERM tears down via K6

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("kernel_boot interrupted", err=True)
        sys.exit(130)


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
