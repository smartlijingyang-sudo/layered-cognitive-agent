"""Typer commands for declarative plan compilation and inspection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from lca.harness.declarative.validation import is_validation_valid
from lca.harness.plan import compiled_run_plan_to_dict
from lca.harness.profile.plan_compiler import CompileOptions, compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.infrastructure.ops.commands._shared import emit_report
from lca.infrastructure.ops.commands.declarative_graph import (
    audit_declarative_boundaries,
    explain_declarative_plan,
    render_declarative_graph,
)


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
        declarative = raw.get("declarative") if isinstance(raw, dict) else None
        validation = declarative.get("validation_report") if isinstance(declarative, dict) else None
        if not isinstance(validation, dict):
            _fail("plan validate: input has no declarative validation report")
        report = {
            "plan_ref": raw.get("plan_ref", ""),
            "schema_version": raw.get("schema_version", ""),
            "valid": bool(validation.get("valid")),
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
        }
        emit_report(report, json_mode=json_mode)
        if not report["valid"]:
            raise typer.Exit(1)

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
        from lca.contracts.protocols.capability_plan import (
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
    from lca.contracts.atoms.plan_template import (
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
