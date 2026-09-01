"""Journal step-tree viewer CLI(ADR-0164 草案 Phase 5)。

三个新命令:
    lcaops journal steps <run_id>           # step 表 + 一句话摘要
    lcaops journal steps <run_id> --step N  # 第 N 步详情(JSON / markdown)
    lcaops journal steps <run_id> --summary  # 因果链
    lcaops journal steps <run_id> --json    # 完整 JournalDocument JSON

    lcaops journal narrative <run_id>       # 输出 narrative.md
    lcaops journal raw <run_id>             # 兜底读 journal.raw.jsonl

设计:
    - 输入: <run_id> + traces 根目录(--traces-root 默认 "traces")
    - 路径解析: 走 FilesystemRunLocator(直接构造,不用 boot 全套)
    - 输出: 表格 / JSON / markdown, 适合人类读 + pipe
    - 错误友好: 文件不存在 / 损坏 → 友好提示 + typer.Exit(1)

不做的事:
    - 不发请求给 kernel_serve
    - 不修改文件
    - 不读 evidence(由 reader 按需 fetch)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca.infrastructure.observability.journal.step.reader import read_step_document

_OUTCOME_ICON: dict[str | None, str] = {
    "ok": "✓",
    "fail": "✗",
    "skip": "→",
    None: "·",
}

_DEFAULT_TRACES_ROOT = Path("traces")  # CLI 默认 traces 根目录


def _format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "—"
    if duration_ms < 1000:
        return f"{duration_ms}ms"
    seconds = duration_ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f}m"


def _summarize_step_one_line(step) -> str:
    """一行人话摘要(用于表格)。"""
    if step.reflect is not None and step.reflect.summary:
        return step.reflect.summary[:80]
    if step.tool_result is not None and step.tool_result.delta_summary:
        return step.tool_result.delta_summary[:80]
    if step.thinking is not None and step.thinking.decision:
        return f"[{step.thinking.decision}]"
    if step.tool_call is not None:
        return step.tool_call.arguments_summary[:80] or step.tool_call.name
    return "—"


def _print_step_table(doc) -> None:
    """打印 step 表 (跟 narrative.md 的 summary 表同款, 但更简洁)。"""
    print(f"# {doc.metadata.objective}")
    print(
        f"run_id={doc.run_id}  trace_id={doc.trace_id}  "
        f"outcome={doc.metadata.outcome}  steps={len(doc.steps)}"
    )
    print()
    print(f"{'#':>3}  {'phase':<10}  {'duration':>8}  {'outcome':<6}  摘要")
    print(f"{'-' * 3}  {'-' * 10}  {'-' * 8}  {'-' * 6}  {'-' * 50}")
    for step in doc.steps:
        outcome_icon = _OUTCOME_ICON.get(step.outcome, "·")
        outcome_str = step.outcome or "—"
        print(
            f"{step.step_index:>3}  {step.phase:<10}  "
            f"{_format_duration(step.duration_ms):>8}  "
            f"{outcome_icon} {outcome_str:<4}  {_summarize_step_one_line(step)}"
        )


def _print_step_detail(doc, step_index: int) -> None:
    """打印第 N 步的完整内容(markdown 格式,复用 StepNarrativeWriter)。"""
    step = doc.step_by_index(step_index)
    if step is None:
        print(f"step index {step_index} 不存在 (1..{len(doc.steps)})", file=sys.stderr)
        raise SystemExit(1)
    # 构造单步 document
    from lca.contracts.models.observability.journal_doc import (
        close_document,
        empty_document,
    )

    single_doc = empty_document(
        run_id=doc.run_id,
        trace_id=doc.trace_id,
        metadata=doc.metadata,
        started_at=doc.started_at,
    )
    single_doc = close_document(single_doc, outcome="in_progress", closed_at=None)
    # append_step 是 frozen → 新 object
    from lca.contracts.models.observability import append_step

    single_doc = append_step(single_doc, step)
    md = StepNarrativeWriter("").render(single_doc)
    print(md)


def _print_summary_chain(doc) -> None:
    """打印因果链(prior_summary_chain 链式)。"""
    chain = doc.prior_summary_chain()
    if not chain:
        print("(空)")
        return
    for i, s in enumerate(chain, 1):
        print(f"{i:>3}. {s}")


def _read_doc_or_exit(traces_root: Path, run_id: str):
    """解析路径 + read document, 错误时友好提示 + typer.Exit(1)。"""
    locator = FilesystemRunLocator(traces_root)
    journal_path = locator.journal_step_path(run_id)
    if not journal_path.exists():
        print(f"journal.json not found: {journal_path}", file=sys.stderr)
        print("  hint: 检查 --traces-root 是否正确,run_id 是否存在", file=sys.stderr)
        raise SystemExit(1)
    try:
        return read_step_document(journal_path)
    except Exception as exc:
        print(f"读取失败: {journal_path}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def register(app: typer.Typer) -> None:
    """Register step-tree viewer commands under ``journal`` group.

    期望: app 已是 ``journal`` group(由 journal.py 注册)。
    """

    @app.command(name="steps")
    def steps_cmd(
        run_id: str = typer.Argument(..., help="run_id (e.g. run_c38532761cfb)"),
        step_index: int | None = typer.Option(None, "--step", "-s", help="只看第 N步 (1-based)"),
        summary_only: bool = typer.Option(False, "--summary", help="只输出 prior_summary_chain"),
        json_output: bool = typer.Option(False, "--json", help="完整 JournalDocument JSON"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """列 step-tree: 表格 / 单步详情 / 因果链 / 完整 JSON."""
        doc = _read_doc_or_exit(traces_root, run_id)
        if json_output:
            payload = _document_to_dict(doc)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        if summary_only:
            _print_summary_chain(doc)
            return
        if step_index is not None:
            _print_step_detail(doc, step_index)
            return
        _print_step_table(doc)

    @app.command(name="narrative")
    def narrative_cmd(
        run_id: str = typer.Argument(..., help="run_id"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """输出 narrative.md(StepNarrativeWriter 写出的 markdown)。"""
        locator = FilesystemRunLocator(traces_root)
        path = locator.journal_narrative_path(run_id)
        if not path.exists():
            print(f"narrative.md not found: {path}", file=sys.stderr)
            raise SystemExit(1)
        sys.stdout.write(path.read_text(encoding="utf-8"))

    @app.command(name="raw")
    def raw_cmd(
        run_id: str = typer.Argument(..., help="run_id"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """兜底读 journal.raw.jsonl(legacy 流式, 回放用)。

        ADR-0164: 主路径走 step-tree (steps / narrative); raw 仅供迁移期调试。
        """
        locator = FilesystemRunLocator(traces_root)
        path = locator.journal_path(run_id)
        if not path.exists():
            print(f"journal.raw.jsonl not found: {path}", file=sys.stderr)
            raise SystemExit(1)
        sys.stdout.write(path.read_text(encoding="utf-8"))


def _document_to_dict(doc) -> dict[str, Any]:
    """JournalDocument → JSON-friendly dict(复用 projector 反序列化逻辑)。"""
    from dataclasses import asdict, is_dataclass

    def _to_jsonable(obj: Any) -> Any:
        if is_dataclass(obj) and not isinstance(obj, type):
            return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
        if isinstance(obj, dict):
            return {k: _to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_to_jsonable(v) for v in obj]
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        return repr(obj)

    return _to_jsonable(doc)


__all__ = ["register"]
