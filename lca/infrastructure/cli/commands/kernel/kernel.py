"""``lca-ops kernel`` subcommands — kernel-driven service entry points.

ADR-0115 + ADR-0117: kernel is the single seam that compiles a profile
into a running process. ``lca-ops kernel {boot,serve,stop,compose,inspect}``
drives that seam without importing transport frameworks — every
subcommand resolves to a call into :mod:`lca_kernel` only.

Subcommands
-----------
- ``restart`` (top-level ``lca-ops kernel-restart``) — SIGTERM + spawn via
  supervisor; the only local-spawn entry point. Auto-runs boot check +
  fiber report + health probe.
- ``compose`` — dump the compiled run plan (YAML or JSON).
- ``check`` — run profile resolve + plan lift validators (no spawn).
- ``plugins`` — list plugin catalog a profile would load.
- ``boot_log`` — parse boot.pending_event lines from kernel stderr.

Retired commands
----------------
- ``boot`` — only blocks until SIGINT/SIGTERM (no HTTP). Use
  ``kernel-restart`` so the supervisor owns the lifecycle; for profile
  inspection use ``kernel_check`` / ``kernel_plugins`` / ``kernel_compose``.
- ``serve`` — only prints the ``lca_kernel serve`` command. Use
  ``kernel-restart`` to actually run the kernel; the supervisor-managed
  process is what the rest of LCA depends on.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import cast

import typer

# Matches KernelServeConfig.host default — referenced from typer Option to
# keep the printed command and the actual config value in lockstep, and to
# give ruff S104 a named literal to attach noqa to.
_LAN_BIND_DEFAULT = "0.0.0.0"  # noqa: S104 — bind-all intentional, see KernelServeConfig


def register(app: typer.Typer) -> None:
    """Register kernel subcommands on the typer app."""

    @app.command()
    def kernel_boot(
        profile_path: Path = typer.Argument(
            "profiles/web-standard.yaml",
            help="RETIRED — kept as fail-loud stub",
        ),
    ) -> None:
        """RETIRED — do not use. Use ``./scripts/lca-ops kernel-restart``.

        Why retired: blocking on SIGINT/SIGTERM without HTTP kept a separate
        code path that the supervisor does not own, and made it easy to
        leave an orphaned ``lca_kernel`` process behind. The
        supervisor-managed kernel started by ``kernel-restart`` is the only
        kernel lifecycle the rest of LCA tolerates.
        """
        typer.echo(
            "[retired] kernel-boot 已退役。\n"
            "  拉起 kernel:    ./scripts/lca-ops kernel-restart\n"
            "  只校验 profile: ./scripts/lca-ops kernel_check\n"
            "  只看 plugin:   ./scripts/lca-ops kernel_plugins\n",
            err=True,
        )
        raise typer.Exit(2)

    @app.command(name="kernel_serve")
    def kernel_serve(
        profile_path: Path = typer.Argument(
            "profiles/web-standard.yaml",
            help="RETIRED — kept as fail-loud stub",
        ),
        host: str = typer.Option(
            _LAN_BIND_DEFAULT, "--host", help="RETIRED — ignored"
        ),
        port: int = typer.Option(8765, "--port", help="RETIRED — ignored"),
    ) -> None:
        """RETIRED — do not use. Use ``./scripts/lca-ops kernel-restart``.

        Why retired: the only consumer ever called this for the printed
        argv, but every shell history entry became a divergence from the
        supervisor's spawn command. ``kernel-restart`` now runs the
        supervisor and the supervisor owns the canonical argv.
        """
        typer.echo(
            "[retired] kernel_serve 已退役。\n"
            "  拉起 kernel: ./scripts/lca-ops kernel-restart\n"
            "  (host/port 仍走 KernelServeConfig,见 ./scripts/lca-ops kernel-supervisor status)",
            err=True,
        )
        raise typer.Exit(2)

    @app.command(name="kernel_compose")
    def kernel_compose(
        profile_path: Path = typer.Argument(
            "profiles/web-standard.yaml",
            help="Profile YAML path to compile and dump",
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit canonical JSON"),
    ) -> None:
        """Dump CompiledRunPlan as YAML/JSON for diff/audit."""
        from lca.harness.profile.resolve.resolve import resolve_profile
        from lca_kernel import compile_profile

        resolved = resolve_profile(profile_path)
        plan = compile_profile(resolved)
        serialized = _serialize_plan(plan)
        if as_json:
            typer.echo(json.dumps(serialized, default=str, indent=2))
        else:
            typer.echo(f"compiled: profile={profile_path} keys={sorted(serialized.keys())}")

    @app.command(name="kernel_check")
    def kernel_check(
        profile_path: Path = typer.Argument(
            "profiles/web-standard.yaml",
            help="Profile YAML path to validate end-to-end without spawning uvicorn",
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit canonical JSON"),
    ) -> None:
        """Run every plan-lift / profile-resolve validator against ``profile_path``.

        Same checks :class:`KernelServeSpawner` runs at boot, but without
        spawning ``lca_kernel serve`` or waiting on /health. Used by
        ``kernel-restart`` failures (``next_command``) and by humans who
        want a fast yes/no on whether the active profile is bootable.

        Exit code: ``0`` iff every check passed; ``1`` on the first
        failure (with the failing check's reason and the recommended
        remediation hint).

        JSON mode redirects stdout to ``/dev/null`` while validators run:
        ``resolve_profile`` and ``validate_profile_plans`` print progress
        banners that would otherwise corrupt the JSON stream. ``kernel
        logs`` reads stderr instead, so progress is still observable.
        """
        import contextlib
        import io
        import os
        import time as _time

        start = _time.monotonic()
        checks: list[dict[str, object]] = []
        first_failure: dict[str, object] | None = None

        # Silence stdout while validators run; their `print("✅ ...")`
        # banners would otherwise leak into --json output. Stderr stays
        # open so humans running interactively still see progress.
        devnull: io.TextIOBase | None = None
        saved_stdout: io.TextIOBase | None = None
        if as_json:
            # Stdout is replaced for the duration of the validator pass so
            # its `print("✅ ...")` banners do not corrupt the JSON stream,
            # then restored before the JSON report itself is emitted. Using
            # `with` would close the handle we want to swap in and out, so
            # the open() is intentionally not inside a context manager.
            devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 — see comment above
            saved_stdout = sys.stdout
            sys.stdout = devnull

        # 1) profile resolve
        try:
            from lca.harness.profile.resolve.resolve import resolve_profile

            resolve_profile(profile_path)
            checks.append({"name": "resolve", "ok": True})
        except Exception as exc:
            entry = {
                "name": "resolve",
                "ok": False,
                "error": exc.__class__.__name__,
                "reason": str(exc),
                "next_command": (
                    f"./scripts/lca-ops plan compile {profile_path}"
                ),
            }
            checks.append(entry)
            first_failure = entry

        # 2) plan lift (only if resolve passed)
        if first_failure is None:
            try:
                from lca.contracts.protocols.graph.errors import PlanLiftError
                from lca_kernel.boot.plan_validation import validate_profile_plans

                # ``resolve_profile`` succeeded above; re-resolve so we
                # have the resolved handle for the validator.
                resolved = resolve_profile(profile_path)
                validate_profile_plans(resolved)
                checks.append({"name": "plan_lift", "ok": True})
            except PlanLiftError as exc:
                next_cmd = (
                    getattr(exc, "next_command", None)
                    or f"./scripts/lca-ops plan validate {profile_path}"
                )
                next_cmd = str(next_cmd).replace("{profile}", str(profile_path))
                entry = {
                    "name": "plan_lift",
                    "ok": False,
                    "error": exc.__class__.__name__,
                    "reason": exc.reason,
                    "plan_id": exc.plan_id,
                    "node_id": exc.node_id,
                    "edge_id": exc.edge_id,
                    "port_name": exc.port_name,
                    "next_command": next_cmd,
                }
                checks.append(entry)
                first_failure = entry
            except Exception as exc:
                entry = {
                    "name": "plan_lift",
                    "ok": False,
                    "error": exc.__class__.__name__,
                    "reason": str(exc),
                    "next_command": (
                        f"./scripts/lca-ops plan validate {profile_path}"
                    ),
                }
                checks.append(entry)
                first_failure = entry

        duration_ms = int((_time.monotonic() - start) * 1000)
        report = {
            "profile": str(profile_path),
            "ok": first_failure is None,
            "duration_ms": duration_ms,
            "checks": checks,
            "next_command": (
                first_failure["next_command"] if first_failure else None
            ),
        }

        # Restore stdout *before* emitting JSON, so the report goes to
        # the real stdout regardless of the redirect we set above.
        if saved_stdout is not None:
            sys.stdout = saved_stdout
        if devnull is not None:
            with contextlib.suppress(OSError):
                devnull.close()

        if as_json:
            typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            typer.echo(
                f"{'OK' if report['ok'] else 'FAIL'} profile={profile_path} "
                f"duration_ms={duration_ms}"
            )
            for entry in checks:
                marker = "ok" if entry["ok"] else f"FAIL({entry['error']})"
                typer.echo(f"  [{marker}] {entry['name']}")
                if not entry["ok"]:
                    typer.echo(f"    reason : {entry['reason']}")
                    if entry.get("next_command"):
                        typer.echo(f"    next   : {entry['next_command']}")
        if not report["ok"]:
            raise typer.Exit(1)

    @app.command(name="kernel_plugins")
    def kernel_plugins(
        profile_path: Path = typer.Option(
            Path("profiles/web-standard.yaml"),
            "--profile",
            "-p",
            help="Profile YAML path to enumerate plugins for",
        ),
        layer: str = typer.Option(
            "",
            "--layer",
            help="Filter by layer (e.g. L0,L1). Comma-separated; empty = all layers.",
        ),
        plugin_id: str = typer.Option(
            "",
            "--id",
            help="Filter to a single plugin id",
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit canonical JSON"),
    ) -> None:
        """List the plugin catalog a profile would load, grouped by layer.

        Projects the same ``plugin_specs`` tuple the compiled plan carries;
        agents and operators can answer "what loaded" without booting the
        kernel or parsing ``kernel_compose --json``.
        """
        from lca.harness.profile.resolve.resolve import resolve_profile
        from lca_kernel.plan.plan_compile import compile_plan

        if not profile_path.exists():
            typer.echo(f"Profile not found: {profile_path}", err=True)
            raise typer.Exit(2)
        resolved = resolve_profile(profile_path)
        plan = compile_plan(resolved)
        specs = list(plan.plugin_specs)

        if plugin_id:
            specs = [spec for spec in specs if spec.id == plugin_id]
        elif layer:
            wanted = {layer.strip() for layer in layer.split(",") if layer.strip()}
            specs = [spec for spec in specs if spec.layer in wanted]

        if as_json:
            payload = {
                "profile": str(profile_path),
                "plugin_count": len(specs),
                "plugins": [
                    {
                        "id": spec.id,
                        "layer": spec.layer,
                        "kind": spec.kind.value if hasattr(spec.kind, "value") else str(spec.kind),
                        "module": spec.implementation.module,
                        "revision": spec.revision,
                    }
                    for spec in specs
                ],
            }
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        if not specs:
            typer.echo("(no plugins match filter)")
            return
        by_layer: dict[str, list[str]] = {}
        for spec in specs:
            by_layer.setdefault(spec.layer, []).append(spec.id)
        for layer_name in sorted(by_layer):
            ids = by_layer[layer_name]
            typer.echo(f"{layer_name} ({len(ids)}):")
            for pid in ids:
                typer.echo(f"  {pid}")
        typer.echo(f"total: {len(specs)}")

    @app.command(name="kernel_boot_log")
    def kernel_boot_log(
        stderr_path: Path | None = typer.Option(
            None,
            "--stderr",
            help="Explicit path to a kernel stderr file (defaults to the latest "
            "lca-kernel.stderr.*.log under /tmp)",
        ),
        failed_only: bool = typer.Option(
            False,
            "--failed-only",
            help="Keep only boot.pending_event entries whose status != ok",
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit canonical JSON"),
    ) -> None:
        """Read the kernel's boot log and surface each plugin fiber spawn.

        Parses ``boot.pending_event`` lines written by
        :func:`lca_kernel.boot._emit_boot_events`. Each line carries
        ``plugin_id`` / ``layer`` / ``kind`` / ``status`` / ``duration_ms``;
        the command groups by layer in the human form and emits a flat
        list in the JSON form. When ``--stderr`` is omitted, the latest
        ``lca-kernel.stderr.*.log`` under ``/tmp`` is used so operators
        can answer "what just loaded?" immediately after a restart.
        """
        target = stderr_path if stderr_path is not None else _latest_kernel_stderr()
        if target is None:
            typer.echo(
                "No kernel stderr file found. Pass --stderr <path> or boot the kernel first.",
                err=True,
            )
            raise typer.Exit(2)
        if not target.exists():
            typer.echo(f"stderr file not found: {target}", err=True)
            raise typer.Exit(2)
        entries = _parse_boot_pending_events(target.read_text(encoding="utf-8"))
        all_entries = entries
        if failed_only:
            entries = [entry for entry in entries if entry["status"] != "ok"]
        if as_json:
            payload = {
                "stderr": str(target),
                "plugin_count": len(entries),
                "entries": entries,
            }
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        if not all_entries:
            typer.echo(f"no boot.pending_event lines in {target}")
            return
        if not entries:
            typer.echo(f"all {len(all_entries)} entries were ok; nothing failed")
            return
        by_layer: dict[str, list[dict[str, object]]] = {}
        for entry in entries:
            by_layer.setdefault(str(entry["layer"]), []).append(entry)
        for layer_name in sorted(by_layer):
            rows = by_layer[layer_name]
            typer.echo(f"{layer_name} ({len(rows)}):")
            for row in rows:
                marker = "ok" if row["status"] == "ok" else f"FAIL({row['status']})"
                typer.echo(
                    f"  {row['plugin_id']:<64} {row['kind']:<10} {marker:<10} "
                    f"{float(row['duration_ms']):.1f}ms"
                )
        typer.echo(f"total: {len(entries)}")


def _serialize_plan(plan: object) -> dict[str, object]:
    """Coerce a CompiledRunPlan to a JSON-friendly dict."""
    data: dict[str, object]
    if is_dataclass(plan) and not isinstance(plan, type):
        data = cast("dict[str, object]", asdict(plan))
    elif isinstance(plan, dict):
        data = dict(plan)
    else:
        data = {"plan": str(plan)}
    if "plugins" in data and isinstance(data["plugins"], list):
        data["plugin_count"] = len(data["plugins"])
    elif "entries" in data and isinstance(data["entries"], list):
        data["plugin_count"] = len(data["entries"])
    elif ("plugin_specs" in data and isinstance(data["plugin_specs"], tuple)) or ("plugin_specs" in data and isinstance(data["plugin_specs"], list)):
        data["plugin_count"] = len(data["plugin_specs"])
    else:
        data["plugin_count"] = data.get("plugin_count", 0)
    return data


_STDERR_DIR = Path("/tmp")  # noqa: S108 — kernel stderr files are stable paths under KernelServeSpawner._STDERR_DIR; keep aligned with spawner.py
_STDERR_PREFIX = "lca-kernel.stderr."


def _latest_kernel_stderr() -> Path | None:
    """Return the most recent ``lca-kernel.stderr.*.log`` under ``/tmp``.

    Matches both ``lca-kernel.stderr.<pid>.<timestamp>.log`` and the
    ``pre`` form written when the spawner fails before knowing the PID.
    The spawner prunes to keep only the 5 most recent files; we mirror
    that with the same prefix filter.
    """
    candidates = sorted(
        (
            path
            for path in _STDERR_DIR.iterdir()
            if path.is_file()
            and path.name.startswith(_STDERR_PREFIX)
            and path.name.endswith(".log")
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _parse_boot_pending_events(text: str) -> list[dict[str, object]]:
    """Extract ``boot.pending_event`` rows from a kernel stderr blob.

    structlog prints each ``key=value`` pair right-aligned in fixed-width
    columns. We tokenize the line, keep only the ``key=value`` tokens, and
    collect the ones ``boot.pending_event`` writes (event_type /
    plugin_id / layer / kind / status / duration_ms). Lines that do not
    match the schema are skipped so Uvicorn banners or other log streams
    in the same file do not poison the output.
    """
    keys = ("plugin_id", "layer", "kind", "status", "duration_ms")
    out: list[dict[str, object]] = []
    for raw_line in text.splitlines():
        if "boot.pending_event" not in raw_line:
            continue
        entry: dict[str, object] = {}
        for token in raw_line.split():
            if "=" not in token:
                continue
            key, _, value = token.partition("=")
            if key in keys:
                if key == "duration_ms":
                    try:
                        entry[key] = float(value)
                    except ValueError:
                        entry[key] = value
                else:
                    entry[key] = value
        if "plugin_id" in entry:
            out.append(entry)
    return out
