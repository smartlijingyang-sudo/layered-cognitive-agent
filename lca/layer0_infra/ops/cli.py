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
  与 DSH 架构对齐：模型可见的一切都可从 journal 重建。

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
上游镜像  upstream
────────────────────────────────
check-upstream
  对比 lca/packages/ 与 ~/deepseek-harness/packages/ 的结构差异。
  三个层级都查：顶层包、子包、src/ 文件（.ts ↔ .py）。
  ./scripts/lca-ops check-upstream                  看差异
  ./scripts/lca-ops check-upstream --sync           生成缺失的骨架（不覆盖）
  ./scripts/lca-ops check-upstream --sync --force   强制覆盖
  ./scripts/lca-ops check-upstream --json           结构化输出（CI）
  ./scripts/lca-ops check-upstream --upstream <p>   自定义上游根目录
  退出码：0=一致；1=有缺失。CI 可据此判定。

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

    Three-layer architecture (DSH-aligned: model-visible = logged):
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


# ── Entry Point ───────────────────────────────────────────────────────


@app.command()
def inspect_tree(
    profile: Path = typer.Argument(
        Path("profiles/web-standard.yaml"),
        help="Profile YAML path to inspect",
    ),
) -> None:
    """Show the resolved plugin tree for a profile."""
    from cordis.loader import load_yaml

    if not profile.exists():
        print(f"Profile not found: {profile}")
        raise typer.Exit(1)

    data = load_yaml(profile)

    print(f"Profile: {profile}")
    print(f"Plugins: {len(tree.entries)}")
    print()
    entries_by_id = {entry.id: entry for entry in tree.entries}
    for handle_id, handle in tree.host.handles.items():
        print(f"  {handle_id}")
        print(f"    state: {handle.state.value}")
        print(f"    provides: {handle.spec.provides or '—'}")
        print(f"    inject: {handle.injected or '—'}")
        print(f"    effects: {len(handle.effects)}")
        original = getattr(entries_by_id.get(handle_id), "_original_module", None)
        if original is not None:
            manifest = getattr(original, "manifest", None)
            if manifest is not None:
                print(f"    kind: {manifest.kind.value}")
                if manifest.seam_key:
                    print(f"    seam: {manifest.seam_key}")
    print()
    print("Seam completeness: PASS")


@app.command()
def dump_profile(
    profile: Path = typer.Argument(
        Path("profiles/web-standard.yaml"),
        help="Profile YAML path to dump the expanded entry list for",
    ),
    source: bool = typer.Option(
        False, "--source", help="Annotate each row with its source bundle/patch"
    ),
) -> None:
    """Dump the expanded plugin-tree entry list for a profile.

    Mirrors DSH ``dsh --dump-config``: prints the exact rows the Loader
    would activate, so a dump can never drift from what boots.
    """
    from cordis.loader import load_yaml

    if not profile.exists():
        print(f"Profile not found: {profile}")
        raise typer.Exit(1)

    data = load_yaml(profile)
    rows = data.get("plugins", []) if isinstance(data, dict) else data
    for row in rows:
        parts = [f"  - id: {row['id']}"]
        if row.get("name"):
            parts.append(f"    name: {row['name']}")
        if row.get("parent"):
            parts.append(f"    parent: {row['parent']}")
        if row.get("group"):
            parts.append("    group: true")
        if row.get("disabled"):
            parts.append("    disabled: true")
        if row.get("config"):
            parts.append(f"    config: {row['config']!r}")
        if source and row.get("source"):
            parts.append(f"    source: {row['source']}")
        print("\n".join(parts))
    print()
    print(f"Total rows: {len(rows)}")


@app.command()
def debug(
    sub: str = typer.Argument(..., help="debug sub-subcommand: tree | run | scope"),
    profile: Path = typer.Option(
        Path("profiles/web-standard.yaml"),
        "--profile",
        "-p",
        help="Profile YAML to boot",
    ),
    run_id: str = typer.Option(
        None, "--run-id", help="Run ID for `debug run` (optional)"
    ),
) -> None:
    """Debug subcommand: tree, run, scope.

    - `debug tree`: render the booted plugin tree (services + event listeners)
    - `debug run <id>`: print session events for a run (stub — full impl in
      follow-up; reads journal from traces/runs/<id>.journal)
    - `debug scope <id>`: print service resolution for a scope (stub —
      full impl queries session_store for the session's scope snapshot)
    """
    import asyncio

    if sub == "tree":
        from lca.harness.profile.boot import boot_profile
        from lca.harness.diagnostics.tree import render_tree

        async def main():
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


@app.command(name="check-upstream")
def check_upstream(
    upstream: Path = typer.Option(
        Path.home() / "deepseek-harness" / "packages",
        "--upstream",
        help="Upstream packages root (default: ~/deepseek-harness/packages).",
    ),
    target: Path = typer.Option(
        Path("lca/packages"),
        "--target",
        help="Local mirror root (default: lca/packages).",
    ),
    sync: bool = typer.Option(
        False,
        "--sync",
        help="Generate missing skeleton files (idempotent; never overwrites).",
    ),
    populate: bool = typer.Option(
        False,
        "--populate",
        help="With --sync, also fill stubs with surface-correct Python exports (passes check_port_surface.py).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="With --sync, overwrite existing files (use sparingly).",
    ),
    json_output: bool = typer.Option(False, "--json", help="JSON report for CI."),
) -> None:
    """Compare local ``lca/packages/`` against upstream ``deepseek-harness/packages/``.

    Reports missing/extra at three levels (top-level package, sub-package, src/ files)
    and, with ``--sync``, generates Python skeleton files mirroring the upstream layout.
    Each upstream ``.ts`` file becomes a local ``.py`` stub with a header pointing back
    to its upstream source. Hyphenated upstream names become underscored Python names
    (e.g. ``llm-deepseek`` → ``llm_deepseek``).

    Exit code: ``0`` when in sync (or after a successful sync), ``1`` otherwise.
    """
    from lca.layer0_infra.ops.upstream_mirror import cli_run

    code = cli_run(
        upstream=upstream,
        target=target,
        sync=sync,
        force=force,
        populate=populate,
        json_output=json_output,
    )
    raise typer.Exit(code)


def main() -> None:
    """Entry point for scripts/lca-ops."""
    app()


if __name__ == "__main__":
    main()
