"""Journal trace — print one event per line, optionally with I17 source columns.

Task 9.3: ``./scripts/lca-ops journal trace [run_id] [--locals] [--source]``
reads the append-only ``<run_id>.spine.jsonl`` written by the spine ``FileSink``
and prints a human-readable table. ``run_id`` is optional: when omitted
the command picks the run under ``traces/runs`` with the newest directory
mtime. The default view shows ``seq /
execution point / channel / outcome / when``. With ``--source`` two extra
columns appear (``source_location`` file:line and the function name).
With ``--locals`` (which implies ``--source``) two more columns are
added: the first ``call_frames`` entry beyond ``source_location`` and a
compact ``locals_snapshot.pre_call`` rendering.

The CLI sits under ``journal`` to keep the LCA Spine concerns grouped;
the older ``lca-ops trace`` command remains for legacy ``journal.jsonl``
replay (via ``TraceInspectorToolAdapter``). Both surfaces are read-only.

I17 contract
------------
Every ``*.start`` event MUST carry ``source_location`` /
``call_frames`` / ``locals_snapshot``. The CLI does NOT enforce this;
that lives in ``EmitPipeline.emit``. A misconfigured pipeline produces
``"-"`` in the source columns and the operator sees the gap instead of
a stack trace.

Not in scope
------------
- The CLI does NOT fall back to ``journal.jsonl``. Spine events and the
  legacy ``journal.jsonl`` are two separate streams; mixing them would
  hide I17 violations. If the spine ledger is missing the CLI emits a
  short error and ``typer.Exit(1)``.
- The CLI does NOT resolve offloaded sidecars (>4 KB rows live in
  ``<event_hash>.json``). Out-of-scope here; future PR can wire a
  sidecar reader.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.cli.commands.journal import spine_event_seq
from lca.infrastructure.cli.commands.journal_extra.journal_trace.parse import (
    TraceRow,
    _event_to_row,
    _iter_events,
)
from lca.infrastructure.cli.commands.journal_extra.journal_trace.render import (
    _render_human,
    _row_iter_to_table,
)
from lca.infrastructure.cli.commands.kernel._shared import find_latest_run_id
from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)

_DEFAULT_TRACES_ROOT = Path("traces")  # CLI default traces root
_DEFAULT_MAX_DETAIL_PER_NODE = 8


def _resolve_events_path(traces_root: Path, run_id: str) -> Path:
    """Resolve spine ledger under ``<run_dir>`` or surface a friendly error (PR-27 / PR-4)。

    ADR-0169 PR-27 L10 + PR-4:唯一 ``<run_id>.spine.jsonl``;不存在时给
    出友好错误,不再回退到旧文件名。
    """
    locator = FilesystemRunLocator(traces_root)
    run_dir = locator.run_dir(run_id)
    if not run_dir.exists():
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        print("  hint: 检查 --traces-root 是否正确,run_id 是否存在", file=sys.stderr)
        raise SystemExit(1)
    spine_path = locator.events_path(run_id)
    if spine_path.exists():
        return spine_path
    print(
        f"spine ledger not found: {spine_path}\n"
        f"  hint: spine FileSink 尚未写入,或 run {run_id} 不存在",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _latest_run_id(traces_root: Path) -> str | None:
    """Resolve the latest ``run_id`` under ``traces_root`` for argument-less trace.

    Delegates to :func:`lca.infrastructure.cli.commands._shared.find_latest_run_id`
    so the resolution rule (newest ``traces/runs/<run_id>`` mtime) stays
    consistent across CLI commands.
    """
    return find_latest_run_id(traces_root)


def register(app: typer.Typer) -> None:
    """Register the ``trace`` command under the ``journal`` group."""

    @app.command(name="trace")
    def trace_cmd(
        run_id: str = typer.Argument(
            "",
            help="run_id (e.g. run_c38532761cfb);空 = traces/runs 下 mtime 最新的 run",
        ),
        human: bool = typer.Option(
            True,
            "--human/--no-human",
            help="人读视图(默认开):tree 缩进 + payload 原文 + Δms",
        ),
        with_locals: bool = typer.Option(
            False, "--locals", help="在表格里追加 next_frame + locals_snapshot 列"
        ),
        with_source: bool = typer.Option(
            False, "--source", help="在表格里追加 source_location 列(默认开)"
        ),
        json_output: bool = typer.Option(False, "--json", help="JSON 输出,给 agent"),
        traces_root: Path = typer.Option(
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
        limit: int = typer.Option(0, "--limit", "-n", help="只输出前 N 行(0 = 全部)"),
        max_detail_per_node: int = typer.Option(
            _DEFAULT_MAX_DETAIL_PER_NODE,
            "--max-detail-per-node",
            help="人读视图下每个节点最多展开的 payload 行数(超出显示 +N more)",
        ),
    ) -> None:
        """检查一个 run 的 spine ledger(只读,PR-9 I17 起生效)。

        不带参数时自动选 ``traces/runs`` 下 mtime 最新的一个 run。
        其余语义同显式传参:

        默认开 ``--human``:tree 缩进 + payload 原文 + Δms 时间戳 +
        自动折叠 ``llm.stream.token`` / ``runtime.reducer.apply`` /
        配对的 ``transport.route.{enter,exit}``,但**不截断 payload 文本**。

        加 ``--no-human`` 回到原表格:``seq / execution_point /
        channel / outcome / when / source``(对 CI / agent 友好)。
        """
        # ``--locals`` implies ``--source`` so the table is consistent:
        # locals without source_location is ambiguous. Only meaningful in
        # the ``--no-human`` path; ignored in ``--human``.
        if with_locals:
            with_source = True

        resolved_run_id = run_id or _latest_run_id(traces_root)
        if not resolved_run_id:
            print(
                "no run_id provided and no runs found under "
                f"{traces_root / 'runs'}; pass a run_id explicitly",
                file=sys.stderr,
            )
            raise SystemExit(1)
        events_path = _resolve_events_path(traces_root, resolved_run_id)
        all_events: list[dict[str, Any]] = []
        for event in _iter_events(events_path):
            if event.get("__decode_error__"):
                continue
            all_events.append(event)

        if limit > 0:
            all_events = all_events[:limit]

        if human and not json_output:
            sys.stdout.write(
                _render_human(
                    all_events,
                    max_detail_per_node=max_detail_per_node,
                )
            )
            return

        rows: list[TraceRow] = []
        skipped = 0
        total = 0
        for event in all_events:
            total += 1
            payload = event.get("payload")
            if not isinstance(payload, dict):
                skipped += 1
                continue
            seq = spine_event_seq(event)
            rows.append(_event_to_row(seq, event))

        if json_output:
            payload_rows = [
                {
                    "seq": r.seq,
                    "execution_point": r.execution_point,
                    "channel": r.channel,
                    "outcome": r.outcome,
                    "when": r.when,
                    "source_location": (
                        {
                            "file": r.source_file,
                            "line": r.source_line,
                            "function": r.source_function,
                        }
                        if r.source_file
                        else None
                    ),
                    "next_frame": r.next_frame or None,
                    "locals_snapshot": r.locals_render or None,
                }
                for r in rows
            ]
            report = {
                "schema": "lca.journal_trace/1",
                "run_id": resolved_run_id,
                "events_path": str(events_path),
                "total": total,
                "rendered": len(rows),
                "skipped": skipped,
                "with_locals": with_locals,
                "with_source": with_source,
                "rows": payload_rows,
            }
            sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            sys.stdout.write("\n")
            return

        table = _row_iter_to_table(rows, with_locals=with_locals)
        sys.stdout.write(table)
        sys.stdout.write("\n")
        sys.stdout.write(
            f"\n── trace done: {len(rows)}/{total} events rendered, "
            f"{skipped} skipped (spine_ledger={events_path}) ──\n"
        )


__all__ = ["register"]
