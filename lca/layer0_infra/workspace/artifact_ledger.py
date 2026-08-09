"""Run-scoped artifact ledger — records deliverables for closure and handoff (ADR-0051)."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.workspace import ArtifactLedgerSnapshot, WorkspaceArtifact


class ArtifactLedger:
    """Append-only registry of run workspace deliverables."""

    def __init__(self) -> None:
        self._artifacts: list[WorkspaceArtifact] = []
        self._seen: set[str] = set()

    def record_file(
        self,
        *,
        name: str,
        mime_type: str,
        url: str = "",
        size_bytes: int = 0,
        tool_name: str = "",
        agent_role: str = "",
        guest_path: str = "",
    ) -> None:
        key = f"{name}|{mime_type}|{url}|{guest_path}"
        if key in self._seen:
            return
        self._seen.add(key)
        self._artifacts.append(
            WorkspaceArtifact(
                name=name,
                mime_type=mime_type,
                url=url,
                size_bytes=size_bytes,
                tool_name=tool_name,
                agent_role=agent_role,
                guest_path=guest_path,
            )
        )

    def record_from_tool_files(
        self,
        files: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
        *,
        tool_name: str = "",
        agent_role: str = "",
    ) -> None:
        if not files:
            return
        for item in files:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("filename") or "").strip()
            if not name:
                continue
            mime = str(item.get("mimeType") or item.get("mime_type") or "application/octet-stream")
            url = str(item.get("url") or "")
            size = int(item.get("sizeBytes") or item.get("size_bytes") or 0)
            guest = str(item.get("path") or item.get("guest_path") or "")
            self.record_file(
                name=name,
                mime_type=mime,
                url=url,
                size_bytes=size,
                tool_name=tool_name,
                agent_role=agent_role,
                guest_path=guest,
            )

    def snapshot(self) -> ArtifactLedgerSnapshot:
        return ArtifactLedgerSnapshot(artifacts=tuple(self._artifacts))

    def closure_text(self, *, locale: str = "zh") -> str:
        return artifact_closure_text(self.snapshot(), locale=locale)

    def handoff_block(self) -> str:
        return artifact_handoff_block(self.snapshot())


def artifact_closure_text(snapshot: ArtifactLedgerSnapshot, *, locale: str = "zh") -> str:
    """User-facing summary when agent never explicitly responded."""
    if not snapshot.artifacts:
        return ""
    lines = (
        ["任务已完成，已生成以下文件："]
        if locale.startswith("zh")
        else ["Task completed. Generated files:"]
    )
    for art in snapshot.artifacts:
        size_kb = art.size_bytes // 1024 if art.size_bytes else 0
        link = art.url or art.guest_path or art.name
        lines.append(f"- **{art.name}** ({art.mime_type}, {size_kb} KB) — {link}")
    return "\n".join(lines)


def artifact_handoff_block(snapshot: ArtifactLedgerSnapshot) -> str:
    """Structured block for pipeline member task injection."""
    if not snapshot.artifacts:
        return ""
    lines = ["[工作区已产出文件 — 可直接读取，勿猜测路径]"]
    for art in snapshot.artifacts:
        path = art.guest_path or f"/mnt/data/outputs/{art.name}"
        lines.append(f"- {art.name} → {path} ({art.mime_type})")
    return "\n".join(lines)
