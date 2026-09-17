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

from lca.infrastructure.cli.commands.kernel._shared import make_context
from lca.infrastructure.cli.pipeline.pipeline import build_pipeline


def register(app: typer.Typer) -> None:
    """Register workflow commands on the typer app."""

    @app.command()
    def stop(
        json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
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
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
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
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
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
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
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
        config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
    ) -> None:
        """LCA 进程本地便捷重启 — supervisor SIGTERM+spawn,后接 SOP 报告。

        ADR-0119 决定 4: lca-ops 不长管 LCA 进程 (生产由 supervisor 守护)。
        本命令给"改完代码 / 换 profile / 强制刷新"用的本地快捷方式,
        委托给 :class:`KernelSupervisor` 做 SIGTERM → 等 → spawn → readiness。

        重启就绪后,自动跑三段 SOP 报告,任何一段 fail-loud 都会让 exit code 非 0:

          1. boot_check   —— profile resolve + plan lift 校验
          2. fiber_report —— 最新 kernel stderr 的 ``boot.pending_event`` 统计
          3. health_probe —— GET /health 并核对 plugin registered/expected/fiber_count

        三段报告原语统一复用现有的 ``kernel_check`` / ``kernel_boot_log``
        / ``health_body_ok``,不引入新的诊断路径,见
        :mod:`lca.infrastructure.cli.services.kernel.restart_report`。
        CI 关掉人类可读横幅:LCA_KERNEL_RESTART_QUIET=1。

        Output shape (--json): 在 supervisor 的 ``{verdict, status, detail,
        next_command}`` 之外并入 ``report`` 字段(JSON 形态见
        :meth:`RestartReport.to_dict`)。
        """

        from lca.infrastructure.cli.commands.kernel.supervisor import (
            _render,
        )
        from lca.infrastructure.cli.config.config import OpsConfig
        from lca.infrastructure.cli.services.kernel import restart_report
        from lca.infrastructure.cli.services.kernel.supervisor import (
            build_restart_result,
            default_program_config,
            get_supervisor,
        )

        # profile/host/port 取 lca-ops.yaml 的 ``kernel_serve``(SSOT),与 heal
        # 的 KernelServeSpawner 同源:只读 OpsConfig,不建 PipelineContext。
        kernel_serve = OpsConfig.load(config).kernel_serve
        cfg = default_program_config(
            profile=kernel_serve.profile,
            host=kernel_serve.host,
            port=kernel_serve.port,
        )
        sup = get_supervisor(cfg)
        # Prune stale per-PID stderr files left behind by previous standalone
        # ``lca_kernel serve`` runs (no supervisor in front of them). The
        # supervisor truncates its own stdout/stderr log on start, so only
        # the orphan files need scrubbing here.
        _prune_legacy_kernel_logs()
        sup.restart()
        ready = sup.wait_ready(timeout=cfg.readiness_timeout)
        status = sup.status()

        # ``cfg.host()``/``cfg.port()`` live on ProgramConfig; tests that
        # pass a SimpleNamespace mock (see
        # test_kernel_restart_does_not_construct_a_pipeline_context) need a
        # fallback so the SOP report can still address the kernel.
        cfg_host = getattr(cfg, "host", lambda: "127.0.0.1")()
        cfg_port = getattr(cfg, "port", lambda: 8765)() or 8765

        # Post-restart SOP report (boot check + fiber report + health probe).
        # Failures here escalate to non-zero exit so CI/scripts catch them,
        # even if the supervisor itself declared ready.
        report = restart_report.run_restart_report(
            profile=Path(kernel_serve.profile),
            host=cfg_host,
            port=cfg_port,
            supervisor_state=status.state.value,
            supervisor_last_event=status.last_event,
        )
        payload = build_restart_result(cfg, status, ready=ready)
        payload["report"] = report.to_dict()
        if not report.ok:
            payload["verdict"] = "failed"
            payload["detail"] = (
                f"restart ok but post-restart report failed: "
                f"{sum(1 for f in report.findings if f.severity == 'error')} error(s)"
            )
            payload["next_command"] = (
                report.next_command
                or "./scripts/lca-ops kernel-supervisor logs --name lca_kernel_dev"
            )

        if json_mode:
            # ``payload['status']`` is a ProgramStatus dataclass; coerce
            # to a dict so the JSON encoder does not have to know about
            # the supervisor's frozen dataclass.
            import dataclasses as _dc

            if _dc.is_dataclass(payload["status"]):
                payload["status"] = _dc.asdict(payload["status"])
            typer.echo(__import__("json").dumps(payload, indent=2, ensure_ascii=False))
        else:
            _render(payload, json_mode=False)
            if not restart_report.should_quiet():
                typer.echo(restart_report.render_text(report))

        if not ready or not report.ok:
            raise typer.Exit(1)


def _prune_legacy_kernel_logs() -> None:
    """Reset kernel log state so each restart starts from a clean slate.

    Two operations:

    1. Drop orphan ``lca-kernel.stderr.<pid>.<ts>.log`` files under /tmp.
       These are written by the standalone ``lca_kernel serve`` path
       (no supervisor in front). They are not used by the supervisor's
       log, so they would only sit on disk and confuse any human who
       greps ``/tmp/lca-kernel.stderr.*.log`` after a restart.

    2. Truncate ``/tmp/lca-kernel.{stdout,stderr}.log`` to zero bytes.
       The supervisor appends to these across restarts; truncating them
       here keeps the post-restart SOP report's fiber tally scoped to
       THIS boot without inventing PID-based anchors (the kernel writes
       boot.pending_event lines to stdout and the report reads stdout).
       We do this BEFORE calling ``sup.restart()`` so the kernel never
       sees a partially-truncated file mid-boot.

    Best-effort: any failure is swallowed because losing the cleanup
    is not worth aborting the restart — the supervisor still owns the
    kernel lifecycle and the post-restart report will surface the real
    failure mode.
    """
    import contextlib
    from pathlib import Path as _Path

    for legacy in _Path("/tmp").glob("lca-kernel.stderr.*.log"):  # noqa: S108 — supervisor-owned log dir
        if legacy.name == "lca-kernel.stderr.log":
            continue  # supervisor's stderr; handled by the truncate below
        with contextlib.suppress(OSError):
            legacy.unlink()

    # NOTE: do NOT truncate /tmp/lca-kernel.{stdout,stderr}.log here.
    # Truncating the supervisor's append-only log from outside the
    # supervisor's lifecycle confuses its fd handling on the next spawn
    # and causes exit=1 within 2-3 seconds (see git history). The SOP
    # report must slice its scope via the kernel stderr's
    # ``Started server process [<pid>]`` banner instead.
