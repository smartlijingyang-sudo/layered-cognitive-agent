"""Creator four-face protocol (ADR-0074 §三).

``plan`` subcommands live in ``lca.infrastructure.cli.commands.declarative``
(``plan_app``), not here. Earlier revisions registered a flat ``plan``
typer on this module too, but the later ``plan_app`` wins and the
positional-arg handler was unreachable.
"""

from __future__ import annotations

import json
import sys

import typer


def register(app: typer.Typer) -> None:
    """Register the creator command on the typer app."""

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
