"""Session 面 CLI —— Wave 5 查询 + transcript（只读,走 spine JSONL）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from lca.plugins.session.runtime.log_reader import SessionLogReadError, load_session_events
from lca.plugins.session.runtime.messages import export_transcript
from lca.plugins.session.runtime.query import filter_session_events, fold_tool_invocations

_DEFAULT_TRACES_ROOT = Path("traces")


def _spine_path(run_id: str, traces_root: Path) -> Path:
    return traces_root / "runs" / run_id / f"{run_id}.spine.jsonl"


def _load_run_events(run_id: str, traces_root: Path):
    path = _spine_path(run_id, traces_root)
    if not path.exists():
        typer.echo(f"spine ledger not found: {path}", err=True)
        raise typer.Exit(1)
    try:
        return load_session_events(path, session_id=run_id)
    except SessionLogReadError as exc:
        typer.echo(f"session log read failed: {exc}", err=True)
        raise typer.Exit(1) from exc


def register(app: typer.Typer) -> None:
    session_app = typer.Typer(help="Session event query / transcript (read-only)")
    app.add_typer(session_app, name="session")

    @session_app.command(name="events")
    def events_cmd(
        run_id: str = typer.Argument(..., help="run_id"),
        event_type: str = typer.Option("", "--type", "-t", help="filter by event type"),
        turn: int | None = typer.Option(None, "--turn", help="filter by turn"),
        step: int | None = typer.Option(None, "--step", help="filter by step"),
        json_output: bool = typer.Option(False, "--json", help="JSON lines output"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT,
            "--traces-root",
            help="traces root directory",
        ),
    ) -> None:
        """按 type/turn/step 过滤 session 事件（fail-closed 读 spine JSONL）。"""
        loaded = _load_run_events(run_id, traces_root)
        filtered = filter_session_events(
            loaded,
            event_type=event_type or None,
            turn=turn,
            step=step,
        )
        if json_output:
            for event in filtered:
                sys.stdout.write(
                    json.dumps(
                        {
                            "type": event.type,
                            "seq": event.seq,
                            "time": event.time,
                            "data": event.data,
                            "ignorable": event.ignorable,
                            "surface_op": event.surface_op,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            return
        typer.echo(f"run_id={run_id} events={len(filtered)}/{len(loaded)}")
        for event in filtered:
            typer.echo(f"seq={event.seq} type={event.type} time={event.time}")

    @session_app.command(name="tools")
    def tools_cmd(
        run_id: str = typer.Argument(..., help="run_id"),
        json_output: bool = typer.Option(False, "--json", help="JSON output"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT,
            "--traces-root",
            help="traces root directory",
        ),
    ) -> None:
        """tool call↔result 对齐视图（按 invocation_id）。"""
        loaded = _load_run_events(run_id, traces_root)
        views = fold_tool_invocations(loaded)
        if json_output:
            payload = [
                {
                    "invocation_id": view.invocation_id,
                    "tool_name": view.tool_name,
                    "turn": view.turn,
                    "step": view.step,
                    "started_seq": view.started_seq,
                    "ended_seq": view.ended_seq,
                    "outcome": view.outcome,
                    "ok": view.ok,
                    "duration_ms": view.duration_ms,
                }
                for view in views
            ]
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            return
        typer.echo(f"run_id={run_id} tool_invocations={len(views)}")
        for view in views:
            status = "ok" if view.ok else ("fail" if view.ok is False else "open")
            typer.echo(
                f"  {view.invocation_id} tool={view.tool_name or '?'} "
                f"turn={view.turn} step={view.step} status={status} "
                f"duration_ms={view.duration_ms}"
            )

    @session_app.command(name="transcript")
    def transcript_cmd(
        run_id: str = typer.Argument(..., help="run_id"),
        json_output: bool = typer.Option(False, "--json", help="JSON output"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT,
            "--traces-root",
            help="traces root directory",
        ),
    ) -> None:
        """导出 surface append-origin transcript（人眼/对外）。"""
        loaded = _load_run_events(run_id, traces_root)
        transcript = export_transcript(loaded)
        if json_output:
            sys.stdout.write(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n")
            return
        typer.echo(f"run_id={run_id} transcript_messages={len(transcript)}")
        for index, message in enumerate(transcript, start=1):
            role = message.get("role", "?")
            content = message.get("content", "")
            preview = str(content)[:120]
            typer.echo(f"  [{index}] {role}: {preview}")
