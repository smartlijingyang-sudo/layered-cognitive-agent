"""Journal exceptions — 列出 run 的所有 traceback,带可读 sidecar 名。

承接 K6 fail-loud SSOT (ADR-2026-09-03):每个 ``exception.caught`` EP
都额外写到 ``<run_id>.exceptions.jsonl``(TracingFileSink 双写)。本命令
直接读这个文件,人话打印每条 traceback 的关键字段:

- exception_class / exception_message
- boundary(K6 fail_loud.<Class> | lifecycle.execute | ...)
- source_location(file:line:function)
- traceback_text(完整堆栈,UTF-8 4 KiB cap)
- 关联的 sidecar 文件名(``<sha8>-<SafeClass>.json``)

用法::

    ./scripts/lca-ops journal exceptions                       # 最新 run
    ./scripts/lca-ops journal exceptions run_c38532761cfb      # 指定 run
    ./scripts/lca-ops journal exceptions --json                # JSON 给 agent
    ./scripts/lca-ops journal exceptions --raw                 # 完整 payload
    ./scripts/lca-ops journal exceptions --grep AttributeError # 按 class 过滤

设计上只读 ``<run_id>.exceptions.jsonl`` sidecar 文件(唯一 source of truth)。
Per spec §15 G-11 / Task 1.10:spine-scan fallback 已删除;sidecar 缺失时直接
报 count=0。避免 spine 扫描产生误导性的"有异常但 CLI 报有异常"结果(当实际
sidecar 缺失时)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

_DEFAULT_TRACES_ROOT = Path("traces")


def _find_run_dir(run_id: str | None, traces_root: Path) -> Path:
    resolved_run_id = run_id
    if not resolved_run_id:
        from lca.infrastructure.cli.commands.kernel._shared import find_latest_run_id

        resolved_run_id = find_latest_run_id(traces_root)
    if not resolved_run_id:
        raise typer.BadParameter("no run_id and no latest run found under traces/runs")
    return traces_root / "runs" / resolved_run_id


def _iter_records(path: Path) -> list[dict[str, Any]]:
    """Read the sidecar exceptions ledger, skipping undecodable lines."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # 主 ledger 的 fallback 也可能写到这里;跳过不致命
            continue
    return out


def _format_record(rec: dict[str, Any], *, raw: bool) -> str:
    if raw:
        return json.dumps(rec, default=str, ensure_ascii=False)
    payload = rec.get("payload") or {}
    cls = payload.get("exception_class") or "?"
    msg = payload.get("exception_message") or ""
    boundary = payload.get("boundary") or "?"
    err_kind = payload.get("err_kind") or "unknown"
    src = payload.get("source_location") or {}
    src_str = (
        f"{src.get('file', '?')}:{src.get('line', '?')}:{src.get('function', '?')}"
        if isinstance(src, dict)
        else "?"
    )
    when = rec.get("when") or "?"
    seq = rec.get("sequence") or "?"
    span = rec.get("span_id") or "?"
    tb = (payload.get("traceback_text") or "").rstrip("\n")
    cause = payload.get("cause_chain") or []
    call_frames = payload.get("call_frames") or []
    # Render with explicit section breaks so a tail/grep result stays readable
    # regardless of how rich the payload is. No leading indentation is
    # applied to traceback frames — Python's default format is already
    # indentation-friendly and double-indenting it made `rg` follow-ups harder.
    blocks = [
        f"[err_kind={err_kind}] [{seq}] {when}",
        f"exception:  {cls}: {msg}",
        f"boundary:   {boundary}",
        f"source:     {src_str}",
        f"span:       {span}",
    ]
    if cause:
        blocks.append("cause_chain: " + " → ".join(str(c) for c in cause))
    if call_frames:
        blocks.append(f"call_frames: {len(call_frames)} frames retained")
    if tb:
        blocks.append("--- traceback ---")
        blocks.append(tb)
        blocks.append("--- end traceback ---")
    return "\n".join(blocks)


def _format_records_grouped(records: list[dict[str, Any]]) -> str:
    """Group records by err_kind with a header and per-record blank-line spacing."""
    if not records:
        return ""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        kind = (r.get("payload") or {}).get("err_kind") or "unknown"
        grouped.setdefault(kind, []).append(r)
    blocks: list[str] = []
    for kind in sorted(grouped):
        items = grouped[kind]
        kind_label = kind.upper()
        blocks.append(
            f"=== {kind_label} ({len(items)} occurrence{'s' if len(items) != 1 else ''}) ==="
        )
        for rec in items:
            blocks.append(_format_record(rec, raw=False))
            blocks.append("")  # blank line between records
    return "\n".join(blocks).rstrip() + "\n"


def register(app: typer.Typer) -> None:
    """Register ``journal exceptions``."""

    @app.command(name="exceptions")
    def exceptions_cmd(
        run_id: str = typer.Argument(
            "",
            help="run_id (e.g. run_c38532761cfb);空 = traces/runs 下 mtime 最新的 run",
        ),
        grep: str = typer.Option("", "--grep", help="按 exception_class 过滤(子串匹配,大小写敏感)"),
        json_output: bool = typer.Option(False, "--json", help="JSON 输出给 agent"),
        raw: bool = typer.Option(False, "--raw", help="完整 payload,不做格式化"),
        traces_root: Path = typer.Option(
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """列出 run 的所有 traceback(只读 exceptions.jsonl sidecar)。"""
        run_dir = _find_run_dir(run_id, traces_root)
        exc_path = run_dir / f"{run_dir.name}.exceptions.jsonl"
        spine_path = run_dir / f"{run_dir.name}.spine.jsonl"
        # Task 1.10 / G-11: sidecar is the ONLY source of truth.
        # Spine-scan fallback removed — it produced misleading counts when
        # the sidecar was missing but spine had exception.caught events.
        source = "exceptions_index" if exc_path.exists() else "no_sidecar"
        records = _iter_records(exc_path) if exc_path.exists() else []
        if not records and not exc_path.exists():
            if json_output:
                sys.stdout.write(
                    json.dumps(
                        {
                            "run_id": run_dir.name,
                            "exceptions_path": str(exc_path),
                            "spine_path": str(spine_path),
                            "source": source,
                            "count": 0,
                            "records": [],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            else:
                print(
                    f"无异常:{exc_path} 不存在 (sidecar 缺失;per spec G-11,本命令只读 sidecar) "
                    "(该 run 无 exception.caught 事件)"
                )
            return
        if not records:
            if json_output:
                sys.stdout.write(
                    json.dumps(
                        {
                            "run_id": run_dir.name,
                            "exceptions_path": str(exc_path),
                            "spine_path": str(spine_path),
                            "source": source,
                            "count": 0,
                            "records": [],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            else:
                print(
                    f"无异常:{exc_path} 不存在,且 {spine_path} 中无完整 "
                    "exception.caught 行 (该 run 无 exception.caught 事件)"
                )
            return
        if grep:
            records = [
                r
                for r in records
                if grep in ((r.get("payload") or {}).get("exception_class") or "")
            ]

        if json_output:
            payload = {
                "run_id": run_dir.name,
                "exceptions_path": str(exc_path),
                "spine_path": str(spine_path),
                "source": source,
                "count": len(records),
                "records": records,
            }
            sys.stdout.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")
            return

        if not records:
            print(f"无匹配 traceback (grep={grep!r})")
            return

        print(f"run_id: {run_dir.name}")
        print(f"exceptions_path: {exc_path}")
        print(f"spine_path: {spine_path}")
        print(f"source: {source}")
        print(f"count: {len(records)}")
        print("===")
        if raw:
            for r in records:
                print(json.dumps(r, default=str, ensure_ascii=False))
                print()
        else:
            print(_format_records_grouped(records), end="")


__all__ = ["register"]
