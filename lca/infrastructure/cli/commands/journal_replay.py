"""Journal trajectory / replay / verify-model-visible (ADR-0167 D9 / D10)。

新子命令:

- ``lca-ops journal trajectory <run_id> [--out PATH]``
  渲染 DSH Trajectory 风格 HTML（waterfall）；默认写到
  ``traces/runs/<id>/journal.trajectory.html``。
- ``lca-ops journal replay <run_id> --step N [--tool NAME=JSON ...]``
  打印 step 的模型所见 + 所做；``--tool`` 仅算 diff，绝不私自执行。
- ``lca-ops journal verify-model-visible <run_id>``
  校验 ``request-header.digest`` 与 messages / tools / manifest 的 sha256 一致。

设计：纯只读；不调 LLM / tool；不依赖 boot；走 FilesystemRunLocator 直读。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from lca.infrastructure.observability.journal.step.reader import (
    read_step_document,
)
from lca.infrastructure.observability.replay import StandardCursor
from lca.infrastructure.observability.spine.derivers.waterfall import (
    WaterfallDeriver,
)
from lca.infrastructure.observability.spine.event_record import EventRecord

_DEFAULT_TRACES_ROOT = Path("traces")


def _read_doc(run_id: str, traces_root: Path):
    journal_path = traces_root / "runs" / run_id / "journal.json"
    if not journal_path.exists():
        raise FileNotFoundError(f"journal.json not found: {journal_path}")
    return read_step_document(journal_path), journal_path


def register(app: typer.Typer) -> None:
    @app.command(name="trajectory")
    def trajectory_cmd(
        run_id: str = typer.Argument(..., help="run_id"),
        out: Path = typer.Option(  # noqa: B008
            None, "--out", help="输出 HTML 路径；默认 traces/runs/<id>/journal.trajectory.html"
        ),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT,
            "--traces-root",
        ),
    ) -> None:
        """DSH Trajectory 风格 HTML —— 与 LobeHub / WebServer 解耦。"""
        run_dir = traces_root / "runs" / run_id
        mv_path = run_dir / "model_visible" if (run_dir / "model_visible").exists() else None
        deriver = WaterfallDeriver(run_id, model_visible_root=mv_path)
        for record in _read_events_jsonl(run_id, traces_root):
            deriver.on_event(record)
        if out is None:
            out = run_dir / "journal.trajectory.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        deriver.write(out)
        typer.echo(f"trajectory written: {out}")

    @app.command(name="replay")
    def replay_cmd(
        run_id: str = typer.Argument(..., help="run_id"),
        step: int = typer.Option(..., "--step", help="step_index"),
        diff_only: bool = typer.Option(
            False, "--diff-only", help="只打印 messages 与 actions 的摘要"
        ),
        tool_args: list[str] | None = typer.Option(  # noqa: B008
            None,
            "--tool",
            help="NAME=JSON_OVERRIDE（仅算 diff，不跑 tool）",
        ),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT,
            "--traces-root",
        ),
    ) -> None:
        """打印 step 的 model-visible + actions; --tool NAME=JSON 仅返回 diff."""
        cursor = StandardCursor(traces_root)
        overrides: dict[str, Any] = {}
        if tool_args:
            for entry in tool_args:
                if "=" not in entry:
                    typer.echo(f"--tool 期望 NAME=JSON；忽略 {entry!r}", err=True)
                    continue
                name, raw = entry.split("=", 1)
                try:
                    overrides[name] = json.loads(raw)
                except json.JSONDecodeError:
                    typer.echo(f"--tool {name} 的 JSON 解析失败；原样保留", err=True)
                    overrides[name] = raw

        if overrides:
            ctx = cursor.with_override(
                run_id=run_id,
                step_index=step,
                tool_args_overrides=overrides,
            )
        else:
            ctx = cursor.at(run_id=run_id, step_index=step)

        if diff_only:
            typer.echo(
                json.dumps(
                    {
                        "step_id": ctx.step_id,
                        "inferred": ctx.inferred,
                        "digest_verified": ctx.digest_verified,
                        "messages_count": len(ctx.messages),
                        "actions_count": len(ctx.actions),
                    },
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(
            json.dumps(
                {
                    "step_id": ctx.step_id,
                    "source": ctx.source,
                    "inferred": ctx.inferred,
                    "digest_verified": ctx.digest_verified,
                    "request_header": ctx.request_header,
                    "messages": list(ctx.messages),
                    "tool_schemas": list(ctx.tool_schemas),
                    "context_manifest": ctx.context_manifest,
                    "actions": list(ctx.actions),
                },
                ensure_ascii=False,
                default=str,
            )
        )

    @app.command(name="verify-model-visible")
    def verify_cmd(
        run_id: str = typer.Argument(..., help="run_id"),
        traces_root: Path = typer.Option(  # noqa: B008
            _DEFAULT_TRACES_ROOT,
            "--traces-root",
        ),
    ) -> None:
        """校验每个 think step 的 request-header.digest 与 messages/tools/manifest sha256 一致。"""
        doc, _ = _read_doc(run_id, traces_root)
        cursor = StandardCursor(traces_root)
        passed = failed = 0
        for s in doc.steps:
            try:
                ctx = cursor.at(run_id=run_id, step_index=s.step_index)
            except Exception as exc:
                typer.echo(f"step {s.step_index}: error {exc}", err=True)
                failed += 1
                continue
            if ctx.digest_verified:
                typer.echo(f"step {s.step_index}: ok (inferred={ctx.inferred})")
                passed += 1
            else:
                typer.echo(f"step {s.step_index}: digest mismatch (inferred={ctx.inferred})")
                failed += 1
        typer.echo(f"\nverify-model-visible: passed={passed} failed={failed}")


def _read_events_jsonl(run_id: str, traces_root: Path) -> list[EventRecord]:
    """Read ``events.jsonl`` into ``EventRecord`` instances for derivers.

    Returns empty list if file missing. Per-line parse errors are skipped
    (best-effort; trajectory page degrades gracefully).
    """
    events_path = traces_root / "runs" / run_id / "events.jsonl"
    if not events_path.exists():
        return []
    out: list[EventRecord] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(EventRecord(**json.loads(line)))
        except (TypeError, ValueError):
            # Unknown EP / missing field — skip, not fail (graceful degrade)
            continue
    return out


__all__ = ["register"]
