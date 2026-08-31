"""Individual service management commands: lobehub, infra, daemon, onlyboxes.

ADR-0119 决定 4:lca-ops 不再管 LCA 进程 — LCA 进程入口是
``python -m lca_kernel serve``,SIGTERM 由 K6 ``lca_kernel.lifecycle`` 守护。
本模块只管 lobehub / infra / daemon / onlyboxes 等外部平台服务。
"""

from __future__ import annotations

from pathlib import Path

import typer

from lca.infrastructure.cli.commands._shared import make_context
from lca.infrastructure.cli.pipeline import build_pipeline


def register(app: typer.Typer) -> None:
    """Register service commands on the typer app.

    ADR-0119 决定 4:``gateway`` 子命令已删除 —— LCA 进程由
    ``python -m lca_kernel serve`` 直管,不需要 ``lca-ops gateway start/stop/restart``。
    """

    @app.command()
    def lobehub(
        action: str = typer.Argument(None, help="start | stop | restart | status | ensure"),
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """Next 前端 :3010。日志 .lca-ops/lobehub.log。ensure=源码补丁依赖，不启进程。"""
        if action is None:
            typer.echo(
                "lobehub  Next 前端  :3010\n"
                "  日志    .lca-ops/lobehub.log\n"
                "  动作    start | stop | restart | status | ensure\n"
                "  ensure  同步源码、打补丁、写 .env、bun install\n"
                "  注意    lobehub 自身不带 LCA 后端;后端进程见 ./scripts/lca-ops kernel_serve\n"
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
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """postgres / redis / s3。start 只补缺的，已有容器会复用。"""
        if action is None:
            typer.echo(
                "infra  postgres :25432  redis :6379  s3 按 .env\n"
                "  动作    start | stop | status\n"
                "  start   端口不通才 docker compose up，不拆已有 lobe-postgres\n"
                "  注意    lca-ops 不管 LCA 进程(kernel serve);infra 与 kernel 独立\n"
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
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
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
                "  注意    daemon 连的是 kernel serve,不是 lca-ops 自身\n"
                "  例子    ./scripts/lca-ops daemon restart\n"
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
