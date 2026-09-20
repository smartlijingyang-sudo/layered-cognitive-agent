"""HttpSkillImporter 裸 SKILL.md 导入：缺 references 时自动注入（ADR-0247 流程测试补强）。

``create_assistant_skill(source_url=...)`` 与 ``import_skill`` 的 URL 路径共用
``HttpSkillImporter``。裸 SKILL.md 常缺省 ADR-0214 要求的 ``references`` 字段，
导入器应注入 ``references: []`` 使安装顺畅，而不是让 agent 手工补救。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

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

    async def test_bare_markdown_without_references_gets_injected(self) -> None:
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
        assert "references: []" in text
        assert text.startswith("---\nreferences: []\n")

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

    async def test_local_store_install_accepts_injected_references(self) -> None:
        skill_md = "---\nname: docx\ndescription: x\n---\n# body"
        with patch.object(self.importer, "_fetch_text", AsyncMock(return_value=skill_md)):
            pkg = await self.importer.import_from_url("https://example.com/SKILL.md", kind="url")
        assert pkg.skill_id == "docx"
        manifest_path = Path(self._tmp.name) / "docx" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["references"] == []
