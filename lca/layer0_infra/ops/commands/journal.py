"""Journal log following: the ``logs`` command + SSE streaming + JSONL replay."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from lca.layer0_infra.ops.config import OpsConfig


def register(app: typer.Typer) -> None:
    """Register the logs command on the typer app."""

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

                backoff = 1.0
                buf = ""
                for chunk in resp.iter_text():
                    buf += chunk
                    last_frame_ts = _time.monotonic()
                    while "\n\n" in buf:
                        block, buf = buf.split("\n\n", 1)
                        record = parse_sse_block(block)
                        if record is None:
                            continue
                        seq = extract_seq_from_record(record)
                        if seq > last_seq:
                            last_seq = seq
                        stamped = sse_record_to_stamped(record)
                        if stamped is not None:
                            projector.on_event(stamped)

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

        _time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)
