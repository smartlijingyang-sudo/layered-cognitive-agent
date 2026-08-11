"""Compose LCA run questions with attachment context."""

from __future__ import annotations

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT
from lca.layer0_infra.file_store import FileStore, LocalFileStore


def compose_run_question(
    user_text: str,
    attachment_ids: tuple[str, ...],
    store: FileStore,
) -> str:
    """Build the task string passed to ``Agent.run`` / ``Team.run``.

    Prior conversation turns are **not** embedded here — they travel via
    ``RunContext.extra`` / ``AgentState.working_memory`` (LobeHub messages[] parity).
    """
    return _question_with_attachments(user_text, attachment_ids, store)


def _question_with_attachments(
    question: str, attachment_ids: tuple[str, ...], store: FileStore
) -> str:
    if not attachment_ids:
        return question.strip()

    lines = [
        "[用户附件]",
        (
            f"（附件已挂载到 {SANDBOX_MOUNT_ROOT}/<文件名>；"
            "分析前先 activate_skill 加载对应 skill，再用 run_skill_script 执行命令）"
        ),
    ]
    for attachment_id in attachment_ids:
        meta = store.get(attachment_id)
        if meta is None:
            lines.append(f"- (missing) {attachment_id}")
            continue
        guest_path = f"{SANDBOX_MOUNT_ROOT}/{meta.name}"
        lines.append(
            f"- {meta.name} → {guest_path} "
            f"({meta.mime_type}, {meta.size_bytes} B) "
            f"url={meta.url} id={meta.attachment_id}"
        )
        if isinstance(store, LocalFileStore):
            preview = store.read_text_preview(attachment_id)
            if preview:
                lines.append("  preview:")
                for preview_line in preview.splitlines()[:40]:
                    lines.append(f"  | {preview_line}")

    lines.append("")
    lines.append(f"用户问题: {question.strip()}")
    return "\n".join(lines)
