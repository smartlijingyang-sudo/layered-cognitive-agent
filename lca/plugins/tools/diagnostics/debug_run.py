"""``lca-ops debug run <run_id>`` — one-shot 8-section diagnostic — ADR-0122.

The previous debug workflow required:

1. ``cat traces/runs/<run_id>/manifest.json``
2. ``cat traces/runs/<run_id>/journal.jsonl``
3. ``tail kernel.log`` (often missing — stdout went to a pipe)
4. ``ps`` + ``/proc/<pid>/fd/1`` to locate kernel stdout
5. grep through several logs

This adapter collapses all of the above into one invocation that prints:

    [1] manifest            path / summary
    [2] journal             event counts / missing-seq report
    [3] kernel.log          tail of per-run kernel log (fallback to global)
    [4] phase.cursor        last completed phase + failure node
    [5] error_ref           StopDecision.failure → typed RunDiagnostic
    [6] stack frames        top frames from the diagnostic
    [7] suggested_action    human-readable next step
    [8] replay commands    `lca-ops journal replay <run_id> --step K` (model-visible)
                            + ``grep <plan_ref> traces/runs/*/manifest.json`` (plan 复现)

Both the agent and a human can consume the output directly. JSON mode is
available via ``--json`` for downstream tooling.

Note on ``lca-ops replay``: the legacy ``lca-ops replay <run_id> --no-llm`` command
is **not** a top-level command. Real replay lives at
``lca-ops journal replay <run_id> --step K`` (ADR-0167 D10);--step is required,
and ``--no-llm`` is the default (it only dumps model-visible + actions, never
calls the LLM). See ``docs/debug/run-debug-guide.md`` for the canonical reference.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.observability.run_locator import RunLocator


@dataclass(frozen=True, slots=True)
class DebugRunReport:
    """8-section diagnostic for one run (ADR-0122).

    ADR-0068 §决策二 + ADR-0167 D10:``[8/8]`` 现在输出**多行真实可跑命令**
    —— journal replay(模型可见)+ 按 plan_ref 反查(plan 复现)。
    旧的 ``replay_command`` 单字段已弃用,改成 ``replay_commands: tuple[str, ...]``
    + 新增 ``plan_ref: str``(从 manifest 顶层读,空串 = 旧 manifest 或 solo
    未走 declarative 路径)。
    """

    run_id: str
    manifest_path: str
    manifest_summary: dict[str, Any]
    spine_events_path: str
    spine_event_count: int
    spine_missing_seqs: tuple[int, ...]
    spine_execution_points: tuple[str, ...]
    kernel_log_path: str
    kernel_log_tail: str
    phase_cursor: str | None
    failure_node_id: str | None
    error_message: str | None
    error_type: str | None
    stack_frames: tuple[dict[str, Any], ...]
    attempts: tuple[dict[str, Any], ...]
    suggested_action: str | None
    # ADR-0068 §决策二:plan_ref 是 CompiledRunPlan 的 16-hex 稳定 ID,
    # 从 ``manifest.plan_ref`` 顶层字段读(declarative 路径)或空串。
    plan_ref: str = ""
    # ADR-0167 D10:replay 是多命令组合——dump messages、grep 同 plan、复现骨架。
    replay_commands: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "manifest_path": self.manifest_path,
            "manifest_summary": self.manifest_summary,
            "spine_events_path": self.spine_events_path,
            "spine_event_count": self.spine_event_count,
            "spine_missing_seqs": list(self.spine_missing_seqs),
            "spine_execution_points": list(self.spine_execution_points),
            "kernel_log_path": self.kernel_log_path,
            "kernel_log_tail": self.kernel_log_tail,
            "phase_cursor": self.phase_cursor,
            "failure_node_id": self.failure_node_id,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "stack_frames": list(self.stack_frames),
            "attempts": list(self.attempts),
            "suggested_action": self.suggested_action,
            "plan_ref": self.plan_ref,
            "replay_commands": list(self.replay_commands),
        }

    def render_text(self) -> str:
        lines: list[str] = []
        lines.append(f"[1/8] manifest            {self.manifest_path}")
        summary = (
            self.manifest_summary.get("extra", {}).get("doctor_report", {}).get("status", "unknown")
        )
        broken = self.manifest_summary.get("extra", {}).get("doctor_report", {}).get("broken_hop")
        lines.append(f"      status={summary}" + (f" broken_hop={broken}" if broken else ""))
        lines.append(f"[1b/8] doctor.viewport     {self.manifest_path}")
        viewport_lines = _render_doctor_viewport(self.manifest_summary)
        if viewport_lines:
            for vl in viewport_lines:
                lines.append(f"      {vl}")
        else:
            lines.append("      (no doctor_report present — likely legacy run)")
        lines.append(
            f"[2/8] journal             {self.spine_events_path} "
            f"events={self.spine_event_count}"
            + (f" missing_seqs={list(self.spine_missing_seqs)}" if self.spine_missing_seqs else "")
        )
        lines.append(
            f"      spine.events        {self.spine_events_path} events={self.spine_event_count}"
        )
        if self.spine_execution_points:
            lines.append(
                "      spine.points        " + " → ".join(self.spine_execution_points[-8:])
            )
        lines.append(f"[3/8] kernel.log          {self.kernel_log_path}")
        for line in self.kernel_log_tail.splitlines()[-5:]:
            lines.append(f"      {line}")
        lines.append(f"[4/8] phase.cursor        {self.phase_cursor}")
        lines.append(f"[5/8] error_ref           {self.error_message or '(none)'}")
        lines.append(f"      error_type:        {self.error_type or '(none)'}")
        lines.append("[6/8] stack frames")
        for frame in self.stack_frames[:8]:
            lines.append(
                f"      {frame.get('filename', '?')}:{frame.get('lineno', '?')} "
                f"in {frame.get('name', '?')}"
            )
        lines.append(f"[7/8] suggested_action    {self.suggested_action or '(none)'}")
        # [8/8] 复现命令:journal replay (model-visible) + plan_ref grep (图复现)。
        # ADR-0068 §决策二:plan_ref 是 run 的 16-hex 稳定 ID,可一锤定音反查。
        lines.append(
            f"[8/8] plan_ref            {self.plan_ref or '(no plan_ref on this manifest)'}"
        )
        if self.replay_commands:
            for idx, cmd in enumerate(self.replay_commands):
                prefix = "      └─" if idx == len(self.replay_commands) - 1 else "      ├─"
                lines.append(f"{prefix} {cmd}")
        else:
            lines.append("      (no replay commands)")
        return "\n".join(lines)


class DebugRunToolAdapter:
    """``DebugRunToolAdapter(path).debug_run(run_id)`` → DebugRunReport."""

    def __init__(self, locator: RunLocator) -> None:
        self._locator = locator

    @classmethod
    def from_locator_root(cls, root: str | Path) -> DebugRunToolAdapter:
        from lca.infrastructure.observability.backends.run_locator_fs import (
            FilesystemRunLocator,
        )

        return cls(FilesystemRunLocator(Path(root)))

    def debug_run(self, run_id: str) -> DebugRunReport:
        run_dir = self._locator.run_dir(run_id)
        manifest_path = self._locator.manifest_path(run_id)
        spine_events_path = self._locator.events_path(run_id)
        kernel_log_path = self._locator.kernel_log_path(run_id)

        manifest_summary = _safe_json(manifest_path)
        spine_events = _safe_lines(spine_events_path)
        seqs = sorted({e.get("run_seq") for e in spine_events if isinstance(e.get("run_seq"), int)})
        missing_seqs = tuple(
            s for s in range(1, (seqs[-1] if seqs else 0) + 1) if s not in set(seqs)
        )
        spine_points = tuple(
            str(e.get("execution_point"))
            for e in spine_events
            if isinstance(e.get("execution_point"), str)
        )

        failure_node_id, error_message, error_type = _extract_failure(
            manifest_summary, spine_events
        )
        phase_cursor = _extract_phase_cursor(spine_events)
        attempts = _extract_attempts(manifest_summary)
        stack_frames, suggested = _extract_diagnostic(manifest_summary)

        tail = _tail_lines(kernel_log_path)

        # ADR-0068 §决策二:plan_ref 从 manifest 顶层字段读,SSOT,16-hex。
        # ADR-0167 D10:replay 是多命令组合 —— journal replay 走 model-visible
        # 重放;``grep plan_ref`` 走 plan 拓扑反查。``lca-ops replay --no-llm``
        # 这个旧命令**不存在**(曾误写在 AGENTS.md / ADR-0122 / debug-run 输出
        # 里);真实命令是 ``lca-ops journal replay <run_id> --step K``,且
        # 默认就是 --no-llm 模式(只 dump messages + actions,不调 LLM)。
        plan_ref = str(manifest_summary.get("plan_ref", "") or "").strip()
        replay_commands: list[str] = [
            f"lca-ops journal replay {run_id} --step 1 --diff-only",
        ]
        if plan_ref:
            replay_commands.append(
                f"grep -rl {plan_ref} traces/runs/*/manifest.json  # 找同 plan 的所有 run"
            )

        return DebugRunReport(
            run_id=run_id,
            manifest_path=str(manifest_path),
            manifest_summary=manifest_summary,
            spine_events_path=str(spine_events_path),
            spine_event_count=len(spine_events),
            spine_missing_seqs=missing_seqs,
            spine_execution_points=spine_points,
            kernel_log_path=str(kernel_log_path),
            kernel_log_tail=tail,
            phase_cursor=phase_cursor,
            failure_node_id=failure_node_id,
            error_message=error_message,
            error_type=error_type,
            stack_frames=stack_frames,
            attempts=attempts,
            suggested_action=suggested,
            plan_ref=plan_ref,
            replay_commands=tuple(replay_commands),
        )


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _safe_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    text = path.read_text()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                out.append(obj)
            idx = end
        except Exception:
            break
    return out


def _extract_failure(
    manifest: dict[str, Any], spine_events: list[dict[str, Any]]
) -> tuple[str | None, str | None, str | None]:
    """失败节点 + 错误信息全部从 manifest extra 推导(spine-only)。

    spine 流只有 execution_point 序列,没有 v2 envelope 的 ``descriptor.type``
    字段,所以失败细节必须从 manifest 的 doctor_report / session_error / flush_errors 抽取。
    """
    extra = manifest.get("extra", {}) or {}
    doctor = extra.get("doctor_report", {}) or {}
    h6 = doctor.get("hops", {}).get("H6", {}) or {}
    error_message = h6.get("error") or extra.get("session_error") or None
    if isinstance(error_message, str) and not error_message.strip():
        error_message = None
    error_type: str | None = None
    failure_node: str | None = None
    flush_errors = extra.get("flush_errors", []) or []
    if isinstance(flush_errors, list) and flush_errors:
        last = flush_errors[-1] if isinstance(flush_errors[-1], dict) else {}
        if last.get("node_id"):
            failure_node = str(last["node_id"])
        if last.get("exception_class"):
            error_type = str(last["exception_class"])
    # 兜底:spine 流里的 exception.caught EP(出现时附 payload.error_type)
    for event in reversed(spine_events):
        if event.get("execution_point") != "exception.caught":
            continue
        data = event.get("payload") or event.get("data") or {}
        error_type = error_type or data.get("error_type")
        node = data.get("node_id")
        if node:
            failure_node = failure_node or str(node)
        break
    return failure_node, error_message, error_type


def _extract_phase_cursor(spine_events: list[dict[str, Any]]) -> str | None:
    """从 spine execution_point 序列推 phase cursor(粗粒度:最后一个 phase.* EP)。"""
    phase_eps = (
        "phase.perceive.fold",
        "phase.think.fold",
        "phase.act.fold",
        "phase.reflect.fold",
        "phase.remember.fold",
        "phase.stop.fold",
    )
    for event in reversed(spine_events):
        ep = event.get("execution_point")
        if isinstance(ep, str) and ep in phase_eps:
            return ep
    return None


def _extract_attempts(manifest: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    attempts = (
        manifest.get("extra", {})
        .get("doctor_report", {})
        .get("hops", {})
        .get("H6", {})
        .get("attempts", [])
    )
    if isinstance(attempts, list):
        return tuple(a for a in attempts if isinstance(a, dict))
    return ()


def _extract_diagnostic(
    manifest: dict[str, Any],
) -> tuple[tuple[dict[str, Any], ...], str | None]:
    diag = manifest.get("extra", {}).get("doctor_report", {}).get("diagnostic")
    if not isinstance(diag, dict):
        return (), None
    return (
        tuple(f for f in diag.get("stack", []) if isinstance(f, dict)),
        diag.get("suggested_action"),
    )


def _tail_lines(path: Path, max_lines: int = 50) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text()
    except Exception:
        return ""
    return "\n".join(text.splitlines()[-max_lines:])


def _render_doctor_viewport(manifest_summary: dict[str, Any]) -> list[str]:
    """Project the ``extra.doctor_report`` block as a 1-line-per-key view.

    The viewport reads from the manifest JSON (no RunManifest schema
    change). Format: ``key: <value>`` per line, sorted for stable diffs.
    """
    doctor = manifest_summary.get("extra", {}).get("doctor_report", {}) or {}
    if not doctor:
        return []
    keys_of_interest = (
        "status",
        "broken_hop",
        "mode",
        "outcome",
        "factory",
        "consistency",
        "summary",
        "trace_id",
        "journal_path",
        "schema",
    )
    rendered: list[str] = []
    for key in keys_of_interest:
        if key in doctor:
            value = doctor[key]
            rendered.append(f"{key}: {value}")
    return rendered
