"""Deterministic delivery response synthesis — no extra LLM (ADR-0196)."""

from __future__ import annotations

from lca.cognition.convergence.material import collect_delivery_material
from lca.contracts.models.core.policy.convergence import DeliveryEvidence, TaskClass
from lca.contracts.models.core.state.state import AgentState

_FALLBACK = "任务产出已在工作区就绪，以下为交付说明。"
_ARTIFACT_HEADER = "工作区产出："
_FILE_HEADER = "生成文件："


def _format_body(*, stdout: str, files: tuple[str, ...], artifacts: tuple[str, ...]) -> str:
    sections: list[str] = []
    if stdout:
        sections.append(stdout)
    if files:
        sections.append(_FILE_HEADER + "\n" + "\n".join(f"- {name}" for name in files))
    if artifacts:
        sections.append(_ARTIFACT_HEADER + "\n" + "\n".join(artifacts))
    return "\n\n".join(sections)


def synthesize_delivery_response(
    state: AgentState,
    evidence: DeliveryEvidence,
    *,
    existing_text: str = "",
) -> str:
    """Build user-facing text from folded producer output and workspace ledger."""
    if existing_text.strip():
        return existing_text.strip()

    material = collect_delivery_material(state)
    body = _format_body(
        stdout=material.stdout,
        files=material.files_created,
        artifacts=material.artifact_lines,
    )
    if body:
        return body

    if evidence.task_class == "visual_artifact" and evidence.artifact_count:
        return f"{_FALLBACK}\n\n{_ARTIFACT_HEADER}\n（共 {evidence.artifact_count} 个产物）"

    return _FALLBACK


def delivery_channel_label(task_class: TaskClass) -> str:
    if task_class == "informative_text":
        return "text"
    if task_class in {"visual_artifact", "code_demo", "mixed"}:
        return "artifact"
    return "unknown"


__all__ = ["delivery_channel_label", "synthesize_delivery_response"]
