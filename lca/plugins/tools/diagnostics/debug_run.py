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
    [8] replay command      `lca-ops replay <run_id> [--no-llm]`

Both the agent and a human can consume the output directly. JSON mode is
available via ``--json`` for downstream tooling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.observability.run_locator import RunLocator


@dataclass(frozen=True, slots=True)
class DebugRunReport:
    """8-section diagnostic for one run (ADR-0122)."""

    run_id: str
    manifest_path: str
    manifest_summary: dict[str, Any]
    journal_path: str
    journal_event_count: int
    journal_missing_seqs: tuple[int, ...]
    spine_events_path: str
    spine_event_count: int
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
    replay_command: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "manifest_path": self.manifest_path,
            "manifest_summary": self.manifest_summary,
            "journal_path": self.journal_path,
            "journal_event_count": self.journal_event_count,
            "journal_missing_seqs": list(self.journal_missing_seqs),
            "spine_events_path": self.spine_events_path,
            "spine_event_count": self.spine_event_count,
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
            "replay_command": self.replay_command,
        }

    def render_text(self) -> str:
        lines: list[str] = []
        lines.append(f"[1/8] manifest            {self.manifest_path}")
        summary = (
            self.manifest_summary.get("extra", {}).get("doctor_report", {}).get("status", "unknown")
        )
        broken = self.manifest_summary.get("extra", {}).get("doctor_report", {}).get("broken_hop")
        lines.append(f"      status={summary}" + (f" broken_hop={broken}" if broken else ""))
        lines.append(
            f"[2/8] journal             {self.journal_path} "
            f"events={self.journal_event_count}"
            + (
                f" missing_seqs={list(self.journal_missing_seqs)}"
                if self.journal_missing_seqs
                else ""
            )
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
        lines.append("[6/8] stack frames")
        for frame in self.stack_frames[:8]:
            lines.append(
                f"      {frame.get('filename', '?')}:{frame.get('lineno', '?')} "
                f"in {frame.get('name', '?')}"
            )
        lines.append("[7/8] suggested_action    " + (self.suggested_action or "(none)"))
        lines.append(f"[8/8] replay command      {self.replay_command}")
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
        journal_path = self._locator.journal_path(run_id)
        spine_events_path = run_dir / "events.jsonl"
        kernel_log_path = run_dir / "kernel.log"

        manifest_summary = _safe_json(manifest_path)
        journal = _safe_lines(journal_path)
        spine_events = _safe_lines(spine_events_path)
        seqs = sorted({e.get("run_seq") for e in journal if isinstance(e.get("run_seq"), int)})
        missing_seqs = tuple(
            s for s in range(1, (seqs[-1] if seqs else 0) + 1) if s not in set(seqs)
        )
        spine_points = tuple(
            str(e.get("execution_point"))
            for e in spine_events
            if isinstance(e.get("execution_point"), str)
        )

        failure_node_id, error_message, error_type = _extract_failure(manifest_summary, journal)
        phase_cursor = _extract_phase_cursor(journal)
        attempts = _extract_attempts(manifest_summary)
        stack_frames, suggested = _extract_diagnostic(manifest_summary)

        tail = _tail_lines(kernel_log_path)

        return DebugRunReport(
            run_id=run_id,
            manifest_path=str(manifest_path),
            manifest_summary=manifest_summary,
            journal_path=str(journal_path),
            journal_event_count=len(journal),
            journal_missing_seqs=missing_seqs,
            spine_events_path=str(spine_events_path),
            spine_event_count=len(spine_events),
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
            replay_command=f"lca-ops replay {run_id} --no-llm",
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
    manifest: dict[str, Any], journal: list[dict[str, Any]]
) -> tuple[str | None, str | None, str | None]:
    extra = manifest.get("extra", {}) or {}
    doctor = extra.get("doctor_report", {}) or {}
    h6 = doctor.get("hops", {}).get("H6", {}) or {}
    error_message = h6.get("error") or extra.get("session_error") or None
    if isinstance(error_message, str) and not error_message.strip():
        error_message = None
    error_type = None
    failure_node = None
    for event in reversed(journal):
        attrs = event.get("data", {}).get("attributes", {}) or {}
        payload = attrs.get("payload", {}) or {}
        if payload.get("node") in {"stop.main", "think.main"}:
            failure = payload.get("failure", {}) or {}
            if failure.get("node_id"):
                failure_node = failure.get("node_id")
            if failure.get("reason") == "error":
                error_message = error_message or "phase_error: " + (
                    failure.get("final_output") or "phase exhausted"
                )
            attempts = failure.get("attempts") or []
            if attempts:
                error_type = attempts[-1].get("error_type")
            break
    return failure_node, error_message, error_type


def _extract_phase_cursor(journal: list[dict[str, Any]]) -> str | None:
    for event in reversed(journal):
        data = event.get("data", {}) or {}
        if event.get("descriptor", {}).get("type") == "RuntimeObserved":
            if data.get("plugin") == "stop":
                return "stop.main (failed)"
            if data.get("operation") == "phase.fact":
                payload = (data.get("attributes") or {}).get("payload") or {}
                node = payload.get("node")
                if node:
                    return node
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
