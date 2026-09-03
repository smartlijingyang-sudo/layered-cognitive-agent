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

设计上不重读 ``events.jsonl`` 主 ledger —— 主 ledger 异常行是
``{execution_point, offloaded}`` 占位符(>4 KiB offload 到 sidecar),
查 traceback 必须走 exceptions.jsonl 或 sidecar,前者是专用索引。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

_DEFAULT_TRACES_ROOT = Path("traces")


def _find_exceptions_path(run_id: str, traces_root: Path) -> Path:
    """定位 <run_id>/<run_id>.exceptions.jsonl。

    run_id 空 → 走 traces/latest.json。
    """
    if not run_id:
        from lca.infrastructure.cli.commands._shared import find_latest_run_id
        run_id = find_latest_run_id(traces_root)
    return traces_root / "runs" / run_id / f"{run_id}.exceptions.jsonl"


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
    src = payload.get("source_location") or {}
    src_str = (
        f"{src.get('file', '?')}:{src.get('line', '?')}:{src.get('function', '?')}"
        if isinstance(src, dict) else "?"
    )
    when = rec.get("when") or "?"
    seq = rec.get("sequence") or "?"
    tb = payload.get("traceback_text") or ""
    sidecar = rec.get("payload", {}).get("offloaded")  # 主 ledger 的占位符字段
    out_lines = [
        f"[{seq}] {when} {cls}: {msg}",
        f"  boundary: {boundary}",
        f"  source:   {src_str}",
    ]
    if sidecar:
        out_lines.append(f"  sidecar:  {sidecar}")
    if tb:
        out_lines.append("  traceback:")
        for tb_line in tb.splitlines():
            out_lines.append(f"    {tb_line}")
    return "\n".join(out_lines)


def register(app: typer.Typer) -> None:
    """Register ``journal exceptions``."""

    @app.command(name="exceptions")
    def exceptions_cmd(
        run_id: str = typer.Argument(
            "",
            help="run_id (e.g. run_c38532761cfb);空 = 最新一个 run(traces/latest.json)",
        ),
        grep: str = typer.Option(
            "", "--grep", help="按 exception_class 过滤(子串匹配,大小写敏感)"
        ),
        json_output: bool = typer.Option(False, "--json", help="JSON 输出给 agent"),
        raw: bool = typer.Option(False, "--raw", help="完整 payload,不做格式化"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """列出 run 的所有 traceback(从 ``<run_id>.exceptions.jsonl`` 读)。"""
        exc_path = _find_exceptions_path(run_id, traces_root)
        if not exc_path.exists():
            if json_output:
                sys.stdout.write(json.dumps({
                    "run_id": exc_path.parent.name if exc_path.parent else "",
                    "exceptions_path": str(exc_path),
                    "count": 0,
                    "records": [],
                }, ensure_ascii=False) + "\n")
            else:
                print(f"无异常:{exc_path} 不存在 (该 run 无 exception.caught 事件)")
            return

        records = _iter_records(exc_path)
        if grep:
            records = [
                r for r in records
                if grep in ((r.get("payload") or {}).get("exception_class") or "")
            ]

        if json_output:
            payload = {
                "run_id": exc_path.parent.name,
                "exceptions_path": str(exc_path),
                "count": len(records),
                "records": records,
            }
            sys.stdout.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")
            return

        if not records:
            print(f"无匹配 traceback (grep={grep!r})")
            return

        print(f"run_id: {exc_path.parent.name}")
        print(f"exceptions_path: {exc_path}")
        print(f"count: {len(records)}")
        print("---")
        for r in records:
            print(_format_record(r, raw=raw))
            print()


__all__ = ["register"]
