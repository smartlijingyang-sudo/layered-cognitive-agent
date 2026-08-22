"""Individual service management commands: gateway, lobehub, infra, daemon."""

from __future__ import annotations

from pathlib import Path

import typer

from lca.layer0_infra.ops.commands._shared import make_context
from lca.layer0_infra.ops.pipeline import build_pipeline


def register(app: typer.Typer) -> None:
    """Register service commands on the typer app."""

    @app.command()
    def gateway(
        action: str = typer.Argument(None, help="start | stop | restart | status"),
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
    ) -> None:
        """LCA API :8765。日志 .lca-ops/gateway.log。动作：start stop restart status。"""
        if action is None:
            typer.echo(
                "gateway  LCA API  :8765\n"
                "  日志    .lca-ops/gateway.log\n"
                "  动作    start | stop | restart | status\n"
                "  例子    ./scripts/lca-ops gateway restart\n"
                "          ./scripts/lca-ops logs\n"
            )
            raise typer.Exit(0)
        ctx = make_context(json_mode, quiet, config)
        step_map = {
            "start": "gateway.start",
            "stop": "gateway.stop",
            "restart": "gateway.restart",
            "status": "stack.status",
        }
        if action not in step_map:
            ctx.console.error(f"未知动作 {action}。用: start stop restart status")
            raise typer.Exit(1)
        pipeline = build_pipeline(f"gateway.{action}", [step_map[action]])
        pipeline.execute(ctx)
        ctx.console.flush()

    @app.command()
    def lobehub(
        action: str = typer.Argument(None, help="start | stop | restart | status | ensure"),
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
    ) -> None:
        """Next 前端 :3010。日志 .lca-ops/lobehub.log。ensure=源码补丁依赖，不启进程。"""
        if action is None:
            typer.echo(
                "lobehub  Next 前端  :3010\n"
                "  日志    .lca-ops/lobehub.log\n"
                "  动作    start | stop | restart | status | ensure\n"
                "  ensure  同步源码、打补丁、写 .env、bun install\n"
                "  例子    ./scripts/lca-ops lobehub restart\n"
                "          ./scripts/lca-ops logs lobehub\n"
            )
            raise typer.Exit(0)
        ctx = make_context(json_mode, quiet, config)
        step_map = {
            "start": "lobehub.start",
            "stop": "lobehub.stop",
            "restart": "lobehub.restart",
            "status": "stack.status",
            "ensure": "lobehub.ensure",
        }
        if action not in step_map:
            ctx.console.error(f"未知动作 {action}。用: start stop restart status ensure")
            raise typer.Exit(1)
        pipeline = build_pipeline(f"lobehub.{action}", [step_map[action]])
        pipeline.execute(ctx)
        ctx.console.flush()

    @app.command()
    def infra(
        action: str = typer.Argument(None, help="start | stop | status"),
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
    ) -> None:
        """postgres / redis / s3。start 只补缺的，已有容器会复用。"""
        if action is None:
            typer.echo(
                "infra  postgres :25432  redis :6379  s3 按 .env\n"
                "  动作    start | stop | status\n"
                "  start   端口不通才 docker compose up，不拆已有 lobe-postgres\n"
                "  例子    ./scripts/lca-ops infra start\n"
            )
            raise typer.Exit(0)
        ctx = make_context(json_mode, quiet, config)
        step_map = {
            "start": "infra.start",
            "stop": "infra.stop",
            "status": "stack.status",
        }
        if action not in step_map:
            ctx.console.error(f"未知动作 {action}。用: start stop status")
            raise typer.Exit(1)
        pipeline = build_pipeline(f"infra.{action}", [step_map[action]])
        pipeline.execute(ctx)
        ctx.console.flush()

    @app.command()
    def daemon(
        action: str = typer.Argument(None, help="start | stop | restart | status | ensure"),
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
    ) -> None:
        """sandbox-user 连 gateway。日志 /home/sandbox-user/.lca/daemon.log。"""
        if action is None:
            typer.echo(
                "daemon  sandbox-user 连接器\n"
                "  日志    /home/sandbox-user/.lca/daemon.log\n"
                "  动作    start | stop | restart | status | ensure\n"
                "  ensure     感知源码变更 → 自动重建部署 packages/lca-cli\n"
                "  restart    stop + ensure + start（改完代码用这个）\n"
                "  整机首次    ./scripts/lca-ops provision\n"
                "  密码    .lobehub-stack/sudo.pass\n"
                "  例子    ./scripts/lca-ops daemon start\n"
                "          ./scripts/lca-ops daemon restart\n"
                "          ./scripts/lca-ops logs daemon\n"
            )
            raise typer.Exit(0)
        ctx = make_context(json_mode, quiet, config)
        step_map = {
            "start": "daemon.start",
            "stop": "daemon.stop",
            "restart": "daemon.restart",
            "status": "stack.status",
            "ensure": "daemon.ensure",
        }
        if action not in step_map:
            ctx.console.error(f"未知动作 {action}。用: start stop restart status ensure")
            raise typer.Exit(1)
        pipeline = build_pipeline(f"daemon.{action}", [step_map[action]])
        pipeline.execute(ctx)
        ctx.console.flush()
