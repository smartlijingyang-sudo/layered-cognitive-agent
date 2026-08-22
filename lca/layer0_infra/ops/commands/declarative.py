"""ADR-0075 声明式计划 CLI。"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import typer

from lca.contracts.protocols.plan import compiled_run_plan_to_dict
from lca.harness.profile.plan_compiler import compile_plan, explain_compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.layer0_infra.ops.commands._shared import emit_report


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
            "valid": plan.validation_report.is_valid,
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
        task_contract: Path | None = typer.Option(None, "--task-contract", help="TaskContract 文件"),
        output: Path | None = typer.Option(None, "--output", "-o", help="写入 canonical JSON"),
        json_mode: bool = typer.Option(False, "--json", help="输出 JSON"),
    ) -> None:
        """编译 Profile 为 canonical CompiledRunPlan v2。"""
        task_ref = str(task_contract) if task_contract is not None else None
        try:
            from lca.harness.profile.plan_compiler import CompileOptions

            plan = compile_plan(
                resolve_profile(profile), options=CompileOptions(task_id=task_ref)
            )
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


def explain_declarative_plan(profile: Path) -> dict[str, Any]:
    """供 ``explain plan`` 命令复用的完整 plan provenance 投影。"""
    plan = compile_plan(resolve_profile(profile))
    return explain_compile_plan(plan)


def render_declarative_graph(profile: Path) -> str:
    """以 Mermaid 输出 capability / phase / replacement 图。"""
    plan = compile_plan(resolve_profile(profile))
    lines = ["flowchart LR"]
    if plan.phase_graph:
        for node in plan.phase_graph.nodes:
            lines.append(f'  {node.id.replace(".", "_")}["{node.semantic_phase.value}"]')
        for edge in plan.phase_graph.edges:
            lines.append(f"  {edge.source.replace('.', '_')} --> {edge.target.replace('.', '_')}")
    for decision in plan.replacement_map:
        lines.append(f'  "{decision.winner}" -. replaces .-> "{decision.target}"')
    return "\n".join(lines)


def audit_declarative_boundaries(root: Path) -> dict[str, Any]:
    """拒绝 MTK / GraphAssembler 基于实现身份进行业务分派。"""
    files = (
        root / "lca/contracts/protocols/declarative_phase_graph.py",
        root / "lca/harness/declarative/assembler.py",
        root / "lca/harness/declarative/interpreter.py",
    )
    violations: list[dict[str, Any]] = []
    forbidden = {"simple", "default"}
    for path in files:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                for operand in operands:
                    if (
                        isinstance(operand, ast.Constant)
                        and isinstance(operand.value, str)
                        and (operand.value in forbidden or operand.value.startswith("plugin."))
                    ):
                        violations.append(
                                {
                                    "path": str(path.relative_to(root)),
                                    "line": node.lineno,
                                    "message": "identity-based dispatch in trusted kernel",
                                }
                            )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "type":
                violations.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": node.lineno,
                        "message": "type-based dispatch in trusted kernel",
                    }
                )
    return {
        "audit": "declarative-boundaries",
        "scanned": [str(path.relative_to(root)) for path in files],
        "violations": violations,
        "valid": not violations,
    }


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise typer.Exit(2)


__all__ = [
    "audit_declarative_boundaries",
    "explain_declarative_plan",
    "register",
    "render_declarative_graph",
]
