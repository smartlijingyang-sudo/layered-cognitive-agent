"""Development workflow commands: dev, restart, stop, status, heal, provision."""

from __future__ import annotations

from pathlib import Path

import typer

from lca.infrastructure.cli.commands._shared import make_context
from lca.infrastructure.cli.pipeline import build_pipeline


def register(app: typer.Typer) -> None:
    """Register workflow commands on the typer app."""

    @app.command()
    def dev(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """第一次或全停之后：起 infra + gateway + lobehub + daemon。"""
        ctx = make_context(json_mode, quiet, config)
        pipeline = build_pipeline(
            "dev",
            ["infra.ensure", "gateway.ensure", "lobehub.ensure", "lobehub.start", "daemon.start"],
        )
        pipeline.execute(ctx)
        if ctx.failed:
            ctx.console.verdict(False, "Development environment failed to start")
            raise typer.Exit(1)
        ctx.console.verdict(True, "Development environment ready")

    @app.command()
    def restart(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """全停再起。日常异常用 heal，不要先 restart。"""
        ctx = make_context(json_mode, quiet, config)
        pipeline = build_pipeline(
            "restart",
            [
                "stack.stop",
                "infra.ensure",
                "gateway.restart",
                "lobehub.ensure",
                "lobehub.start",
                "daemon.restart",
            ],
        )
        pipeline.execute(ctx)
        if ctx.failed:
            ctx.console.verdict(False, "Restart failed")
            raise typer.Exit(1)
        ctx.console.verdict(True, "All services restarted")

    @app.command()
    def stop(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """停 daemon / lobehub / gateway / infra。"""
        ctx = make_context(json_mode, quiet, config)
        pipeline = build_pipeline("stop", ["stack.stop"])
        pipeline.execute(ctx)
        ctx.console.verdict(True, "All services stopped")

    @app.command()
    def status(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """看五个服务现在怎样。异常会写出原因。heal 会自己修。"""
        ctx = make_context(json_mode, quiet, config)
        pipeline = build_pipeline("status", ["stack.status"])
        pipeline.execute(ctx)
        ctx.console.flush()

    @app.command()
    def heal(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """自己修：缺的容器拉起、过期 gateway 重启、daemon 连上。不用再拆命令。"""
        ctx = make_context(json_mode, quiet, config)
        pipeline = build_pipeline("heal", ["stack.heal"])
        pipeline.execute(ctx)
        if ctx.failed:
            ctx.console.verdict(False, "heal finished with remaining problems")
            raise typer.Exit(1)
        ctx.console.verdict(True, "All services healthy")

    @app.command()
    def provision(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """装系统包、venv、sandbox 用户、工作区、CLI。新机器跑一次。"""
        ctx = make_context(json_mode, quiet, config)
        pipeline = build_pipeline("provision", ["host.provision", "daemon.ensure"])
        pipeline.execute(ctx)
        if ctx.failed:
            ctx.console.verdict(False, "provision failed")
            raise typer.Exit(1)
        ctx.console.verdict(True, "host provisioned")
