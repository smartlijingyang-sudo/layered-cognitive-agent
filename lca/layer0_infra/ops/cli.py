"""CLI entry point — typer app with all commands.

Design: commands compose steps from the step registry.
All output goes through Console (rich or JSON).
All service access goes through ServiceRegistry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

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
  ./scripts/lca-ops logs       跟 journal 事实流

────────────────────────────────
全站
────────────────────────────────
status
  看 infra / gateway / lobehub / daemon / onlyboxes / dsh。异常会写出原因。
  onlyboxes 未钉 LCA terminal 镜像时会提示 configure-terminal-runtime。
  dsh 未建镜像时会提示 build-dsh-image。
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
  ./scripts/lca-ops logs              journal 事实流（模型所见即日志）
  ./scripts/lca-ops logs -v           + prompt/response/args/result
  ./scripts/lca-ops logs -d           + 增量事件（text/reasoning delta）
  ./scripts/lca-ops logs --replay     从 traces/lca_journal.jsonl 回放
  ./scripts/lca-ops logs lobehub      Next.js 进程日志
  ./scripts/lca-ops logs daemon       sandbox 连接器

  事实（decision / step / tool / llm）→ 观察（insight：冗余/循环/成本/关键路径）
  模型可见的一切都可从 journal 重建。

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
Run 复盘  coding-agent tools(ADR-0065 §六 / PR-9,只读)
────────────────────────────────
  7 个只读工具 —— trace / explain / optimize / graph-run / minimal-repro /
  diff-context / diff-runs / cost。默认走人类可读,加 --json 给 agent。
  ./scripts/lca-ops trace <run_id>           通用轨迹
  ./scripts/lca-ops explain <run_id>         失败路径投影
  ./scripts/lca-ops optimize <run_id>        优化候选(延迟/token/重试)
  ./scripts/lca-ops graph-run <run_id>       Mermaid 插件交互图
  ./scripts/lca-ops minimal-repro <run_id>   失败因果链 + evidence refs
  ./scripts/lca-ops diff-context <run_id>    同 run step 上下文
  ./scripts/lca-ops diff-runs <a> <b>        两次 run 对比
  ./scripts/lca-ops cost <run_id>            LlmCallCompleted 成本累加
  ./scripts/lca-ops evidence <run_id> <ref>  查 state_ref → evidence payload

  diagnose <alias> 已内置 4 个 alias:model-not-seen / loop-stuck /
  memory-poisoned / approval-rejected(看 DIAGNOSE_HINTS 拿修复建议)。

────────────────────────────
Audit 测量网  ADR-0074 PR-0（只读）
────────────────────────────
  4 个 AST 扫描器,让 reviewer 一行命令看清 hardcode 在哪。
  默认走人类可读,加 --json 给 agent。有发现时 exit 1（CI 可识别）。
  ./scripts/lca-ops audit-control-surface  Control Slot 投稿分布 + 缺 control 段
  ./scripts/lca-ops audit-state-writers     state.* 写入点(Reducer 单写校验基线)
  ./scripts/lca-ops audit-direct-commands   Body 直接 import sandbox/transport 的路径
  ./scripts/lca-ops audit-hook-attach       hooks.trigger / middleware_bag / _emit 残留

  ./scripts/lca-ops status-adr-supervision   一命令看 ADR-0066/0067/0068/0069/0074 监督状态
                                              = 验证 tracker.md 一致性 + 输出当前历史迁移基线
                                              (实现了 tracker 即实现 5 ADR)

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
    """看五个服务现在怎样。异常会写出原因。heal 会自己修。"""
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
            "          ./scripts/lca-ops logs\n"
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
            "          ./scripts/lca-ops logs lobehub\n"
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
    target: str = typer.Argument(
        "",
        help="空=journal 事实流；lobehub | daemon = 进程日志",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="显示完整字段（prompt/response/args/result）"
    ),
    deltas: bool = typer.Option(
        False, "--deltas", "-d", help="显示增量事件（text/reasoning/sandbox delta）"
    ),
    replay: bool = typer.Option(
        False, "--replay", "-r", help="从 traces/lca_journal.jsonl 回放（不连 SSE）"
    ),
    config: Path | None = typer.Option(None, "--config", "-c", help="配置文件"),
) -> None:
    """事实流。默认是 journal（思考/工具/步/洞察），不是 gateway.log。"""
    ops_config = OpsConfig.load(config)
    if target in {"", "journal", "gateway"}:
        _follow_journal(ops_config, verbose=verbose, show_deltas=deltas, replay=replay)
        return
    import subprocess

    log_map = {
        "lobehub": ops_config.state_dir / "lobehub.log",
        "daemon": Path(f"/home/{ops_config.daemon.user}/.lca/daemon.log"),
    }
    if target not in log_map:
        print(f"Unknown target: {target}. Use: journal, lobehub, daemon")
        raise typer.Exit(1)
    log_file = log_map[target]
    if not log_file.exists():
        print(f"No log yet: {log_file}")
        raise typer.Exit(1)
    subprocess.run(["/usr/bin/tail", "-f", str(log_file)])


def _follow_journal(
    ops_config: OpsConfig,
    *,
    verbose: bool = False,
    show_deltas: bool = False,
    replay: bool = False,
) -> None:
    """Resilient journal SSE consumer with rich fact-stream rendering.

    Three-layer architecture (model-visible = logged):
    - Transport: SSE connection with auto-reconnect + Last-Event-ID
    - Domain: SSE record → StampedEvent adapter
    - Render: FactStreamProjector (every event as a structured fact)

    ``--replay`` reads from the durable jsonl file instead of live SSE.
    Death detection only triggers on actual connection stalls (no SSE
    frames at all for 60s), not on absence of specific event types.
    Heartbeats keep the connection alive silently.
    """
    if replay:
        _replay_from_jsonl(verbose=verbose, show_deltas=show_deltas)
        return
    _stream_live(ops_config, verbose=verbose, show_deltas=show_deltas)


def _replay_from_jsonl(*, verbose: bool, show_deltas: bool) -> None:
    """Read the durable jsonl journal file and project every event."""
    from pathlib import Path

    from lca.layer0_infra.observability.journal.fact_stream_projector import (
        FactStreamProjector,
    )
    from lca.layer0_infra.observability.journal.journal_io import (
        JOURNAL_SCHEMA_VERSION,
        record_to_stamped,
    )

    jsonl_path = Path("traces/lca_journal.jsonl")
    if not jsonl_path.exists():
        print(f"No journal file at {jsonl_path}")
        raise typer.Exit(1)

    import json

    projector = FactStreamProjector(verbose=verbose, show_deltas=show_deltas)
    total = 0
    rendered = 0
    skipped = 0
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        try:
            record = json.loads(line)
            if record.get("schema") != JOURNAL_SCHEMA_VERSION:
                skipped += 1
                continue
            stamped = record_to_stamped(record)
            if stamped is not None:
                projector.on_event(stamped)
                rendered += 1
        except Exception:
            skipped += 1

    projector.close()
    print(f"\n── replay done: {rendered}/{total} events rendered, {skipped} skipped ──")


def _stream_live(
    ops_config: OpsConfig,
    *,
    verbose: bool,
    show_deltas: bool,
) -> None:
    """Live SSE consumer with fact-stream rendering.

    Death detection: only triggers when no SSE frames arrive for 60s
    (connection stall). Heartbeats and all event types reset the timer.
    This avoids false-positive "30s without cognitive events" messages
    during slow LLM calls or quiet periods.
    """
    import time as _time

    import httpx

    from lca.layer0_infra.observability.journal.fact_stream_projector import (
        FactStreamProjector,
    )
    from lca.layer0_infra.ops.journal_log import (
        extract_seq_from_record,
        parse_sse_block,
        sse_record_to_stamped,
    )

    url = f"{ops_config.gateway.base_url}/journal/live"
    projector = FactStreamProjector(verbose=verbose, show_deltas=show_deltas)
    last_seq = 0
    last_frame_ts = _time.monotonic()
    backoff = 1.0
    stall_timeout = 60.0
    max_backoff = 30.0

    while True:
        try:
            headers = {"Accept": "text/event-stream"}
            if last_seq > 0:
                headers["Last-Event-ID"] = str(last_seq)
            with (
                httpx.Client(timeout=httpx.Timeout(None, connect=5.0, read=120.0)) as client,
                client.stream("GET", url, headers=headers) as resp,
            ):
                if resp.status_code == 404:
                    print("gateway 还没有 /journal/live，先 ./scripts/lca-ops gateway restart")
                    raise typer.Exit(1)
                if resp.status_code != 200:
                    print(f"gateway 拒绝 journal 订阅（HTTP {resp.status_code}）")
                    raise typer.Exit(1)

                # Connected — reset backoff.
                backoff = 1.0
                buf = ""
                for chunk in resp.iter_text():
                    buf += chunk
                    # Any frame resets the stall timer.
                    last_frame_ts = _time.monotonic()
                    while "\n\n" in buf:
                        block, buf = buf.split("\n\n", 1)
                        record = parse_sse_block(block)
                        if record is None:
                            continue

                        # Track seq for reconnection.
                        seq = extract_seq_from_record(record)
                        if seq > last_seq:
                            last_seq = seq

                        # Convert to StampedEvent and feed fact-stream projector.
                        stamped = sse_record_to_stamped(record)
                        if stamped is not None:
                            projector.on_event(stamped)

                    # Stall detection: no frames at all for 60s.
                    if _time.monotonic() - last_frame_ts > stall_timeout:
                        print(f"\n⚠ journal 连接 60 秒无数据帧，主动重连（seq={last_seq}）...")
                        break

        except httpx.ConnectError:
            print(f"\n⚠ gateway 连接失败，{backoff:.0f}s 后重试...")
        except httpx.RemoteProtocolError:
            print(f"\n⚠ SSE 协议错误，{backoff:.0f}s 后重试...")
        except (httpx.ReadError, httpx.ReadTimeout, httpx.StreamError) as exc:
            print(f"\n⚠ 流中断（{type(exc).__name__}），{backoff:.0f}s 后从 seq={last_seq} 续播...")
        except KeyboardInterrupt:
            projector.close()
            raise typer.Exit(0) from None
        except Exception as exc:
            print(f"\n⚠ 未知错误（{type(exc).__name__}: {exc}），{backoff:.0f}s 后重试...")

        # Exponential backoff with cap.
        _time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


# ── Coding Agent Tools —— ADR-0065 §六 / PR-9 CLI 包装 ───────────────────────
#
# 7 个只读工具(TraceInspector / FailureExplainer / OptimizationFinder /
# PluginGraphRenderer / MinimalReproduction / DiffContext / RunDiff) 已在
# ``lca/layer0_infra/observability/coding_agent_tools/`` 实现;本节把它们
# 暴露成 ``lca-ops`` 子命令。全部 read-only;不调用 RunLedger.append。
# 每个子命令支持 ``--json`` 给 agent / 仪表盘消费;默认走人类可读渲染。


def _resolve_journal_path(jsonl: Path | None, run_id: str | None) -> Path:
    """Resolve journal.jsonl: 显式参数 → ``traces/lca_journal.jsonl`` →
    ``traces/runs/<run_id>/journal.jsonl``。
    """
    if jsonl is not None:
        if not jsonl.exists():
            print(f"No journal file at {jsonl}")
            raise typer.Exit(1)
        return jsonl
    default_global = Path("traces/lca_journal.jsonl")
    if default_global.exists():
        return default_global
    if run_id is not None:
        per_run = Path(f"traces/runs/{run_id}/journal.jsonl")
        if per_run.exists():
            return per_run
    print(f"No journal file found (tried {default_global} and traces/runs/<id>/journal.jsonl)")
    raise typer.Exit(1)


def _emit_report(report: object, *, json_mode: bool) -> None:
    """输出 coding_agent tool 的 report:json 模式全 dump,否则走 ``str()`` 渲染。"""
    if json_mode:
        typer.echo(json.dumps(report, ensure_ascii=False, default=str))
        return
    if isinstance(report, str):
        typer.echo(report)
        return
    if isinstance(report, dict):
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(report, list):
        for item in report:
            typer.echo(json.dumps(item, ensure_ascii=False, indent=2, default=str))
        return
    typer.echo(str(report))


@app.command(name="trace")
def trace(
    run_id: str = typer.Argument(..., help="Run id"),
    jsonl: Path = typer.Option(
        None, "--jsonl", help="journal.jsonl 路径(默认 traces/lca_journal.jsonl)"
    ),
    json_mode: bool = typer.Option(False, "--json", help="JSON 输出,给 agent"),
    focus: str = typer.Option("all", "--focus", help="焦点:all / llm / tools / delegation"),
    depth: int = typer.Option(24, "--depth", help="事件深度"),
) -> None:
    """检查一个 run 的 journal 轨迹(只读)。"""
    from lca.layer0_infra.observability.coding_agent_tools.trace_inspector_tool import (
        TraceInspectorToolImpl,
    )

    path = _resolve_journal_path(jsonl, run_id)
    report = TraceInspectorToolImpl(path).inspect_trace(run_id=run_id, focus=focus, depth=depth)
    _emit_report(report, json_mode=json_mode)


@app.command(name="explain")
def explain(
    run_id: str = typer.Argument(..., help="Run id"),
    jsonl: Path = typer.Option(None, "--jsonl"),
    json_mode: bool = typer.Option(False, "--json"),
    depth: int = typer.Option(24, "--depth"),
) -> None:
    """失败路径投影 —— 给出失败 event 与因果祖先。"""
    from lca.layer0_infra.observability.coding_agent_tools.failure_explainer import (
        FailureExplainer,
    )

    path = _resolve_journal_path(jsonl, run_id)
    report = FailureExplainer(path).explain_failure(run_id=run_id, depth=depth)
    _emit_report(report, json_mode=json_mode)


@app.command(name="optimize")
def optimize(
    run_id: str = typer.Argument(..., help="Run id"),
    jsonl: Path = typer.Option(None, "--jsonl"),
    json_mode: bool = typer.Option(False, "--json"),
    limit: int = typer.Option(5, "--limit", "-n"),
) -> None:
    """优化候选 —— 按延迟/token/重试排序。"""
    from lca.layer0_infra.observability.coding_agent_tools.optimization_finder import (
        OptimizationFinder,
    )

    path = _resolve_journal_path(jsonl, run_id)
    candidates = OptimizationFinder(path).find_optimization_candidates(run_id=run_id, limit=limit)
    _emit_report(candidates, json_mode=json_mode)


@app.command(name="graph-run")
def graph_run(
    run_id: str = typer.Argument(..., help="Run id"),
    jsonl: Path = typer.Option(None, "--jsonl"),
) -> None:
    """Mermaid 插件交互图(写到 stdout;供 docs / dashboard 嵌入)。"""
    from lca.layer0_infra.observability.coding_agent_tools.plugin_graph_renderer import (
        PluginGraphRenderer,
    )

    path = _resolve_journal_path(jsonl, run_id)
    mermaid = PluginGraphRenderer(path).render(run_id=run_id)
    typer.echo(mermaid)


@app.command(name="minimal-repro")
def minimal_repro(
    run_id: str = typer.Argument(..., help="Run id"),
    jsonl: Path = typer.Option(None, "--jsonl"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """失败因果链 + 必要 evidence refs(供离线复现)。"""
    from lca.layer0_infra.observability.coding_agent_tools.minimal_reproduction import (
        MinimalReproduction,
    )

    path = _resolve_journal_path(jsonl, run_id)
    pkg = MinimalReproduction(path).export(run_id=run_id)
    payload = {
        "schema": "lca.minimal_reproduction/1",
        "run_id": run_id,
        "failure_seq": pkg.failure_seq,
        "failure_event_type": pkg.failure_event_type,
        "causal_chain": list(pkg.causal_chain),
        "evidence_refs": list(pkg.evidence_refs),
        "extra": dict(pkg.extra),
    }
    _emit_report(payload, json_mode=json_mode)


@app.command(name="diff-context")
def diff_context(
    run_id: str = typer.Argument(..., help="Run id"),
    jsonl: Path = typer.Option(None, "--jsonl"),
    json_mode: bool = typer.Option(False, "--json"),
    step: int = typer.Option(0, "--step", help="DiffContext.diff 的 step 参数"),
) -> None:
    """同 run 在 step 处的上下文快照(返回 ContextDiff)。"""
    from lca.layer0_infra.observability.coding_agent_tools.diff_context import (
        DiffContext,
    )

    path = _resolve_journal_path(jsonl, run_id)
    diff = DiffContext(path).diff(run_id=run_id, step=step)
    payload = {
        "run_id": diff.run_id,
        "step_a": diff.step_a,
        "step_b": diff.step_b,
        "items_added": list(diff.items_added),
        "items_removed": list(diff.items_removed),
    }
    _emit_report(payload, json_mode=json_mode)


@app.command(name="diff-runs")
def diff_runs(
    run_id_a: str = typer.Argument(..., help="Run id A"),
    run_id_b: str = typer.Argument(..., help="Run id B"),
    jsonl: Path = typer.Option(None, "--jsonl"),
    json_mode: bool = typer.Option(False, "--json"),
    step: int = typer.Option(0, "--step"),
) -> None:
    """两次 run 同 step 的差异(prompt_hash + delta)。"""
    from lca.layer0_infra.observability.coding_agent_tools.run_diff import (
        RunDiffToolImpl,
    )

    path = _resolve_journal_path(jsonl, run_id_a)
    diff = RunDiffToolImpl(path).diff(run_id_a=run_id_a, run_id_b=run_id_b, step=step)
    payload = {
        "run_id_a": diff.run_id_a,
        "run_id_b": diff.run_id_b,
        "step": diff.step,
        "prompt_hash_a": diff.prompt_hash_a,
        "prompt_hash_b": diff.prompt_hash_b,
        "delta": dict(diff.delta),
    }
    _emit_report(payload, json_mode=json_mode)


@app.command(name="cost")
def cost(
    run_id: str = typer.Argument(..., help="Run id"),
    jsonl: Path = typer.Option(None, "--jsonl"),
    json_mode: bool = typer.Option(False, "--json"),
    pricing_ref: str = typer.Option("", "--pricing-ref", help="按 pricing_ref 过滤"),
) -> None:
    """按 LlmCallCompleted 累加成本(ADR-0065 §六 / PR-6 CostProjector)。"""
    from lca.layer0_infra.observability.cost.projector import CostProjector
    from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

    path = _resolve_journal_path(jsonl, run_id)
    projector = CostProjector()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamped = record_to_stamped(payload)
        if stamped is not None:
            projector.on_event(stamped)
    report = projector.render()
    if pricing_ref:
        report["filtered_pricing_ref"] = pricing_ref
    _emit_report(report, json_mode=json_mode)


@app.command(name="evidence")
def evidence(
    run_id: str = typer.Argument(..., help="Run id"),
    ref: str = typer.Argument(..., help="EvidenceRef digest (sha256:<hex> 或裸 64-hex)"),
    jsonl: Path = typer.Option(None, "--jsonl"),
    json_mode: bool = typer.Option(False, "--json", help="JSON 输出,给 agent"),
) -> None:
    """按 digest 从 run 的 journal.jsonl 查 ``state_ref`` 命中 Tool* 事件,
    从 boot-time EvidenceStore 取回完整 payload(0065 §四 L5)。

    退出码:
    - 0 找到 + 摘要校验通过;stdout 是 JSON-decoded dict(``--json``)
      或 human-rendered dict
    - 1 ref 格式非法 / 摘要校验失败 / 找不到
    - 2 EvidenceStore 未配(boot 时缺 seam)
    """
    from lca.contracts.observability.evidence import (
        Classification,
        EvidenceIntegrityError,
        EvidenceRef,
    )
    from lca.layer0_infra.observability.facade import current_bound

    raw = ref.strip()
    if raw.startswith("sha256:"):
        digest_only = raw[len("sha256:") :]
    elif len(raw) == 64 and all(c in "0123456789abcdef" for c in raw.lower()):
        digest_only = raw.lower()
    else:
        print(f"ERROR: invalid ref format: {ref!r}", file=sys.stderr)
        raise typer.Exit(1)

    path = _resolve_journal_path(jsonl, run_id)
    # 1) 在 journal.jsonl 里查 state_ref.digest 命中的 Tool* 事件
    full_ref: EvidenceRef | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        sr_raw = payload.get("data", {}).get("state_ref")
        if not isinstance(sr_raw, dict):
            continue
        if str(sr_raw.get("digest", "")).lower() != digest_only:
            continue
        try:
            full_ref = EvidenceRef.from_dict(sr_raw)
        except (ValueError, TypeError, KeyError):
            full_ref = None
        break

    if full_ref is None:
        print(
            f"ERROR: no evidence referenced — run {run_id!r} has no Tool* event "
            f"with state_ref.digest={digest_only!r}",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    # 2) EvidenceStore 取回
    bound = current_bound()
    if bound is None or bound.evidence_store is None:
        print("ERROR: evidence_store not configured (no seam)", file=sys.stderr)
        raise typer.Exit(2)

    requester = f"lca-ops:evidence:{run_id}"
    try:
        payload = bound.evidence_store.get(
            full_ref, requester=requester, audience=Classification.INTERNAL
        )
    except EvidenceIntegrityError as exc:
        print(f"ERROR: integrity violation: {exc}", file=sys.stderr)
        raise typer.Exit(1) from exc

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: evidence payload not JSON: {exc}", file=sys.stderr)
        raise typer.Exit(1) from exc

    report = {
        "run_id": run_id,
        "ref": raw,
        "byte_length": len(payload),
        "data": decoded,
    }
    _emit_report(report, json_mode=json_mode)


# ── Entry Point ───────────────────────────────────────────────────────


def _graph_from_yaml(profile_path: Path, data: object) -> dict[str, object]:
    """Derive a minimal capability graph directly from a profile YAML.

    Used as a fallback when ``boot_profile`` rejects the YAML (e.g.
    minimal / synthetic profiles that use ``plugins: []``).
    """
    plugins_list: list[object] = []
    if isinstance(data, dict):
        raw = data.get("plugins") or data.get("entries") or []
        if isinstance(raw, list):
            plugins_list = raw
    return {
        "profile": str(profile_path),
        "plugins": [
            {
                "name": (p.get("name") or p.get("id") or "?") if isinstance(p, dict) else str(p),
                "implements": p.get("provides") if isinstance(p, dict) else [],
                "emitted_events": [],
                "context_fields": [],
                "capabilities": [],
                "side_effects": [],
                "policy_class": "",
            }
            for p in plugins_list
        ],
        "totals": {"plugins": len(plugins_list)},
    }


@app.command()
def inspect_tree(
    profile: Path = typer.Argument(
        Path("profiles/web-standard.yaml"),
        help="Profile YAML path to inspect",
    ),
) -> None:
    """Show the resolved plugin Manifest tree (ADR-0061)."""
    import asyncio

    from lca.harness.diagnostics.inspect import format_plugin_tree, inspect_profile_tree

    if not profile.exists():
        print(f"Profile not found: {profile}")
        raise typer.Exit(1)

    try:
        ctx = asyncio.run(inspect_profile_tree(profile))
    except Exception as exc:
        # Minimal / synthetic profiles may not boot — fall back to YAML sketch.
        import yaml as _yaml

        with profile.open() as fh:
            data = _yaml.safe_load(fh) or {}
        graph = _graph_from_yaml(profile, data)
        print(f"Profile: {profile} (unbooted: {exc})")
        totals = cast("dict[str, object]", graph.get("totals", {}))
        print(f"Plugins: {cast('int', totals.get('plugins', 0))}")
        return

    print(format_plugin_tree(ctx, profile=str(profile)))


@app.command()
def dump_profile(
    profile: Path = typer.Argument(
        Path("profiles/web-standard.yaml"),
        help="Profile YAML path to dump the resolved Manifest for",
    ),
    source: bool = typer.Option(
        False, "--source", help="Annotate each row with its source bundle/patch"
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit canonical redacted JSON"),
) -> None:
    """Dump the resolved, redacted Manifest (ADR-0061). Never prints secrets."""
    import json

    from lca.harness.profile.resolve import dump_resolved, resolve_profile

    if not profile.exists():
        print(f"Profile not found: {profile}")
        raise typer.Exit(1)

    resolved = resolve_profile(profile)
    dumped = dump_resolved(resolved, redact=True)
    if as_json:
        print(json.dumps(dumped, indent=2, sort_keys=True, default=str))
        return
    print(f"profile: {dumped['profile']}")
    print(f"manifest_hash: {dumped['manifest_hash']}")
    print(f"bundles: {dumped['bundles']}")
    print()
    for row in dumped["plugins"]:
        if row["disabled"]:
            continue
        parts = [f"  - id: {row['id']}", f"    module: {row['module']}"]
        parts.append(f"    kind/layer: {row['kind']}/{row['layer']}")
        if row["config"]:
            parts.append(f"    config: {row['config']!r}")
        if source and row.get("source"):
            parts.append(f"    source: {row['source']}")
        print("\n".join(parts))
    print()
    print(f"Total rows: {sum(1 for r in dumped['plugins'] if not r['disabled'])}")


@app.command("why")
def why_cmd(
    capability: str = typer.Argument(..., help="Capability key to explain"),
    profile: Path = typer.Option(
        Path("profiles/web-standard.yaml"), "--profile", "-p", help="Profile YAML"
    ),
) -> None:
    """Explain who owns / requires a capability (ADR-0061)."""
    import asyncio

    from lca.harness.diagnostics.inspect import inspect_profile_tree, why_capability

    ctx = asyncio.run(inspect_profile_tree(profile))
    print(why_capability(ctx, capability))


@app.command("why-plugin")
def why_plugin_cmd(
    plugin_id: str = typer.Argument(..., help="Plugin id to explain"),
    profile: Path = typer.Option(
        Path("profiles/web-standard.yaml"), "--profile", "-p", help="Profile YAML"
    ),
) -> None:
    """Explain why a plugin was started (ADR-0061)."""
    import asyncio

    from lca.harness.diagnostics.inspect import inspect_profile_tree, why_plugin

    ctx = asyncio.run(inspect_profile_tree(profile))
    print(why_plugin(ctx, plugin_id))


@app.command()
def graph(
    profile: Path = typer.Argument(
        Path("profiles/web-standard.yaml"),
        help="Profile YAML path",
    ),
) -> None:
    """Print the plugin DAG edges (provider → consumer)."""
    from lca.harness.profile.resolve import resolve_profile

    resolved = resolve_profile(profile)
    print(f"manifest_hash: {resolved.manifest_hash}")
    print(f"nodes: {sum(1 for p in resolved.plugins if not p.disabled)}")
    print(f"edges: {len(resolved.dag_edges)}")
    for src, dst in resolved.dag_edges:
        print(f"  {src} → {dst}")


@app.command()
def debug(
    sub: str = typer.Argument(..., help="debug sub-subcommand: tree | run | scope | trace"),
    profile: Path = typer.Option(
        Path("profiles/web-standard.yaml"),
        "--profile",
        "-p",
        help="Profile YAML to boot",
    ),
    run_id: str = typer.Option(None, "--run-id", help="Run ID for `debug run` / `debug trace`"),
    diagnostic: Path = typer.Option(None, "--diagnostic", help="Explicit diagnostic JSONL path"),
    category: str = typer.Option("", "--category", help="Filter `debug trace` by category"),
    plugin: str = typer.Option("", "--plugin", help="Filter `debug trace` by plugin"),
) -> None:
    """Debug subcommand: tree, run, scope.

    - `debug tree`: render the booted plugin tree (services + event listeners)
    - `debug run <id>`: print session events for a run (stub — full impl in
      follow-up; reads journal from traces/runs/<id>.journal)
    - `debug scope <id>`: print service resolution for a scope (stub —
      full impl queries session_store for the session's scope snapshot)
    - `debug trace --run-id <id>`: render the run-scoped diagnostic JSONL
    """
    import asyncio

    if sub == "tree":
        from lca.harness.diagnostics.tree import render_tree
        from lca.harness.profile.boot import boot_profile

        async def main() -> None:
            ctx = await boot_profile(str(profile))
            print(render_tree(ctx))

        asyncio.run(main())
    elif sub == "run":
        if run_id is None:
            print("debug run requires --run-id")
            raise typer.Exit(1)
        from pathlib import Path as _Path

        journal_path = _Path("traces/runs") / f"{run_id}.journal"
        if not journal_path.exists():
            print(f"No journal for {run_id} (expected {journal_path})")
            raise typer.Exit(1)
        # Read the journal (JSONL) and print events
        for line in journal_path.read_text().splitlines():
            print(line)
    elif sub == "trace":
        if diagnostic is None:
            if run_id is None:
                print("debug trace requires --run-id or --diagnostic")
                raise typer.Exit(1)
            diagnostic = Path("traces/runs") / f"{run_id}.diagnostic.jsonl"
        if not diagnostic.exists():
            print(f"No diagnostic trace found (expected {diagnostic})")
            raise typer.Exit(1)
        for line in diagnostic.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if category and item.get("category") != category:
                continue
            if plugin and item.get("plugin") != plugin:
                continue
            _render_diagnostic_trace_line(item)
    elif sub == "scope":
        if run_id is None:
            print("debug scope requires --run-id")
            raise typer.Exit(1)
        # Stub: print run_id + a hint
        print(f"Run: {run_id}")
        print("Service resolution: deferred to follow-up (requires session_store.index)")
    else:
        print(f"Unknown debug sub: {sub!r} (expected: tree, run, scope)")
        raise typer.Exit(1)


def _render_diagnostic_trace_line(item: dict[str, Any]) -> None:
    """Render one diagnostic JSONL record as a compact human-readable timeline row."""
    timestamp = str(item.get("ts", ""))
    category = str(item.get("category", "infra"))
    status = str(item.get("status", "info")).upper()
    plugin = str(item.get("plugin", "-"))
    operation = str(item.get("operation", "-"))
    duration = item.get("duration_ms")
    suffix = f" {duration}ms" if duration is not None else ""
    print(f"{timestamp} [{status:<9}] {category:<10} {plugin:<28} {operation}{suffix}")
    attributes = item.get("attributes") or {}
    output = item.get("output") or {}
    if attributes:
        print(f"  input: {json.dumps(attributes, ensure_ascii=False, sort_keys=True)}")
    if output:
        print(f"  output: {json.dumps(output, ensure_ascii=False, sort_keys=True)}")
    if item.get("error_type"):
        print(f"  error: {item['error_type']}: {item.get('error_message', '')}")


# ── Diagnostics (Phase J / spec §24.5) ──────────────────────────────


@app.command()
def diagnose(
    problem: str = typer.Argument(
        ...,
        help=(
            "Diagnostic pattern to run: model-not-seen | loop-stuck | "
            "memory-poisoned | approval-rejected"
        ),
    ),
    trace_id: str = typer.Option(None, "--trace-id", help="Limit the scan to a specific trace id"),
    expected_kind: str = typer.Option(
        "",
        "--expected-kind",
        help="For model-not-seen: the manifest kind the model should have seen",
    ),
    window: int = typer.Option(
        10, "--window", help="For loop-stuck: the recent-tool window to inspect"
    ),
    journal: Path = typer.Option(
        None,
        "--journal",
        help=(
            "Path to a journal jsonl file (defaults to "
            "traces/runs/<trace_id>.journal or traces/lca_journal.jsonl)"
        ),
    ),
) -> None:
    """Run a v3 diagnostic pattern against a journal.

    Mirrors spec §24.5 — each pattern is a single root-cause walk; the
    output is a list of ``Finding`` rows (severity / summary / refs).
    """
    from lca.layer0_infra.observability.diagnostics import (
        DiagnosePattern,
        diagnose,
    )
    from lca.layer0_infra.observability.journal.engine import RunStore
    from lca.layer0_infra.observability.journal.journal_io import read_journal

    pattern_key = problem.strip().lower()
    aliases: dict[str, str] = {
        "model-not-seen": DiagnosePattern.MODEL_NOT_SEEN.value,
        "loop-stuck": DiagnosePattern.LOOP_STUCK.value,
        "memory-poisoned": DiagnosePattern.MEMORY_POISONED.value,
        "approval-rejected": DiagnosePattern.APPROVAL_REJECTED.value,
    }
    if pattern_key not in aliases:
        print(f"Unknown pattern {problem!r}; expected one of {sorted(aliases)}")
        raise typer.Exit(1)
    canonical = aliases[pattern_key]

    journal_path = _resolve_diagnose_journal_path(journal, trace_id)
    if journal_path is None or not journal_path.exists():
        print(
            "No journal file found. Pass --journal <path> or set --trace-id "
            "(looks under traces/runs/)."
        )
        raise typer.Exit(1)

    store = RunStore()
    for stamped in read_journal(journal_path):
        store.append(stamped.event)

    pattern = DiagnosePattern(canonical)
    report = diagnose(
        store,
        pattern=pattern,
        trace_id=trace_id or None,
        expected_kind=expected_kind,
        window=window,
    )
    if report.ok:
        print(f"OK ({pattern.value}): no findings.")
        raise typer.Exit(0)
    print(f"Pattern: {pattern.value}")
    print(f"Journal: {journal_path}")
    if trace_id:
        print(f"Trace: {trace_id}")
    print()
    for finding in report.findings:
        print(f"  [{finding.severity.upper()}] {finding.summary}")
        if finding.evidence_refs:
            print(f"    refs: seq={','.join(str(s) for s in finding.evidence_refs)}")
        if finding.detail:
            print(f"    detail: {finding.detail}")
    raise typer.Exit(2 if any(f.severity == "high" for f in report.findings) else 1)


@app.command(name="diagnose-model-not-seen")
def diagnose_model_not_seen_alias(
    trace_id: str = typer.Option(None, "--trace-id"),
    expected_kind: str = typer.Option(
        "", "--expected-kind", help="Manifest kind the model should have seen"
    ),
    journal: Path = typer.Option(None, "--journal"),
) -> None:
    """Alias for ``diagnose model-not-seen``."""
    diagnose(
        problem="model-not-seen",
        trace_id=trace_id,
        expected_kind=expected_kind,
        journal=journal,
    )


@app.command(name="diagnose-loop-stuck")
def diagnose_loop_stuck_alias(
    trace_id: str = typer.Option(None, "--trace-id"),
    window: int = typer.Option(10, "--window"),
    journal: Path = typer.Option(None, "--journal"),
) -> None:
    """Alias for ``diagnose loop-stuck``."""
    diagnose(
        problem="loop-stuck",
        trace_id=trace_id,
        window=window,
        journal=journal,
    )


@app.command(name="diagnose-memory-poisoned")
def diagnose_memory_poisoned_alias(
    journal: Path = typer.Option(None, "--journal"),
) -> None:
    """Alias for ``diagnose memory-poisoned``."""
    diagnose(problem="memory-poisoned", journal=journal)


@app.command(name="diagnose-approval-rejected")
def diagnose_approval_rejected_alias(
    journal: Path = typer.Option(None, "--journal"),
) -> None:
    """Alias for ``diagnose approval-rejected``."""
    diagnose(problem="approval-rejected", journal=journal)


def _resolve_diagnose_journal_path(
    explicit: Path | None,
    trace_id: str | None,
) -> Path | None:
    """Pick the journal jsonl file to scan.

    Resolution order:
    1. Explicit ``--journal`` argument (always wins).
    2. ``traces/runs/<trace_id>.journal`` when ``--trace-id`` is set.
    3. ``traces/lca_journal.jsonl`` (the durable global fact stream).
    """
    if explicit is not None:
        return explicit
    if trace_id:
        candidate = Path("traces/runs") / f"{trace_id}.journal"
        if candidate.exists():
            return candidate
    fallback = Path("traces/lca_journal.jsonl")
    if fallback.exists():
        return fallback
    return None


# ── Audit 测量网 (ADR-0074 PR-0) ───────────────────────────────────


def _resolve_repo_root() -> Path:
    """Return the LCA repository root (where lca-ops was invoked from)."""
    return Path.cwd()


def _audit_roots(*names: str) -> list[Path]:
    """Build the default scan roots under the repo, ignoring missing dirs."""
    root = _resolve_repo_root()
    return [root / name for name in names]


@app.command(name="audit-control-surface")
def audit_control_surface_cmd(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
) -> None:
    """Scan plugins / bundles / profiles for Control Slot references and missing
    ``control:`` field declarations (ADR-0074 PR-0 / V1 baseline).

    Exit ``0`` when no findings; ``1`` when findings exist (CI hook).
    """
    from lca.harness.diagnostics.audit_control_surface import (
        format_report,
        scan_control_surface,
    )

    roots = _audit_roots("lca/plugins", "bundles", "profiles")
    findings = scan_control_surface(roots)
    report = format_report(findings, json_mode=json_mode)
    sys.stdout.write(report)
    total = sum(len(v) for v in findings.values())
    raise typer.Exit(0 if total == 0 else 1)


@app.command(name="audit-state-writers")
def audit_state_writers_cmd(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
) -> None:
    """Scan ``lca/layer{1,2,3}_*`` for direct ``state.<attr> = ...`` writes
    outside the reducer (ADR-0074 PR-0 / C4 / V3 baseline).

    Exit ``0`` when no findings; ``1`` when findings exist.
    """
    from lca.harness.diagnostics.audit_state_writers import (
        format_report,
        scan_state_writers,
    )

    roots = _audit_roots(
        "lca/layer1_cognitive",
        "lca/layer2_runtime",
        "lca/layer3_agent",
    )
    findings = scan_state_writers(roots)
    report = format_report(findings, json_mode=json_mode)
    sys.stdout.write(report)
    raise typer.Exit(0 if not findings else 1)


@app.command(name="audit-direct-commands")
def audit_direct_commands_cmd(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
) -> None:
    """Scan Body code for direct ``sandbox.*`` / ``transport.*`` calls
    bypassing ``SafeExecutor`` / seams (ADR-0074 PR-0 / V4 baseline).

    Exit ``0`` when no findings; ``1`` when findings exist.
    """
    from lca.harness.diagnostics.audit_direct_commands import (
        format_report,
        scan_direct_commands,
    )

    roots = _audit_roots("lca/layer1_cognitive/body", "lca/plugins/body")
    findings = scan_direct_commands(roots)
    report = format_report(findings, json_mode=json_mode)
    sys.stdout.write(report)
    raise typer.Exit(0 if not findings else 1)


@app.command(name="audit-hook-attach")
def audit_hook_attach_cmd(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
) -> None:
    """Scan ``lca/layer{1,2,3,4}_*`` for residual hook-mounting patterns
    (``hooks.trigger`` / ``middleware_bag.<attr>`` / ``_emit`` calls /
    ``register_hook|attach_hook|subscribe``) that PR-7 retires
    (ADR-0074 PR-0 / V5 baseline).

    Exit ``0`` when no findings; ``1`` when findings exist.
    """
    from lca.harness.diagnostics.audit_hook_attach import (
        format_report,
        scan_hook_attach,
    )

    roots = _audit_roots(
        "lca/layer1_cognitive",
        "lca/layer2_runtime",
        "lca/layer3_agent",
        "lca/layer4_app",
    )
    findings = scan_hook_attach(roots)
    report = format_report(findings, json_mode=json_mode)
    sys.stdout.write(report)
    raise typer.Exit(0 if not findings else 1)


@app.command(name="status-adr-supervision")
def status_adr_supervision_cmd(
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
) -> None:
    """Print the ADR-0074 supervision status — implements ADR-0066 / 0067 /
    0068 / 0069 / 0074 supervision by delegating to scripts/check_adr_supervision
    + scripts/route_legacy_patterns.

    Exit ``0`` if tracker is consistent; ``1`` if inconsistencies are found.
    """
    import json as _json
    import subprocess as _sp

    repo_root = _resolve_repo_root()
    check_proc = _sp.run(
        [sys.executable, "scripts/check_adr_supervision.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    check_rc = check_proc.returncode

    if json_mode:
        sys.stdout.write(
            _json.dumps(
                {
                    "check_rc": check_rc,
                    "check_stderr": check_proc.stderr.strip(),
                    "tracker": str(
                        repo_root / "docs" / "plans" / "adr-0074-plugin-everything-tracker.md"
                    ),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
    else:
        if check_rc == 0:
            print("ADR supervision tracker: consistent ✅")
        elif check_rc == 2:
            print("ADR supervision tracker: file missing")
        else:
            print("ADR supervision tracker: inconsistencies; details:")
            for line in check_proc.stderr.splitlines():
                print(f"  {line}")

        print()
        print("Historical migration baseline (PR-0 → ownership):")
        route_proc = _sp.run(
            [sys.executable, "scripts/route_legacy_patterns.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if route_proc.returncode == 0:
            sys.stdout.write(route_proc.stdout)
        else:
            print(f"  (route_legacy_patterns failed: rc={route_proc.returncode})")

    raise typer.Exit(0 if check_rc == 0 else 1)


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
    path: str = typer.Option(
        "", "--path", "-p", help="plugin source path (for author face)"
    ),
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

    Examples:
        lca-ops creator --face inspect
        lca-ops creator --face author --name plugin.x --path /tmp/x.py
        lca-ops creator --face validate --name plugin.x
        lca-ops creator --face promote --name plugin.x
        lca-ops creator --face promote --name plugin.x --rollback
    """
    import json as _json

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
            _json.dumps(
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
    subcommand: str = typer.Option(
        "list-templates",
        "--sub",
        "-s",
        help="Plan subcommand: list-templates / relations",
    ),
    template_id: str = typer.Option(
        "", "--template", "-t", help="template id (for relations subcommand)"
    ),
    plugin_id: str = typer.Option(
        "", "--plugin", "-p", help="plugin id (for relations subcommand)"
    ),
    json_mode: bool = typer.Option(False, "--json", help="JSON，给 agent"),
) -> None:
    """Plan management (PR-12 + V12 acceptance §4.6).

    Subcommands:

    - ``list-templates`` —— 输出 12 个标准 PlanTemplate (V12 acceptance)
    - ``relations --plugin <id>`` —— 输出某 plugin 的关系图谱 (V11 acceptance)

    Examples:
        lca-ops plan --sub list-templates
        lca-ops plan --sub list-templates --json
        lca-ops plan --sub relations --plugin plugin.a
    """
    import json as _json

    if subcommand == "list-templates":
        from lca.contracts.atoms.plan_template import (
            all_plan_template_ids,
            plan_template_to_dict,
            standard_plan_templates,
        )

        templates = standard_plan_templates()
        if json_mode:
            sys.stdout.write(
                _json.dumps(
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

    if subcommand == "relations":
        if not plugin_id:
            print("plan relations: --plugin <id> required", file=sys.stderr)
            raise typer.Exit(2)
        from lca.contracts.protocols.capability_plan import (
            relations_from_plugin,
            relations_to_plugin,
        )
        from lca.harness.profile.plan_compiler import compile_plan

        # resolve profile + compile plan; print relations
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
                _json.dumps(
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

    print(f"plan: unknown subcommand {subcommand!r}", file=sys.stderr)
    raise typer.Exit(2)


def main() -> None:
    """Entry point for scripts/lca-ops."""
    app()


if __name__ == "__main__":
    main()
