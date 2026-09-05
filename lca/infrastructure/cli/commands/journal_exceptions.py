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

设计上优先读 ``<run_id>.exceptions.jsonl``(旧 FileSink 双写索引)。
ADR-0183 ``SpineSink`` 路径只写 ``<run_id>.spine.jsonl`` 时,本命令回退扫描
spine 主 ledger 中的 ``exception.caught`` 行,避免"有异常但 CLI 报无异常"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

_DEFAULT_TRACES_ROOT = Path("traces")


def _find_run_dir(run_id: str, traces_root: Path) -> Path:
    if not run_id:
        from lca.infrastructure.cli.commands._shared import find_latest_run_id

        run_id = find_latest_run_id(traces_root)
    return traces_root / "runs" / run_id


def _iter_spine_exception_records(spine_path: Path) -> list[dict[str, Any]]:
    if not spine_path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in spine_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("execution_point") != "exception.caught":
            continue
        payload = rec.get("payload")
        if not isinstance(payload, dict):
            continue
        # 兼容旧 offload 占位符:只有 offloaded digest 时跳过,交给 sidecar 路径。
        if payload.keys() <= {"offloaded", "execution_point"} or payload.get("offloaded"):
            continue
        out.append(rec)
    return out


def _iter_records(path: Path) -> list[dict[str, Any]]:
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
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """列出 run 的所有 traceback(优先 exceptions.jsonl,回退 spine.jsonl)。"""
        run_dir = _find_run_dir(run_id, traces_root)
        exc_path = run_dir / f"{run_dir.name}.exceptions.jsonl"
        spine_path = run_dir / f"{run_dir.name}.spine.jsonl"
        source = "exceptions_index"
        if exc_path.exists():
            records = _iter_records(exc_path)
        else:
            records = _iter_spine_exception_records(spine_path)
            source = "spine_fallback"
        if not records and not exc_path.exists() and not spine_path.exists():
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
                    f"无异常:{exc_path} 不存在且 {spine_path} 不存在 "
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
