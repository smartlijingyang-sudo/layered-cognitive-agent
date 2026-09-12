"""Typer commands for declarative plan compilation and inspection."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

import typer

from lca.contracts.protocols.declarative.declarative_1.bundle_graph import BundleGraphSpec
from lca.harness.declarative.controls.validation import is_validation_valid
from lca.harness.plan import compiled_run_plan_to_dict
from lca.harness.profile.resolve.resolve import resolve_profile
from lca.infrastructure.cli.commands.kernel._shared import emit_report
from lca.infrastructure.cli.commands.profile.declarative_graph import (
    audit_declarative_boundaries,
    explain_declarative_plan,
    render_declarative_graph,
)
from lca_kernel.plan.plan_compile import CompileOptions, compile_plan


def register(app: typer.Typer) -> None:
    plugin_app = typer.Typer(help="PluginSpec 完整性与所有权验证。", invoke_without_command=True)
    plan_app = typer.Typer(help="声明式 CompiledRunPlan 编译与验证。", invoke_without_command=True)
    app.add_typer(plugin_app, name="plugin")
    app.add_typer(plan_app, name="plan")

    @plugin_app.command("check")
    def plugin_check(
        profile: Path = typer.Argument(..., help="Profile YAML"),
        strict: bool = typer.Option(False, "--strict", help="将任何声明缺失视为失败"),
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """校验激活 PluginSpec 的 identity、capability、effect 与 verification 段。"""
        try:
            plan = compile_plan(resolve_profile(profile))
        except (OSError, ValueError) as exc:
            _fail(f"plugin check: {exc}")
        report = {
            "profile": str(profile),
            "strict": strict,
            "active_plugins": len(plan.plugin_specs),
            "valid": is_validation_valid(plan.validation_report),
            "issues": [
                {"code": issue.code, "message": issue.message, "location": issue.location}
                for issue in plan.validation_report.issues
            ],
            "plugins": [
                {
                    "id": spec.id,
                    "revision": spec.revision,
                    "kind": spec.kind.value,
                    "capabilities": [item.key for item in spec.provides],
                    "effects": list(spec.effects),
                    "verification": spec.verification.test_suite,
                }
                for spec in plan.plugin_specs
            ],
        }
        emit_report(report, json_mode=json_mode)
        if strict and not report["valid"]:
            raise typer.Exit(1)

    @plan_app.callback(invoke_without_command=True)
    def plan_compat(
        ctx: typer.Context,
        subcommand: str | None = typer.Option(
            None,
            "--sub",
            "-s",
            help="Compatibility alias: list-templates",
        ),
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """兼容 ADR-0074 的 ``plan [--sub] list-templates`` 入口。"""
        if ctx.invoked_subcommand is not None:
            return
        selected = subcommand or "list-templates"
        if selected != "list-templates":
            _fail(f"plan: unsupported compatibility command: {selected}")
        _emit_plan_templates(json_mode=json_mode)

    @plan_app.command("list-templates")
    def plan_list_templates(
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """列出既有标准 PlanTemplate（兼容命令）。"""
        _emit_plan_templates(json_mode=json_mode)

    @plan_app.command("compile")
    def plan_compile(
        profile: Path = typer.Argument(..., help="Profile YAML"),
        task_contract: Path | None = typer.Option(
            None, "--task-contract", help="TaskContract 文件"
        ),
        output: Path | None = typer.Option(None, "--output", "-o", help="写入 canonical JSON"),
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """编译 Profile 为 canonical CompiledRunPlan v2。"""
        task_ref = str(task_contract) if task_contract is not None else None
        try:
            plan = compile_plan(resolve_profile(profile), options=CompileOptions(task_id=task_ref))
        except (OSError, ValueError) as exc:
            _fail(f"plan compile: {exc}")
        payload = compiled_run_plan_to_dict(plan)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        emit_report(payload, json_mode=json_mode)

    @plan_app.command("validate")
    def plan_validate(
        plan_file: Path = typer.Argument(..., help="由 plan compile 写出的 JSON"),
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """验证已序列化计划中记录的 schema、phase graph、effect 与 evidence 状态。"""
        try:
            raw = json.loads(plan_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            _fail(f"plan validate: {exc}")
        if not isinstance(raw, dict):
            _fail("plan validate: input must be a JSON object")
        declarative = raw.get("declarative")
        validation = declarative.get("validation_report") if isinstance(declarative, dict) else None
        if not isinstance(validation, dict):
            _fail("plan validate: input has no declarative validation report")
        validation_report = cast("dict[str, Any]", validation)
        report = {
            "plan_ref": raw.get("plan_ref", ""),
            "schema_version": raw.get("schema_version", ""),
            "valid": bool(validation_report.get("valid")),
            "errors": validation_report.get("errors", []),
            "warnings": validation_report.get("warnings", []),
        }
        emit_report(report, json_mode=json_mode)
        if not report["valid"]:
            raise typer.Exit(1)

    @plan_app.command("tree")
    def plan_tree(
        profile: Path = typer.Argument(..., help="Profile YAML"),
        depth: int = typer.Option(
            8,
            "--depth",
            "-d",
            help="递归展开 sub_spec_ref.plan_ref 的最大层级;0 仅顶层",
        ),
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """按层递归 inflate 声明图:顶层 phase_graph + 所有嵌套 sub_spec_ref 子图。

        输出每层的节点 / 边 / factory / sub_spec_ref.plan_ref;每个 subgraph
        单独校验节点 id 唯一 + edge.source/target 命中 + entry 命中。
        任何一层失败立即失败,exit code 1。
        """
        from lca.harness.declarative.compile.subgraph_resolver import (
            _load_bundle_graph_spec,
        )

        try:
            resolved = resolve_profile(profile)
            plan = compile_plan(resolved, options=CompileOptions())
        except (OSError, ValueError) as exc:
            _fail(f"plan tree: compile failed: {exc}")

        payload = compiled_run_plan_to_dict(plan)
        plan_ref = payload.get("plan_ref", "")
        schema_version = payload.get("schema_version", "")
        declarative = payload.get("declarative", {}) if isinstance(payload, dict) else {}
        phase_graph = declarative.get("phase_graph", {}) if isinstance(declarative, dict) else {}
        top_nodes = list(phase_graph.get("nodes", []) or [])
        top_edges = list(phase_graph.get("edges", []) or [])
        top_validation = (
            declarative.get("validation_report", {}) if isinstance(declarative, dict) else {}
        )

        # Per-layer inflate:顶层走 CompiledRunPlan;sub_spec_ref 走 _load_bundle_graph_spec
        layers: list[dict[str, Any]] = []

        def _layer_status(spec: BundleGraphSpec) -> dict[str, Any]:
            return {
                "id": spec.id,
                "region": spec.region,
                "purpose": spec.purpose,
                "node_count": len(spec.nodes),
                "edge_count": len(spec.edges),
                "entry": spec.entry,
            }

        def _visit_subgraph(
            plan_ref_path: str, current_depth: int, parent_node_id: str
        ) -> dict[str, Any]:
            """递归加载一个 sub_spec_ref.plan_ref 指向的 bundle yaml。

            Returns 一个 layer dict;失败时把 error 装进 layer,exit code 由 caller 决定。
            """
            try:
                spec = _load_bundle_graph_spec(plan_ref_path)
            except FileNotFoundError as exc:
                return {
                    "plan_ref": plan_ref_path,
                    "parent_node": parent_node_id,
                    "depth": current_depth,
                    "error": f"not found on disk: {exc}",
                    "nodes": [],
                    "edges": [],
                    "children": [],
                }
            except Exception as exc:
                return {
                    "plan_ref": plan_ref_path,
                    "parent_node": parent_node_id,
                    "depth": current_depth,
                    "error": f"inflate failed ({type(exc).__name__}): {exc}",
                    "nodes": [],
                    "edges": [],
                    "children": [],
                }

            layer: dict[str, Any] = {
                "plan_ref": plan_ref_path,
                "parent_node": parent_node_id,
                "depth": current_depth,
                "status": _layer_status(spec),
                "nodes": [
                    {
                        "id": n.id,
                        "factory": n.factory,
                        "purpose": n.purpose,
                        "config_keys": sorted(n.config.keys()),
                        "sub_spec_ref": (
                            dict(n.config["sub_spec_ref"])
                            if isinstance(n.config.get("sub_spec_ref"), dict)
                            else None
                        ),
                    }
                    for n in spec.nodes
                ],
                "edges": [
                    {"source": e.source, "target": e.target, "kind": e.kind, "when": e.when}
                    for e in spec.edges
                ],
            }
            children: list[dict[str, Any]] = []
            if current_depth < depth:
                for n in spec.nodes:
                    nested = n.config.get("sub_spec_ref") if isinstance(n.config, dict) else None
                    if not (isinstance(nested, dict) and nested.get("plan_ref")):
                        continue
                    children.append(_visit_subgraph(nested["plan_ref"], current_depth + 1, n.id))
            layer["children"] = children
            return layer

        # 顶层 phase_graph 节点本身也可能带 sub_spec_ref,只走 _load 路径
        if depth > 0:
            for n in top_nodes:
                if not isinstance(n, dict):
                    continue
                ssr = n.get("sub_spec_ref")
                if isinstance(ssr, dict) and ssr.get("plan_ref"):
                    layers.append(_visit_subgraph(ssr["plan_ref"], 1, n["id"]))

        tree_payload: dict[str, Any] = {
            "profile": str(profile),
            "plan_ref": plan_ref,
            "schema_version": schema_version,
            "top": {
                "entry": phase_graph.get("entry"),
                "node_count": len(top_nodes),
                "edge_count": len(top_edges),
                "nodes": [
                    {
                        "id": n.get("id"),
                        "semantic_phase": n.get("semantic_phase"),
                        "binding": n.get("binding"),
                        "terminal": bool(n.get("terminal", False)),
                        "max_visits": n.get("max_visits"),
                        "sub_spec_ref": n.get("sub_spec_ref"),
                    }
                    for n in top_nodes
                    if isinstance(n, dict)
                ],
                "edges": [
                    {"source": e.get("source"), "target": e.get("target"), "when": e.get("when")}
                    for e in top_edges
                    if isinstance(e, dict)
                ],
                "validation_report": top_validation,
            },
            "layers": layers,
        }
        top_invalid = bool(top_validation) and not bool(top_validation.get("valid", True))
        any_layer_failed = any("error" in layer for layer in layers if isinstance(layer, dict))

        if json_mode:
            typer.echo(json.dumps(tree_payload, ensure_ascii=False, indent=2, default=str))
            if top_invalid or any_layer_failed:
                raise typer.Exit(1)
            return

        # 文本输出
        typer.echo(f"profile={profile}")
        typer.echo(f"plan_ref={plan_ref}  schema={schema_version}")
        typer.echo("")
        typer.echo("▸ phase_graph[L0]")
        last_idx = len(tree_payload["top"]["nodes"]) - 1
        for i, n in enumerate(tree_payload["top"]["nodes"]):
            prefix = "  └─ " if i == last_idx else "  ├─ "
            suffix = "  terminal" if n.get("terminal") else ""
            ssr = n.get("sub_spec_ref")
            sub_marker = (
                f"  sub={ssr['plan_ref']}" if isinstance(ssr, dict) and ssr.get("plan_ref") else ""
            )
            binding = n.get("binding") or "—"
            typer.echo(f"{prefix}{n['id']:18s} binding={binding:30s}{sub_marker}{suffix}")
        typer.echo("")
        typer.echo(
            f"top validation: valid={tree_payload['top']['validation_report'].get('valid', True)} "
            f"errors={len(tree_payload['top']['validation_report'].get('errors', []) or [])} "
            f"warnings={len(tree_payload['top']['validation_report'].get('warnings', []) or [])}"
        )

        def _render_layer(layer: dict[str, Any], prefix_chain: tuple[str, ...]) -> None:
            indent = "  ".join(prefix_chain)
            typer.echo("")
            if "error" in layer:
                typer.echo(f"{indent}✗ {layer['plan_ref']}[L{layer['depth']}] {layer['error']}")
                return
            typer.echo(
                f"{indent}▸ {layer['status']['id']}[L{layer['depth']}] "
                f"plan={layer['plan_ref']}  "
                f"nodes={layer['status']['node_count']} edges={layer['status']['edge_count']} "
                f"entry={layer['status']['entry']}"
            )
            nodes = layer["nodes"]
            last = len(nodes) - 1
            for i, n in enumerate(nodes):
                branch = "└─ " if i == last else "├─ "
                cfg_keys = ",".join(n["config_keys"]) if n["config_keys"] else "—"
                inner_prefix = indent + "  " + branch
                typer.echo(
                    f"{inner_prefix}{n['id']:24s} factory={n['factory']:24s} cfg=[{cfg_keys}]"
                )
                if n["sub_spec_ref"]:
                    sub = n["sub_spec_ref"]
                    sub_line_prefix = indent + "  " + ("   " if i == last else "│  ")
                    typer.echo(
                        f"{sub_line_prefix}  ⤷ sub_spec_ref → {sub.get('plan_ref')} "
                        f"(entry={sub.get('entry_node')})"
                    )
            for child in layer.get("children", []):
                _render_layer(child, (*prefix_chain, "│") if nodes else prefix_chain)

        for layer in layers:
            _render_layer(layer, ("",))
            typer.echo("")

        if top_invalid:
            typer.echo("✗ top phase_graph validation failed", err=True)
            raise typer.Exit(1)
        if any_layer_failed:
            typer.echo("✗ one or more subgraph layers failed to inflate", err=True)
            raise typer.Exit(1)
        typer.echo("✓ all layers inflated and validated")

    @plan_app.command("relations")
    def plan_relations(
        plugin: str = typer.Option(..., "--plugin", "-p", help="plugin id"),
        profile: Path = typer.Option(
            Path("profiles/web-standard.yaml"),
            "--profile",
            help="Profile YAML to compile for relations lookup",
        ),
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """编译 Profile 并列出指定 plugin 的出/入关系。"""
        if not plugin:
            _fail("plan relations: --plugin <id> required")
        from lca.contracts.protocols.perceive.capability_plan import (
            relations_from_plugin,
            relations_to_plugin,
        )

        try:
            resolved = resolve_profile(profile)
            plan = compile_plan(resolved)
        except (OSError, ValueError) as exc:
            _fail(f"plan relations: {exc}")
        outgoing = relations_from_plugin(plan.capability, plugin)
        incoming = relations_to_plugin(plan.capability, plugin)
        if json_mode:
            payload = {
                "plugin_id": plugin,
                "profile": str(profile),
                "outgoing": [
                    {"kind": r.kind.value, "target": r.target, "weight": r.weight} for r in outgoing
                ],
                "incoming": [
                    {"kind": r.kind.value, "source": r.source, "weight": r.weight} for r in incoming
                ],
            }
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        typer.echo(f"plan relations: plugin_id={plugin} profile={profile}")
        typer.echo(f"  outgoing ({len(outgoing)}):")
        for r in outgoing:
            typer.echo(f"    {r.kind.value} → {r.target}")
        typer.echo(f"  incoming ({len(incoming)}):")
        for r in incoming:
            typer.echo(f"    {r.source} → {r.kind.value}")

    @app.command(name="audit")
    def audit(
        target: str = typer.Argument(..., help="只支持 declarative-boundaries"),
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """审计最小可信内核与 GraphAssembler 的声明式边界。"""
        if target != "declarative-boundaries":
            _fail("audit only supports declarative-boundaries")
        report = audit_declarative_boundaries(Path.cwd())
        emit_report(report, json_mode=json_mode)
        if report["violations"]:
            raise typer.Exit(1)


def _emit_plan_templates(*, json_mode: bool) -> None:
    from lca.contracts.atoms.plan.template import (
        all_plan_template_ids,
        plan_template_to_dict,
        standard_plan_templates,
    )

    templates = standard_plan_templates()
    payload = {
        "count": len(templates),
        "template_ids": [template.value for template in all_plan_template_ids()],
        "templates": [plan_template_to_dict(template) for template in templates],
    }
    if json_mode:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"PlanTemplate count: {payload['count']}")
    for template in templates:
        typer.echo(
            f"  {template.template_id}: {template.name} ({template.scope.value}) — "
            f"{len(template.relations)} relations, {len(template.control_slots)} slots, "
            f"{len(template.required_groups)} groups"
        )


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise typer.Exit(2)


__all__ = [
    "audit_declarative_boundaries",
    "explain_declarative_plan",
    "register",
    "render_declarative_graph",
]
