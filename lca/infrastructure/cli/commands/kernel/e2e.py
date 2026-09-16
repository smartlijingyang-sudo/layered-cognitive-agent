"""End-to-end smoke commands — wrappers for ``scripts/e2e_*.py``.

Exposes the existing ``scripts/e2e_timeline_smoke.py`` as
``lca-ops e2e timeline``. ``lca-ops e2e boot`` is RETIRED — it wrapped
``scripts/e2e_smoke_test.py`` which depended on v1 ``CompiledRunPlan``
fields (``phase_graph`` / ``phase_bindings`` / ``semantic_phase`` /
loop edges) retired by ADR-0221 P3. The boot check, plan projection,
and wire smoke that ``e2e boot`` approximated now have dedicated
commands:

  - ``lca-ops kernel-restart`` — boot check + fiber report + health probe
  - ``lca-ops plan compile``    — v2 CompiledRunPlan projection
  - ``lca-ops e2e timeline``    — browser wire smoke

Both commands forward ``LCA_FRONTEND_URL`` / ``LCA_TOKEN`` to the
subprocess — the same envs the underlying scripts read — and inherit the
parent environment otherwise.

The subprocess exit code is preserved; ``--json`` prints the command
invocation alongside stdout/stderr so agents can capture the wire trace.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import typer

from lca.infrastructure.cli.commands.kernel._shared import resolve_repo_root


def _script_path(name: str) -> Path:
    """Locate an e2e script under the invoking repo's ``scripts/``."""
    return resolve_repo_root() / "scripts" / name


def register(app: typer.Typer) -> None:
    """Register the ``e2e`` subcommand on the CLI app."""
    e2e_app = typer.Typer(help="End-to-end smoke (wraps scripts/e2e_*.py).", no_args_is_help=True)
    e2e_app.command(name="timeline", help=_timeline.__doc__ or "")(_timeline)
    e2e_app.command(name="boot", help=_boot.__doc__ or "")(_boot)
    app.add_typer(e2e_app, name="e2e")


def _spawn(script: Path, extra_env: dict[str, str]) -> int:
    """Run the e2e script with merged env, stream output, return its exit code."""
    if not script.exists():
        typer.echo(f"[lca-ops e2e] script not found: {script}", err=True)
        return 2
    env = os.environ.copy()
    env.update(extra_env)
    # Inherit parent stdio so the agent/CI sees the same output as if it had
    # run the script directly. The returned exit code is the script's.
    result = subprocess.run(  # repo-local script, env-controlled.
        [sys.executable, str(script)],
        env=env,
        check=False,
    )
    return result.returncode


def _timeline(
    frontend_url: str = typer.Option(
        "http://10.36.6.252:3010",
        "--frontend-url",
        envvar="LCA_FRONTEND_URL",
        help="LobeHub Next app base (the URL the browser fetches /lca-api/runs from).",
    ),
    token: str = typer.Option(
        "lca-local",
        "--token",
        envvar="LCA_TOKEN",
        help="Bearer token forwarded as Authorization header.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Print env summary as JSON."),
) -> None:
    """Simulate frontend wire — ``POST {frontend}/lca-api/runs`` + SSE ``/live``.

    Mirrors the legacy lobehub UI SSE consumer (retired in PR-4).
    Use ``--frontend-url`` to point at a reachable LobeHub dev/prod
    host; the bare gateway port does not serve the ``/lca-api``
    rewrite prefix.
    """
    script = _script_path("e2e_timeline_smoke.py")
    extra = {"LCA_FRONTEND_URL": frontend_url, "LCA_TOKEN": token}
    if json_mode:
        typer.echo(
            json.dumps(
                {"script": script.name, "env": extra},
                ensure_ascii=False,
            )
        )
    raise typer.Exit(_spawn(script, extra))


def _boot(
    http_mode: bool = typer.Option(
        False,
        "--http",
        envvar="LCA_E2E_HTTP",
        help="RETIRED — ignored",
    ),
    frontend_url: str = typer.Option(
        "http://10.36.6.252:3010",
        "--frontend-url",
        envvar="LCA_FRONTEND_URL",
        help="RETIRED — ignored",
    ),
    token: str = typer.Option(
        "lca-local",
        "--token",
        envvar="LCA_TOKEN",
        help="RETIRED — ignored",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Print env summary as JSON."),
) -> None:
    """RETIRED — use ``lca-ops kernel-restart`` + ``lca-ops plan compile``.

    ``scripts/e2e_smoke_test.py`` depended on v1 ``CompiledRunPlan`` fields
    retired by ADR-0221 P3 (phase_graph / phase_bindings / loop edges).
    The boot check + plan projection + wire smoke it approximated now have
    dedicated commands:

      ./scripts/lca-ops kernel-restart    # boot check + fiber report + health
      ./scripts/lca-ops plan compile      # v2 CompiledRunPlan projection
      ./scripts/lca-ops e2e timeline      # browser wire smoke
    """
    typer.echo(
        """[retired] lca-ops e2e boot 已退役。
  等价命令:
    ./scripts/lca-ops kernel-restart     # 自动 boot_check + fiber_report + health_probe
    ./scripts/lca-ops plan compile       # v2 CompiledRunPlan 投影
    ./scripts/lca-ops e2e timeline       # 浏览器线路 smoke
""",
        err=True,
    )
    raise typer.Exit(2)


__all__ = ["register"]
