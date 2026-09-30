"""assistant.skill_overlay 拆分后的 gating / receipts 聚焦测试。

经 barrel(``lca.plugins.assistant.skill.overlay``)直接验证:

- ``_gate_package`` —— ADR-0067 三闸各失败分支 + ``DRAFT → VERIFIED``;
- ``_receipt_from_disk`` —— 有/无 manifest 索引、digest 兜底的回执重建;
- ``_ACTIVATABLE_STATES`` —— activate 状态闭集(ADR-0187 §3 D6)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.atoms.artifact.state import ArtifactState
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.protocols.memory.operational_skills import (
    SKILL_MAX_CONTENT_CHARS,
    SKILL_MAX_RESOURCES,
    SkillImportError,
    SkillPackage,
)
from lca.plugins.assistant.skill.overlay import (
    _ACTIVATABLE_STATES,
    _gate_package,
    _receipt_from_disk,
)


def _make_package(**overrides: object) -> SkillPackage:
    base: dict[str, object] = {
        "skill_id": "demo-skill",
        "name": "demo",
        "summary": "demo package",
        "content": "---\nname: demo-skill\ndescription: d\n---\nbody",
        "resource_paths": ("resources/reference.md",),
        "source_url": "https://example.com/skill.md",
        "content_hash": "abc123",
    }
    base.update(overrides)
    return SkillPackage(**base)  # type: ignore[arg-type]


class TestGatePackage:
    def test_valid_package_promotes_to_verified(self) -> None:
        artifact = _gate_package(_make_package())
        assert artifact.state is ArtifactState.VERIFIED
        assert artifact.logical_id == "assistant.skill:demo-skill"
        assert artifact.scope is Scope.AGENT

    def test_invalid_skill_id_rejected(self) -> None:
        with pytest.raises(SkillImportError, match="identity 闸"):
            _gate_package(_make_package(skill_id="Bad Skill!"))

    def test_missing_content_hash_rejected(self) -> None:
        with pytest.raises(SkillImportError, match="内容 digest"):
            _gate_package(_make_package(content_hash=""))

    def test_missing_source_url_rejected(self) -> None:
        with pytest.raises(SkillImportError, match="安装来源"):
            _gate_package(_make_package(source_url=""))

    def test_content_over_limit_rejected(self) -> None:
        with pytest.raises(SkillImportError, match=r"SKILL\.md 超过上限"):
            _gate_package(_make_package(content="x" * (SKILL_MAX_CONTENT_CHARS + 1)))

    def test_too_many_resources_rejected(self) -> None:
        with pytest.raises(SkillImportError, match="资源数超过上限"):
            _gate_package(
                _make_package(
                    resource_paths=tuple(f"r/{i}.md" for i in range(SKILL_MAX_RESOURCES + 1))
                )
            )

    def test_invalid_resource_path_rejected(self) -> None:
        with pytest.raises(SkillImportError, match="资源路径非法"):
            _gate_package(_make_package(resource_paths=("../evil.md",)))


class TestReceiptFromDisk:
    def _write_store_manifest(self, skill_dir: Path, data: dict[str, object]) -> None:
        skill_dir.mkdir(parents=True)
        (skill_dir / "manifest.json").write_text(json.dumps(data), encoding="utf-8")

    def test_with_manifest_entry_uses_index_values(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "demo-skill"
        self._write_store_manifest(skill_dir, {"content_hash": "ignored"})
        receipt = _receipt_from_disk(
            skill_dir,
            {
                "artifact_state": "verified",
                "digest": "sha256:entry-digest",
                "installed_at": "2026-01-01T00:00:00Z",
                "actor": "user:test",
                "source": "local",
                "version": "1.2.3",
            },
            assistant_id="asst_1",
            revision_seq=3,
            manifest_digest="sha256:manifest",
        )
        assert receipt.artifact_state == "verified"
        assert receipt.digest == "sha256:entry-digest"
        assert receipt.installed_at == "2026-01-01T00:00:00Z"
        assert receipt.actor == "user:test"
        assert receipt.source == "local"
        assert receipt.version == "1.2.3"
        assert receipt.revision_seq == 3
        assert receipt.manifest_digest == "sha256:manifest"
        assert receipt.install_path == str(skill_dir)

    def test_without_entry_falls_back_to_draft_store_manifest(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "manual-skill"
        self._write_store_manifest(
            skill_dir,
            {"content_hash": "deadbeef", "source_url": "https://x/s.md", "version": "2.0.0"},
        )
        receipt = _receipt_from_disk(
            skill_dir,
            None,
            assistant_id="asst_1",
            revision_seq=0,
            manifest_digest="sha256:manifest",
        )
        assert receipt.artifact_state == ArtifactState.DRAFT.value
        assert receipt.digest == "sha256:deadbeef"
        assert receipt.source == "https://x/s.md"
        assert receipt.version == "2.0.0"
        assert receipt.actor == "system"

    def test_without_any_digest_uses_unknown(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bare-skill"
        self._write_store_manifest(skill_dir, {})
        receipt = _receipt_from_disk(
            skill_dir,
            None,
            assistant_id="asst_1",
            revision_seq=0,
            manifest_digest="sha256:manifest",
        )
        assert receipt.artifact_state == ArtifactState.DRAFT.value
        assert receipt.digest == "sha256:unknown"


class TestActivatablestatesThroughBarrel:
    def test_allowlist_is_closed(self) -> None:
        assert frozenset({"verified", "active"}) == _ACTIVATABLE_STATES
