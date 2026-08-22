"""Profile inspection commands: inspect-tree, dump-profile, why, why-plugin, graph, debug."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

import typer

from lca.layer0_infra.ops.commands._shared import render_diagnostic_trace_line


def register(app: typer.Typer) -> None:
    """Register profile inspection commands on the typer app."""

    @app.command()
    def inspect_tree(
        profile: Path = typer.Argument(
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
        profile: Path = typer.Argument(
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
        profile: Path = typer.Option(
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
        profile: Path = typer.Option(
            Path("profiles/web-standard.yaml"), "--profile", "-p", help="Profile YAML"
        ),
    ) -> None:
        """Explain why a plugin was started (ADR-0061)."""
        from lca.harness.diagnostics.inspect import inspect_profile_tree, why_plugin

        ctx = asyncio.run(inspect_profile_tree(profile))
        print(why_plugin(ctx, plugin_id))

    @app.command()
    def graph(
        profile: Path = typer.Argument(
            Path("profiles/web-standard.yaml"),
            help="Profile YAML path",
        ),
    ) -> None:
        """Print the compiled capability / phase / replacement graph as Mermaid."""
        from lca.layer0_infra.ops.commands.declarative import render_declarative_graph

        print(render_declarative_graph(profile))

    @app.command()
    def debug(
        sub: str = typer.Argument(..., help="debug sub-subcommand: tree | run | scope | trace"),
        profile: Path = typer.Option(
            Path("profiles/web-standard.yaml"),
            "--profile",
            "-p",
            help="Profile YAML to boot",
        ),
        run_id: str = typer.Option(None, "--run-id", help="Run ID for `debug run` / `debug trace`"),
        diagnostic: Path = typer.Option(
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
