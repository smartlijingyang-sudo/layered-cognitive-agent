"""``lca-ops journal step <run> --step N`` —— 渲单个 step 的全文事实。

看板 / 一行 trace 不够看清现场 —— 这是 single-step, 一次读 step +
thinking + tool_call + tool_result 五个原语到一个干净块。
不做 sub-step 嵌套 / 不做 phase tree, 一张表一个 step。

设计原则 (first-principles):

1. 单一源是 ``journal.json`` (lca.journal/3.1);不在端点再去 grep spine。
2. reasoning / raw_response_preview 在 journal 里已被 step_tree_accumulator 截到头+尾预算,
   ``--tail`` 可看 model_visible/messages.json 完整版。
3. tool_call.arguments / stdout_head 已经在 step.tool_call/result EP payload 直发;
   --json 给 agent,文本给人。
4. --model-visible PATH 把 detail 路径附在末尾(不是自动打开, 避免副作用)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

_DEFAULT_TRACES_ROOT = Path("traces")


def _resolve_run_dir(run_id: str, traces_root: Path) -> Path | None:
    if not run_id:
        from lca.infrastructure.cli.commands._shared import find_latest_run_id

        run_id = find_latest_run_id(traces_root)
    if not run_id:
        return None
    return traces_root / "runs" / run_id


def _load_journal(run_dir: Path) -> dict[str, Any] | None:
    from lca.infrastructure.observability.backends.run_locator_fs import (
        FilesystemRunLocator,
    )

    locator = FilesystemRunLocator(run_dir.parent)
    journal_path = locator.journal_step_path(run_dir.name)
    if not journal_path.exists():
        return None
    try:
        return json.loads(journal_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _select_step(doc: dict[str, Any], step_index: int) -> dict[str, Any] | None:
    for st in doc.get("steps", []):
        if int(st.get("step_index", 0)) == step_index:
            return st
    return None


def _format_section(title: str, body: str | None) -> list[str]:
    if not body:
        return []
    lines = [f"--- {title} ---"]
    for line in body.splitlines() or ["(empty)"]:
        lines.append(line)
    return lines


def _format_step_human(step: dict[str, Any]) -> str:
    blocks: list[str] = []
    header = (
        f"step_id: {step.get('step_id')}  "
        f"step_index: {step.get('step_index')}  "
        f"phase: {step.get('phase')}  "
        f"outcome: {step.get('outcome')}"
    )
    duration_ms = step.get("duration_ms") or 0
    blocks.append(header)
    blocks.append(f"duration_ms: {duration_ms}")
    parent = step.get("parent_step_id")
    if parent:
        blocks.append(f"parent_step_id: {parent}")
    subagent = step.get("subagent_role")
    if subagent:
        blocks.append(f"subagent_role: {subagent}")

    ctx = step.get("context_before") or {}
    if ctx:
        obj = ctx.get("objective", "")
        if obj:
            blocks.append("")
            blocks.append("--- context.objective ---")
            for line in obj.splitlines() or ["(empty)"]:
                blocks.append(line)

    thinking = step.get("thinking")
    if thinking:
        blocks.append("")
        blocks.append("--- thinking ---")
        blocks.append(f"model:           {thinking.get('model', '')}")
        blocks.append(f"latency_ms:      {thinking.get('latency_ms', 0)}")
        if thinking.get("prompt_tokens") is not None:
            blocks.append(f"prompt_tokens:   {thinking.get('prompt_tokens')}")
        if thinking.get("completion_tokens") is not None:
            blocks.append(f"completion_tokens:{thinking.get('completion_tokens')}")
        blocks.append(f"decision:        {thinking.get('decision', '')}")
        blocks.extend(_format_section("reasoning (kept)", thinking.get("reasoning")))
        blocks.extend(_format_section("raw_response_preview", thinking.get("raw_response_preview")))

    tc = step.get("tool_call")
    if tc:
        blocks.append("")
        blocks.append("--- tool_call ---")
        for key in ("invocation_id", "name", "arguments_summary"):
            val = tc.get(key)
            if val:
                blocks.append(f"{key}: {val}")
        args = tc.get("arguments") or {}
        if args:
            blocks.append("arguments:")
            blocks.append(json.dumps(args, default=str, ensure_ascii=False, indent=2))

    tr = step.get("tool_result")
    if tr:
        blocks.append("")
        blocks.append("--- tool_result ---")
        blocks.append(f"ok:               {tr.get('ok')}")
        blocks.append(f"latency_ms:       {tr.get('latency_ms', 0)}")
        stdout_head = tr.get("stdout_head") or ""
        if stdout_head:
            blocks.append("stdout_head:")
            for line in stdout_head.splitlines():
                blocks.append(f"  {line}")
        if tr.get("stdout_chars_total"):
            blocks.append(
                f"stdout_chars_total: {tr.get('stdout_chars_total')}"
                f"{'  (truncated)' if tr.get('stdout_truncated') else ''}"
            )
        stderr = tr.get("stderr") or ""
        if stderr:
            blocks.append("stderr:")
            for line in stderr.splitlines():
                blocks.append(f"  {line}")
        if tr.get("files_created"):
            blocks.append("files_created:")
            for f in tr["files_created"]:
                blocks.append(f"  - {f}")
        if tr.get("error"):
            blocks.append(f"error:            {tr['error']}")
        if tr.get("delta_summary"):
            blocks.append(f"delta_summary:    {tr['delta_summary']}")

    rf = step.get("reflect")
    if rf:
        blocks.append("")
        blocks.append("--- reflect ---")
        blocks.append(f"summary: {rf.get('summary', '')}")
        if rf.get("verdict"):
            blocks.append(f"verdict: {rf['verdict']}")

    if step.get("error"):
        blocks.append("")
        blocks.append(f"error: {step['error']}")
    return "\n".join(blocks) + "\n"


def register(app: typer.Typer) -> None:
    """Register ``journal step`` under the parent journal group."""

    @app.command(name="step")
    def step_cmd(
        run_id: str = typer.Argument(
            "",
            help="run_id (e.g. run_c38532761cfb);空 = 最新一个 run(traces/latest.json)",
        ),
        step_index: int = typer.Option(..., "--step", help="step_index (1-based) within the run"),
        json_output: bool = typer.Option(False, "--json", help="完整 step JSON 输出"),
        model_visible: bool = typer.Option(
            False,
            "--model-visible",
            help="step 后附上 model_visible/<step_id> 路径(不打开文件)",
        ),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT, "--traces-root", help="traces 根目录"
        ),
    ) -> None:
        """打印单个 step 的全部事实(thinking / tool_call / tool_result)。"""
        run_dir = _resolve_run_dir(run_id, traces_root)
        if run_dir is None:
            print(f"无 run 可用 (run_id={run_id!r})")
            raise typer.Exit(1)
        if not run_dir.exists():
            print(f"run_dir 不存在: {run_dir}")
            raise typer.Exit(1)
        doc = _load_journal(run_dir)
        if doc is None:
            print(f"journal.json 不存在或损坏: {run_dir / 'journal.json'}")
            raise typer.Exit(1)
        step = _select_step(doc, step_index)
        if step is None:
            n = len(doc.get("steps", []))
            print(f"step_index={step_index} 不存在;该 run 共 {n} 个 steps")
            raise typer.Exit(1)

        if json_output:
            sys.stdout.write(json.dumps(step, default=str, ensure_ascii=False) + "\n")
            return

        print(f"run_id: {doc.get('run_id')}")
        print(f"trace_id: {doc.get('trace_id')}")
        print(_format_step_human(step), end="")

        if model_visible:
            mv_dir = run_dir / "model_visible" / (step.get("step_id") or "")
            print("")
            print(f"model_visible: {mv_dir}  (messages.json / system_prompt.md / ...)")


__all__ = ["register"]
