"""HttpSkillImporter 裸 SKILL.md 导入：缺 references 时显式声明并记录（RA-077）。

``create_assistant_skill(source_url=...)`` 与 ``import_skill`` 的 URL 路径共用
``HttpSkillImporter``。裸 SKILL.md 常缺省 ADR-0214 要求的 ``references`` 字段；
导入器不再做字节手术补 ``references: []``（pulled bytes 保持原样），而是把
``assume_empty_references=True`` 显式传给 ``install_package``，由安装方声明空
列表并记录在 manifest 的 ``references_assumed_empty``。本地安装路径缺字段仍
fail-loud —— 两条安装路径语义一致且有据可查。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from lca.contracts.protocols.memory.operational_skills import SkillContractError
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.http.importer import HttpSkillImporter
from lca.infrastructure.skills.settings.settings import SkillSettings


class _RecordingStore:
    """记录 ``install_package`` 参数的 fake store。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def install_package(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return object()


class TestHttpImporterReferences(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._settings = SkillSettings(
            cache_dir=Path(self._tmp.name),
            allowed_hosts=("example.com",),
        )
        self.store = DiskSkillPackageStore(self._settings)
        self.importer = HttpSkillImporter(store=self.store, settings=self._settings)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_bare_markdown_keeps_pulled_bytes_and_passes_explicit_flag(self) -> None:
        """RA-077: 缺 references 的裸 SKILL.md —— 字节不动，显式参数接管。"""
        recorder = _RecordingStore()
        importer = HttpSkillImporter(
            store=recorder,  # type: ignore[arg-type]
            settings=self._settings,
        )
        skill_md = "---\nname: docx\ndescription: docx skill\n---\n# body"
        with patch.object(importer, "_fetch_text", AsyncMock(return_value=skill_md)):
            await importer.import_from_url("https://example.com/SKILL.md", kind="url")

        assert len(recorder.calls) == 1
        text = str(recorder.calls[0]["skill_md_text"])
        assert text == skill_md  # pulled bytes 保持原样，不再做字节手术
        assert recorder.calls[0]["assume_empty_references"] is True

    async def test_markdown_with_references_passes_through(self) -> None:
        recorder = _RecordingStore()
        importer = HttpSkillImporter(
            store=recorder,  # type: ignore[arg-type]
            settings=self._settings,
        )
        skill_md = "---\nname: docx\nreferences:\n  - resources/x.py\ndescription: x\n---\n# body"
        with patch.object(importer, "_fetch_text", AsyncMock(return_value=skill_md)):
            await importer.import_from_url("https://example.com/SKILL.md", kind="url")

        assert len(recorder.calls) == 1
        text = str(recorder.calls[0]["skill_md_text"])
        assert text == skill_md

    async def test_url_import_records_assumed_empty_references(self) -> None:
        """RA-077 pin: URL 导入缺 references —— 安装成功 + manifest 记录代声明。"""
        skill_md = "---\nname: docx\ndescription: x\n---\n# body"
        with patch.object(self.importer, "_fetch_text", AsyncMock(return_value=skill_md)):
            pkg = await self.importer.import_from_url("https://example.com/SKILL.md", kind="url")
        assert pkg.skill_id == "docx"
        assert pkg.references == ()
        assert pkg.references_assumed_empty is True
        manifest_path = Path(self._tmp.name) / "docx" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["references"] == []
        assert manifest["references_assumed_empty"] is True
        # content_hash 按原始字节算 —— 手术前的文本哈希即安装哈希
        assert manifest["content_hash"] == pkg.content_hash

    def test_direct_install_without_flag_still_fails_loud(self) -> None:
        """RA-077: 本地安装路径缺 references 仍 fail-loud（两条路径语义一致）。"""
        with pytest.raises(SkillContractError, match="缺 'references' 字段"):
            self.store.install_package(
                skill_id="local-docx",
                skill_md_text="---\nname: local-docx\ndescription: x\n---\n# body",
                resource_files={},
                source_url="local",
            )

    def test_direct_install_with_flag_records_assumption(self) -> None:
        pkg = self.store.install_package(
            skill_id="flagged",
            skill_md_text="---\nname: flagged\ndescription: x\n---\n# body",
            resource_files={},
            source_url="local",
            assume_empty_references=True,
        )
        assert pkg.references == ()
        assert pkg.references_assumed_empty is True
        # get() 回读同样带记录
        reread = self.store.get("flagged")
        assert reread.references_assumed_empty is True
