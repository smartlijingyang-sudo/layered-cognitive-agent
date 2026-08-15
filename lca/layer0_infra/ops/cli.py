"""CLI entry point — typer app with all commands.

Design: commands compose steps from the step registry.
All output goes through Console (rich or JSON).
All service access goes through ServiceRegistry.
"""

from __future__ import annotations

from pathlib import Path

import typer

# Import steps to register them
import lca.layer0_infra.ops.steps  # noqa: F401
from lca.layer0_infra.ops.config import OpsConfig
from lca.layer0_infra.ops.console import Console, ConsoleConfig
from lca.layer0_infra.ops.pipeline import PipelineContext, build_pipeline
from lca.layer0_infra.ops.services import build_registry
from lca.layer0_infra.ops.state import StateStore

GUIDE = """\
LCA 开发平台编排  ./scripts/lca-ops

日常只记三句
  ./scripts/lca-ops status     看现在怎样
  ./scripts/lca-ops heal       有问题就修，不用再拆命令
  ./scripts/lca-ops logs       看日志（默认 gateway）

────────────────────────────────
全站
────────────────────────────────
status
  看 infra / gateway / lobehub / daemon。异常会写出原因。
  ./scripts/lca-ops status
  ./scripts/lca-ops status --json          给 agent 用

heal
  自己把不健康的服务拉起来（复用已有容器、重启过期 gateway、连 daemon）。
  ./scripts/lca-ops heal

dev
  第一次或全停之后：起 infra + gateway + lobehub + daemon。
  ./scripts/lca-ops dev

restart
  全停再起。setup 已做好会跳过。日常异常优先 heal，不要先 restart。
  ./scripts/lca-ops restart

stop
  停 daemon / lobehub / gateway / infra。
  ./scripts/lca-ops stop

────────────────────────────────
日志  logs
────────────────────────────────
文件
  gateway    .lca-ops/gateway.log     API / uvicorn
  lobehub    .lca-ops/lobehub.log     Next.js / bun dev
  daemon     /home/sandbox-user/.lca/daemon.log

  ./scripts/lca-ops logs                 gateway，默认 tail -f
  ./scripts/lca-ops logs lobehub         前端，同样跟着刷
  ./scripts/lca-ops logs daemon          sandbox 连接器
  ./scripts/lca-ops logs -n 200          先打 200 行再跟着刷
  ./scripts/lca-ops logs -F              只打一次，不跟随

────────────────────────────────
单服务
────────────────────────────────
gateway    LCA API  :8765     日志 .lca-ops/gateway.log
  start | stop | restart | status
  ./scripts/lca-ops gateway restart

lobehub    Next 前端 :3010    日志 .lca-ops/lobehub.log
  start | stop | restart | status | ensure
  ensure = 源码 / 补丁 / .env / bun install，不启进程
  ./scripts/lca-ops lobehub restart

infra      postgres / redis / s3
  start | stop | status
  start 只补缺的（已有 lobe-postgres:25432 会复用）
  ./scripts/lca-ops infra start

daemon     sandbox-user 连 gateway
  start | stop | status | ensure
  ensure     部署 /opt/lca CLI
  provision  装包 / venv / 建用户 / 工作区 / CLI（原 lca-host.py）
  ./scripts/lca-ops daemon start
  ./scripts/lca-ops provision

────────────────────────────────
通用参数
────────────────────────────────
  --json           结构化 JSON（agent）
  -q / --quiet     少说话
  -c PATH          配置，默认 ./lca-ops.yaml
  密码文件         .lobehub-stack/sudo.pass
"""


app = typer.Typer(
    name="lca-ops",
    help=GUIDE,
    rich_markup_mode=None,
    add_completion=False,
    invoke_without_command=True,
    context_settings={"help_option_names": []},
)


@app.callback()
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(GUIDE)
        raise typer.Exit(0)


def _make_context(
    json_mode: bool = False,
    quiet: bool = False,
    config_path: Path | None = None,
) -> PipelineContext:
    """Build a PipelineContext from CLI options."""
    config = OpsConfig.load(config_path)
    console = Console(ConsoleConfig(json_mode=json_mode, quiet=quiet))
    registry = build_registry(config)
    state = StateStore(config.state_dir)
    return PipelineContext(
        config=config,
        registry=registry,
        state=state,
        console=console,
    )


# ── Development Workflow ──────────────────────────────────────────────


@app.command()
def dev(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
    config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
) -> None:
    """第一次或全停之后：起 infra + gateway + lobehub + daemon。"""
    ctx = _make_context(json_mode, quiet, config)
    pipeline = build_pipeline(
        "dev",
        ["infra.ensure", "gateway.ensure", "lobehub.ensure", "lobehub.start", "daemon.start"],
    )
    pipeline.execute(ctx)
    if ctx.failed:
        ctx.console.verdict(False, "Development environment failed to start")
        raise typer.Exit(1)
    else:
        ctx.console.verdict(True, "Development environment ready")


@app.command()
def restart(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
    config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
) -> None:
    """全停再起。日常异常用 heal，不要先 restart。"""
    ctx = _make_context(json_mode, quiet, config)
    pipeline = build_pipeline(
        "restart",
        [
            "stack.stop",
            "infra.ensure",
            "daemon.restart",
            "gateway.restart",
            "lobehub.ensure",
            "lobehub.start",
        ],
    )
    pipeline.execute(ctx)
    if ctx.failed:
        ctx.console.verdict(False, "Restart failed")
        raise typer.Exit(1)
    else:
        ctx.console.verdict(True, "All services restarted")


@app.command()
def stop(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
    config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
) -> None:
    """停 daemon / lobehub / gateway / infra。"""
    ctx = _make_context(json_mode, quiet, config)
    pipeline = build_pipeline("stop", ["stack.stop"])
    pipeline.execute(ctx)
    ctx.console.verdict(True, "All services stopped")


@app.command()
def status(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="少输出"),
    config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
) -> None:
    """看四个服务现在怎样。异常会写出原因。heal 会自己修。"""
    ctx = _make_context(json_mode, quiet, config)
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
    ctx = _make_context(json_mode, quiet, config)
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
    ctx = _make_context(json_mode, quiet, config)
    pipeline = build_pipeline("provision", ["host.provision", "daemon.ensure"])
    pipeline.execute(ctx)
    if ctx.failed:
        ctx.console.verdict(False, "provision failed")
        raise typer.Exit(1)
    ctx.console.verdict(True, "host provisioned")


# ── Individual Service Commands ───────────────────────────────────────


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
            "          ./scripts/lca-ops logs gateway -f\n"
        )
        raise typer.Exit(0)
    ctx = _make_context(json_mode, quiet, config)
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
            "          ./scripts/lca-ops logs lobehub -n 100\n"
        )
        raise typer.Exit(0)
    ctx = _make_context(json_mode, quiet, config)
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
    ctx = _make_context(json_mode, quiet, config)
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
    ctx = _make_context(json_mode, quiet, config)
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


# ── Logs Command ──────────────────────────────────────────────────────


@app.command()
def logs(
    service: str = typer.Argument(
        "gateway",
        help="gateway | lobehub | daemon。默认跟着刷",
    ),
    follow: bool = typer.Option(
        True, "--follow/--no-follow", "-f/-F", help="默认跟着刷；-F 只打一次"
    ),
    lines: int = typer.Option(50, "--lines", "-n", help="先打最近多少行再跟着刷"),
    config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
) -> None:
    """默认 tail -f。gateway=.lca-ops/gateway.log  lobehub=.lca-ops/lobehub.log"""
    import subprocess

    ops_config = OpsConfig.load(config)
    state_dir = ops_config.state_dir
    log_map = {
        "gateway": state_dir / "gateway.log",
        "lobehub": state_dir / "lobehub.log",
        "daemon": Path(f"/home/{ops_config.daemon.user}/.lca/daemon.log"),
    }
    if service not in log_map:
        print(f"Unknown service: {service}. Use: {', '.join(log_map)}")
        raise typer.Exit(1)

    log_file = log_map[service]
    if not log_file.exists():
        print(f"No log yet: {log_file}")
        raise typer.Exit(1)

    cmd = ["tail", "-f" if follow else f"-n{lines}", str(log_file)]
    if follow:
        cmd = ["tail", "-f", "-n", str(lines), str(log_file)]
    subprocess.run(cmd)


# ── Entry Point ───────────────────────────────────────────────────────


def main() -> None:
    """Entry point for scripts/lca-ops."""
    app()


if __name__ == "__main__":
    main()
