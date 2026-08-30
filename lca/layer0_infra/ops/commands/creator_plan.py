"""Creator four-face protocol (ADR-0074 §三) + plan management commands."""

from __future__ import annotations

import json
import sys

import typer


def register(app: typer.Typer) -> None:
    """Register creator and plan commands on the typer app."""

    @app.command(name="creator")
    def creator_cmd(
        face: str = typer.Option(
            "inspect",
            "--face",
            "-f",
            help="Creator face: inspect / author / validate / promote",
        ),
        name: str = typer.Option(
            "", "--name", "-n", help="plugin name (required for author/validate/promote)"
        ),
        path: str = typer.Option("", "--path", "-p", help="plugin source path (for author face)"),
        preset_id: str = typer.Option(
            "", "--preset-id", help="preset id (for promote with target_scope=release)"
        ),
        target_scope: str = typer.Option(
            "", "--target-scope", help="promote target scope: release / experiment / run / ..."
        ),
        rollback: bool = typer.Option(
            False, "--rollback", help="promote rollback=True → ACTIVE → RETIRED"
        ),
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Creator 4 faces (ADR-0074 §三 + PR-9 V7 acceptance).

        4 faces（ADR-0074 §三裁剪 7 → 4）：

        - inspect —— read-only; inspect Context 派生能力图
        - author —— write to DRAFT
        - validate —— descriptor / signature / dependencies
        - promote —— DRAFT → VERIFIED → ACTIVE；rollback=True → RETIRED

        stage / retire / publish 三个旧 action 通过 promote flags 实现
        （legacy backward compat 6 个月后删除）。
        """
        from lca.plugins.creator.faces import (
            CreatorFace,
            PromoteSpec,
            parse_creator_face,
        )
        from lca.plugins.creator.faces.implementations import (
            dispatch_creator_face,
        )

        try:
            face_enum = parse_creator_face(face)
        except (ValueError, TypeError) as exc:
            print(f"creator: invalid face {face!r}: {exc}", file=sys.stderr)
            raise typer.Exit(2) from exc

        spec = None
        if face_enum is CreatorFace.PROMOTE:
            spec = PromoteSpec(
                target_scope=target_scope or None,
                rollback=rollback,
                preset_id=preset_id or None,
            )

        try:
            result = dispatch_creator_face(
                face_enum,
                name=name,
                path=path or None,
                spec=spec,
            )
        except ValueError as exc:
            print(f"creator: {exc}", file=sys.stderr)
            raise typer.Exit(2) from exc

        if json_mode:
            sys.stdout.write(
                json.dumps(
                    {
                        "face": result.face.value,
                        "state_after": result.state_after.value,
                        "payload": result.payload,
                        "plan_ref": result.plan_ref,
                        "metadata": result.metadata,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            sys.stdout.write("\n")
        else:
            print(f"face: {result.face.value}")
            print(f"state_after: {result.state_after.value}")
            if result.payload:
                print(f"payload: {result.payload}")
            if result.plan_ref:
                print(f"plan_ref: {result.plan_ref}")
        raise typer.Exit(0)

    @app.command(name="plan")
    def plan_cmd(
        command: str | None = typer.Argument(
            None,
            metavar="[COMMAND]",
            help="Plan command: list-templates / relations",
        ),
        subcommand: str | None = typer.Option(
            None,
            "--sub",
            "-s",
            help="Compatibility alias for the positional plan command",
        ),
        template_id: str = typer.Option(
            "", "--template", "-t", help="template id (for relations subcommand)"
        ),
        plugin_id: str = typer.Option(
            "", "--plugin", "-p", help="plugin id (for relations subcommand)"
        ),
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    ) -> None:
        """Plan management (PR-12 + V12 acceptance §4.6)."""
        if command and subcommand and command != subcommand:
            print(
                f"plan: positional command {command!r} conflicts with --sub {subcommand!r}",
                file=sys.stderr,
            )
            raise typer.Exit(2)
        selected_command = command or subcommand or "list-templates"

        if selected_command == "list-templates":
            from lca.contracts.atoms.plan_template import (
                all_plan_template_ids,
                plan_template_to_dict,
                standard_plan_templates,
            )

            templates = standard_plan_templates()
            if json_mode:
                sys.stdout.write(
                    json.dumps(
                        {
                            "count": len(templates),
                            "template_ids": [t.value for t in all_plan_template_ids()],
                            "templates": [plan_template_to_dict(t) for t in templates],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                sys.stdout.write("\n")
            else:
                print(f"PlanTemplate count: {len(templates)}")
                for t in templates:
                    print(
                        f"  {t.template_id}: {t.name} ({t.scope.value}) — "
                        f"{len(t.relations)} relations, "
                        f"{len(t.control_slots)} slots, "
                        f"{len(t.required_groups)} groups"
                    )
            raise typer.Exit(0)

        if selected_command == "relations":
            if not plugin_id:
                print("plan relations: --plugin <id> required", file=sys.stderr)
                raise typer.Exit(2)
            from lca.contracts.protocols.capability_plan import (
                relations_from_plugin,
                relations_to_plugin,
            )
            from lca.harness.profile.plan_compiler import compile_plan
            from lca.harness.profile.resolve import resolve_profile

            try:
                resolved = resolve_profile("profiles/web-standard.yaml")
                plan = compile_plan(resolved)
            except Exception as exc:
                print(f"plan relations: resolve failed: {exc}", file=sys.stderr)
                raise typer.Exit(2) from exc

            outgoing = relations_from_plugin(plan.capability, plugin_id)
            incoming = relations_to_plugin(plan.capability, plugin_id)

            if json_mode:
                sys.stdout.write(
                    json.dumps(
                        {
                            "plugin_id": plugin_id,
                            "outgoing": [
                                {
                                    "kind": r.kind.value,
                                    "target": r.target,
                                    "weight": r.weight,
                                }
                                for r in outgoing
                            ],
                            "incoming": [
                                {
                                    "kind": r.kind.value,
                                    "source": r.source,
                                    "weight": r.weight,
                                }
                                for r in incoming
                            ],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                sys.stdout.write("\n")
            else:
                print(f"plan relations: plugin_id={plugin_id}")
                print(f"  outgoing ({len(outgoing)}):")
                for r in outgoing:
                    print(f"    {r.kind.value} → {r.target}")
                print(f"  incoming ({len(incoming)}):")
                for r in incoming:
                    print(f"    {r.source} → {r.kind.value}")
            raise typer.Exit(0)

        print(f"plan: unknown command {selected_command!r}", file=sys.stderr)
        raise typer.Exit(2)
