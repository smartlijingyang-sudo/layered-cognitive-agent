"""Profile inspection commands: inspect-tree, dump-profile, why, why-plugin, graph, debug."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import typer

from lca.infrastructure.cli.commands._shared import render_diagnostic_trace_line

if TYPE_CHECKING:
    from lca.harness.profile.pipeline_loader import ProfilePipeline


def register(app: typer.Typer) -> None:
    """Register profile inspection commands on the typer app."""

    @app.command()
    def inspect_tree(
        profile: Path = typer.Argument(  # noqa: B008
            Path("profiles/web-standard.yaml"),
            help="Profile YAML path to inspect",
        ),
    ) -> None:
        """Show the resolved plugin Manifest tree (ADR-0061)."""
        from lca.harness.diagnostics.inspect import format_plugin_tree, inspect_profile_tree

        if not profile.exists():
            print(f"Profile not found: {profile}")
            raise typer.Exit(1)

        try:
            ctx = asyncio.run(inspect_profile_tree(profile))
        except Exception as exc:
            import yaml as _yaml

            with profile.open() as fh:
                data = _yaml.safe_load(fh) or {}
            graph = _graph_from_yaml(profile, data)
            print(f"Profile: {profile} (unbooted: {exc})")
            totals = cast("dict[str, object]", graph.get("totals", {}))
            print(f"Plugins: {cast('int', totals.get('plugins', 0))}")
            return

        print(format_plugin_tree(ctx, profile=str(profile)))

    @app.command()
    def dump_profile(
        profile: Path = typer.Argument(  # noqa: B008
            Path("profiles/web-standard.yaml"),
            help="Profile YAML path to dump the resolved Manifest for",
        ),
        source: bool = typer.Option(
            False, "--source", help="Annotate each row with its source bundle/patch"
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit canonical redacted JSON"),
    ) -> None:
        """Dump the resolved, redacted Manifest (ADR-0061). Never prints secrets."""
        from lca.harness.profile.resolve import dump_resolved, resolve_profile

        if not profile.exists():
            print(f"Profile not found: {profile}")
            raise typer.Exit(1)

        resolved = resolve_profile(profile)
        dumped = dump_resolved(resolved, redact=True)
        if as_json:
            print(json.dumps(dumped, indent=2, sort_keys=True, default=str))
            return
        print(f"profile: {dumped['profile']}")
        print(f"manifest_hash: {dumped['manifest_hash']}")
        print(f"bundles: {dumped['bundles']}")
        print()
        for row in dumped["plugins"]:
            if row["disabled"]:
                continue
            parts = [f"  - id: {row['id']}", f"    module: {row['module']}"]
            parts.append(f"    kind/layer: {row['kind']}/{row['layer']}")
            if row["config"]:
                parts.append(f"    config: {row['config']!r}")
            if source and row.get("source"):
                parts.append(f"    source: {row['source']}")
            print("\n".join(parts))
        print()
        print(f"Total rows: {sum(1 for r in dumped['plugins'] if not r['disabled'])}")

    @app.command("why")
    def why_cmd(
        capability: str = typer.Argument(..., help="Capability key to explain"),
        profile: Path = typer.Option(  # noqa: B008
            Path("profiles/web-standard.yaml"), "--profile", "-p", help="Profile YAML"
        ),
    ) -> None:
        """Explain who owns / requires a capability (ADR-0061)."""
        from lca.harness.diagnostics.inspect import inspect_profile_tree, why_capability

        ctx = asyncio.run(inspect_profile_tree(profile))
        print(why_capability(ctx, capability))

    @app.command("why-plugin")
    def why_plugin_cmd(
        plugin_id: str = typer.Argument(..., help="Plugin id to explain"),
        profile: Path = typer.Option(  # noqa: B008
            Path("profiles/web-standard.yaml"), "--profile", "-p", help="Profile YAML"
        ),
    ) -> None:
        """Explain why a plugin was started (ADR-0061)."""
        from lca.harness.diagnostics.inspect import inspect_profile_tree, why_plugin

        ctx = asyncio.run(inspect_profile_tree(profile))
        print(why_plugin(ctx, plugin_id))

    @app.command()
    def graph(
        profile: Path = typer.Argument(  # noqa: B008
            Path("profiles/web-standard.yaml"),
            help="Profile YAML path",
        ),
    ) -> None:
        """Print the compiled capability / phase / replacement graph as Mermaid."""
        from lca.infrastructure.cli.commands.declarative import render_declarative_graph

        print(render_declarative_graph(profile))

    @app.command("inspect-pipeline")
    def inspect_pipeline_cmd(
        profile: str = typer.Argument(
            "web-standard",
            help="Profile 名(如 web-standard)或 Profile YAML 路径",
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit canonical JSON"),
    ) -> None:
        """Inspect the event Pipeline a profile declares (ADR-0183 §3.3).

        Prints the four sections: hooks / sinks / consumer_rules / options.
        Exit 1 when the profile or its pipeline declaration is missing.
        """
        from lca.harness.profile.pipeline_loader import load_profile_pipeline

        profile_path = _resolve_profile_arg(profile)
        if not profile_path.exists():
            print(f"Profile not found: {profile}")
            raise typer.Exit(1)
        bundle = load_profile_pipeline(profile_path)
        if bundle is None:
            print(f"No event pipeline declared in profile: {profile_path}")
            raise typer.Exit(1)
        if as_json:
            print(json.dumps(_pipeline_bundle_dict(bundle, profile_path), indent=2, sort_keys=True))
            return
        print(_format_pipeline_bundle(bundle, profile_path))

    @app.command()
    def debug(
        sub: str = typer.Argument(..., help="debug sub-subcommand: tree | run | scope | trace"),
        profile: Path = typer.Option(  # noqa: B008
            Path("profiles/web-standard.yaml"),
            "--profile",
            "-p",
            help="Profile YAML to boot",
        ),
        run_id: str = typer.Option(None, "--run-id", help="Run ID for `debug run` / `debug trace`"),
        diagnostic: Path = typer.Option(  # noqa: B008
            None, "--diagnostic", help="Explicit diagnostic JSONL path"
        ),
        category: str = typer.Option("", "--category", help="Filter `debug trace` by category"),
        plugin: str = typer.Option("", "--plugin", help="Filter `debug trace` by plugin"),
    ) -> None:
        """Debug subcommand: tree, run, scope, trace."""
        if sub == "tree":
            from lca.harness.diagnostics.tree import render_tree
            from lca.harness.profile.boot import boot_profile

            async def main() -> None:
                ctx = await boot_profile(str(profile))
                print(render_tree(ctx))

            asyncio.run(main())
        elif sub == "run":
            if run_id is None:
                print("debug run requires --run-id")
                raise typer.Exit(1)
            journal_path = Path("traces/runs") / f"{run_id}.journal"
            if not journal_path.exists():
                print(f"No journal for {run_id} (expected {journal_path})")
                raise typer.Exit(1)
            for line in journal_path.read_text().splitlines():
                print(line)
        elif sub == "trace":
            if diagnostic is None:
                if run_id is None:
                    print("debug trace requires --run-id or --diagnostic")
                    raise typer.Exit(1)
                diagnostic = Path("traces/runs") / f"{run_id}.diagnostic.jsonl"
            if not diagnostic.exists():
                print(f"No diagnostic trace found (expected {diagnostic})")
                raise typer.Exit(1)
            for line in diagnostic.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if category and item.get("category") != category:
                    continue
                if plugin and item.get("plugin") != plugin:
                    continue
                render_diagnostic_trace_line(item)
        elif sub == "scope":
            if run_id is None:
                print("debug scope requires --run-id")
                raise typer.Exit(1)
            print(f"Run: {run_id}")
            print("Service resolution: deferred to follow-up (requires session_store.index)")
        else:
            print(f"Unknown debug sub: {sub!r} (expected: tree, run, scope)")
            raise typer.Exit(1)


def _graph_from_yaml(profile_path: Path, data: object) -> dict[str, object]:
    """Derive a minimal capability graph from a profile YAML (fallback)."""
    plugins_list: list[object] = []
    if isinstance(data, dict):
        raw = data.get("plugins") or data.get("entries") or []
        if isinstance(raw, list):
            plugins_list = raw
    return {
        "profile": str(profile_path),
        "plugins": [
            {
                "name": (p.get("name") or p.get("id") or "?") if isinstance(p, dict) else str(p),
                "implements": p.get("provides") if isinstance(p, dict) else [],
                "emitted_events": [],
                "context_fields": [],
                "capabilities": [],
                "side_effects": [],
                "policy_class": "",
            }
            for p in plugins_list
        ],
        "totals": {"plugins": len(plugins_list)},
    }


# ── inspect-pipeline helpers ─────────────────────────────────────────────


def _resolve_profile_arg(profile: str) -> Path:
    """Bare profile names resolve under ``profiles/``; paths pass through."""
    candidate = Path(profile)
    if candidate.exists():
        return candidate
    named = Path("profiles") / f"{profile}.yaml"
    if named.exists():
        return named
    return candidate


def _type_path(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _pipeline_bundle_dict(bundle: ProfilePipeline, profile_path: Path) -> dict[str, Any]:
    """Canonical dict view of one loaded pipeline bundle (JSON-safe)."""
    pipeline = bundle.pipeline
    return {
        "profile": str(profile_path),
        "source": bundle.source,
        "name": pipeline.name,
        "version": pipeline.version,
        "hooks": [
            {
                "id": spec.id,
                "hook": _type_path(spec.hook),
                "stage": spec.stage.value,
                "config": dict(spec.config),
            }
            for spec in pipeline.hooks
        ],
        "sinks": [
            {
                "id": spec.id,
                "backend": _type_path(spec.backend),
                "failure": spec.failure.value,
                "config": dict(spec.config),
                "depends_on": spec.depends_on,
            }
            for spec in pipeline.sinks
        ],
        "consumer_rules": [
            {
                "prefix": rule.prefix,
                "failure": rule.failure.value,
                "plugins": [_type_path(plugin) for plugin in rule.plugins],
            }
            for rule in pipeline.consumer_rules
        ],
        "options": dict(bundle.options),
    }


def _format_pipeline_bundle(bundle: ProfilePipeline, profile_path: Path) -> str:
    """Human-readable rendering of the four pipeline sections."""
    data = _pipeline_bundle_dict(bundle, profile_path)
    lines = [
        f"profile: {data['profile']}",
        f"source: {data['source']}",
        f"pipeline: {data['name']} (v{data['version']})",
        "",
        f"hooks ({len(data['hooks'])}):",
    ]
    for hook in data["hooks"]:
        lines.append(f"  - id: {hook['id']}")
        lines.append(f"    hook: {hook['hook']}")
        lines.append(f"    stage: {hook['stage']}")
        if hook["config"]:
            lines.append(f"    config: {hook['config']!r}")
    lines.append("")
    lines.append(f"sinks ({len(data['sinks'])}):")
    for sink in data["sinks"]:
        lines.append(f"  - id: {sink['id']}")
        lines.append(f"    backend: {sink['backend']}")
        lines.append(f"    failure: {sink['failure']}")
        if sink["depends_on"]:
            lines.append(f"    depends_on: {sink['depends_on']}")
        if sink["config"]:
            lines.append(f"    config: {sink['config']!r}")
    lines.append("")
    lines.append(f"consumer_rules ({len(data['consumer_rules'])}):")
    for rule in data["consumer_rules"]:
        lines.append(f"  - prefix: {rule['prefix']!r}")
        lines.append(f"    failure: {rule['failure']}")
        for plugin in rule["plugins"]:
            lines.append(f"    plugin: {plugin}")
    lines.append("")
    lines.append(f"options ({len(data['options'])}):")
    for key in sorted(data["options"]):
        lines.append(f"  {key}: {data['options'][key]!r}")
    return "\n".join(lines)
