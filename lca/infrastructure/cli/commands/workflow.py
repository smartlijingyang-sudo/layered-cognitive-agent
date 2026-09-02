"""Development workflow commands: stop, status, heal, provision.

ADR-0119 决定 4: ``dev`` 与 ``restart`` 已删除 —— 这两个子命令引用
``gateway.ensure`` / ``gateway.restart`` 死 step,跑必崩。LCA 进程入口
已切到 ``uv run python -m lca_kernel serve ...``,详见 GUIDE banner 的
"LCA 进程 (kernel serve)" 章节。``stop`` 仍保留:它只停外部平台服务
(daemon / lobehub / infra),不含 LCA 进程。
"""

from __future__ import annotations

from pathlib import Path

import typer

from lca.infrastructure.cli.commands._shared import make_context
from lca.infrastructure.cli.pipeline import build_pipeline


def register(app: typer.Typer) -> None:
    """Register workflow commands on the typer app."""

    @app.command()
    def stop(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """停 daemon / lobehub / infra。不含 LCA 进程(kernel serve 自管)。"""
        ctx = make_context(json_mode, quiet, config)
        pipeline = build_pipeline("stop", ["stack.stop"])
        pipeline.execute(ctx)
        ctx.console.verdict(True, "All external services stopped")

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

    @app.command(name="kernel-restart")
    def kernel_restart(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),  # noqa: B008
    ) -> None:
        """LCA 进程本地便捷重启: SIGTERM 现有 → 等 K6 dispose → spawn 新。

        ADR-0119 决定 4: lca-ops 不长管 LCA 进程 (生产由 supervisor 守护)。
        本命令给"改完代码 / 换 profile / 强制刷新"用的本地快捷方式。
        旧进程被 SIGTERM,K6 ``run_kernel_lifespan`` LIFO dispose,然后
        ``KernelServeService._spawn`` 拉起新 worker。

        与 ``heal`` 区别: heal 不重启健康进程,只补缺失进程。
        """
        ctx = make_context(json_mode, quiet, config)
        ks = ctx.registry.get("kernel_serve")
        state = ks.restart()
        ctx.console.service_state("kernel_serve", state)
        if not state.is_running:
            ctx.console.verdict(False, f"kernel_restart failed: {state.why or state.detail}")
            raise typer.Exit(1)
        ctx.console.verdict(True, "LCA kernel restarted")
