"""Run-scoped artifact ledger — records deliverables for closure and handoff (ADR-0051)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from lca.contracts.models.core.workspace import ArtifactLedgerSnapshot, WorkspaceArtifact
from lca.infrastructure.plane.paths import join_under
from lca.infrastructure.plane.scope import current_primary
from lca.infrastructure.workspace.deliverable import publishable_file_parts


class ArtifactLedger:
    """Append-only registry of run workspace deliverables."""

    def __init__(self) -> None:
        self._artifacts: list[WorkspaceArtifact] = []
        self._seen_names: set[str] = set()

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
        key = PurePosixPath(name).name or name
        artifact = WorkspaceArtifact(
            name=name,
            mime_type=mime_type,
            url=url,
            size_bytes=size_bytes,
            tool_name=tool_name,
            agent_role=agent_role,
            guest_path=guest_path,
        )
        if key in self._seen_names:
            for index, existing in enumerate(self._artifacts):
                existing_key = PurePosixPath(existing.name).name or existing.name
                if existing_key == key:
                    self._artifacts[index] = artifact
                    return
            return
        self._seen_names.add(key)
        self._artifacts.append(artifact)

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

    def record_harvest(
        self,
        files: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
        *,
        stdout: str = "",
        tool_name: str = "",
        agent_role: str = "",
        command: str = "",
    ) -> None:
        """User ledger: publishable harvests only, latest basename wins."""
        self.record_from_tool_files(
            publishable_file_parts(
                list(files or []),
                stdout=stdout,
                tool_name=tool_name,
                command=command,
            ),
            tool_name=tool_name,
            agent_role=agent_role,
        )

    def snapshot(self) -> ArtifactLedgerSnapshot:
        return ArtifactLedgerSnapshot(artifacts=tuple(self._artifacts))

    def closure_text(self, *, locale: str = "zh") -> str:
        return artifact_closure_text(self.snapshot(), locale=locale)

    def handoff_block(self) -> str:
        return artifact_handoff_block(self.snapshot())


def rewrite_artifact_markdown(text: str, snapshot: ArtifactLedgerSnapshot) -> str:
    """Point relative markdown hrefs at ledger URLs. Longer names first."""
    if not text or not snapshot.artifacts:
        return text
    by_name: dict[str, str] = {}
    for art in snapshot.artifacts:
        if not art.url:
            continue
        by_name.setdefault(art.name, art.url)
        by_name.setdefault(PurePosixPath(art.name).name, art.url)
    rewritten = text
    for name in sorted(by_name, key=len, reverse=True):
        url = by_name[name]
        rewritten = re.sub(
            rf"\]\((?:\./)?{re.escape(name)}\)",
            f"]({url})",
            rewritten,
        )
    return rewritten


def artifact_closure_text(snapshot: ArtifactLedgerSnapshot, *, locale: str = "zh") -> str:
    """Download list. Inline image preview is the rewritten answer markdown."""
    if not snapshot.artifacts:
        return ""
    lines = ["已生成以下文件："] if locale.startswith("zh") else ["Generated files:"]
    for art in snapshot.artifacts:
        if art.url:
            lines.append(f"- [📥 {art.name}]({art.url})")
        else:
            lines.append(f"- **{art.name}**")
    return "\n".join(lines)


def _artifact_fallback_path(name: str) -> str:
    """Only the bound plane may invent a path. No cross-plane guess."""
    primary = current_primary()
    if primary is None:
        return name
    return join_under(primary.outputs_dir, name)


def artifact_handoff_block(snapshot: ArtifactLedgerSnapshot) -> str:
    """Structured block for pipeline member task injection."""
    if not snapshot.artifacts:
        return ""
    lines = ["[工作区已产出文件 — 可直接读取，勿猜测路径]"]
    for art in snapshot.artifacts:
        path = art.guest_path or _artifact_fallback_path(art.name)
        lines.append(f"- {art.name} → {path} ({art.mime_type})")
    return "\n".join(lines)
