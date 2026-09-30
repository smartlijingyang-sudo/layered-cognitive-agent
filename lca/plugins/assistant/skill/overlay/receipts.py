"""assistant.skill_overlay —— 从磁盘重建安装回执。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.contracts.atoms.artifact.state import ArtifactState
from lca.contracts.protocols.assistant.skill_overlay import SkillInstallReceipt


def _receipt_from_disk(
    skill_dir: Path,
    entry: Mapping[str, Any] | None,
    *,
    assistant_id: str,
    revision_seq: int,
    manifest_digest: str,
) -> SkillInstallReceipt:
    """从 ``{home}/skills/<skill_id>/`` 重建回执。

    ``entry`` = Home manifest skills 索引记录;缺失(手动落盘)⇒
    ``artifact_state="draft"`` —— 可见但不可 activate(fail-closed)。
    """
    store_manifest: dict[str, Any] = {}
    store_manifest_path = skill_dir / "manifest.json"
    if store_manifest_path.is_file():
        try:
            loaded = json.loads(store_manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                store_manifest = loaded
        except (OSError, ValueError):
            store_manifest = {}

    if entry is not None:
        state = str(entry.get("artifact_state") or "draft")
        digest = str(entry.get("digest") or "")
        installed_at = str(entry.get("installed_at") or "")
        actor = str(entry.get("actor") or "system")
        source = str(entry.get("source") or "")
        version = str(entry.get("version") or "")
    else:
        state = ArtifactState.DRAFT.value
        digest = ""
        installed_at = str(store_manifest.get("imported_at") or "")
        actor = "system"
        source = str(store_manifest.get("source_url") or "")
        version = str(store_manifest.get("version") or "")
    if not digest:
        content_hash = str(store_manifest.get("content_hash") or "")
        digest = f"sha256:{content_hash}" if content_hash else "sha256:unknown"
    return SkillInstallReceipt(
        assistant_id=assistant_id,
        skill_id=skill_dir.name,
        version=version,
        digest=digest,
        artifact_state=state,
        installed_at=installed_at,
        revision_seq=revision_seq,
        manifest_digest=manifest_digest,
        actor=actor,
        source=source,
        install_path=str(skill_dir),
    )
