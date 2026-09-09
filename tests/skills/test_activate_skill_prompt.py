"""activate_skill prompt 注入测试(ADR-0214 §7.4)。

3 fixture:
1. 激活后 prompt 包含 SKILL.md 内容
2. 激活后 prompt 包含 references 索引
3. 激活后 prompt 包含 "不要重复读" 文案(引导模型别反复 read_skill_reference_once)
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from lca.contracts.protocols.memory.operational_skills import SkillPackage
from lca.infrastructure.skills.bundled.bundled import ensure_bundled_skills
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.infrastructure.tools.skills.activate.tool import (
    SkillActivateTool,
    build_skill_references_section,
)


class TestActivateSkillPromptInjection(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))
        ensure_bundled_skills(self.store, root=Path("skills").resolve())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _activate(self, skill_id: str):
        tool = SkillActivateTool(self.store)
        return await tool.execute({"skill_id": skill_id})

    def test_activate_injects_skill_md_body(self) -> None:
        """激活后 prompt 必须包含 SKILL.md 正文。"""
        obs = asyncio.run(self._activate("create-assistant"))
        self.assertTrue(obs.success, obs.error)
        text = obs.payload["text"]
        # 关键段落
        self.assertIn("create-assistant", text)
        self.assertIn("create_assistant", text)

    def test_activate_injects_references_index(self) -> None:
        """激活后 prompt 包含 references 索引(ADR-0214 §7.4)。"""
        # editing-lca-compositions 声明了 2 个 references
        obs = asyncio.run(self._activate("editing-lca-compositions"))
        self.assertTrue(obs.success, obs.error)
        text = obs.payload["text"]
        # references 索引段必须存在
        self.assertIn("<skill_references", text)
        self.assertIn("resources/plane-decision.md", text)
        self.assertIn("resources/preset-schema.md", text)

    def test_activate_includes_no_redundant_read_message(self) -> None:
        """激活后 prompt 必须包含「不要重复读」文案,引导模型。

        PRD-§7.4 文案:read_skill_reference_once(path) 仅用于冷门子文档,
        不要重复读。本测试允许宽松匹配:含「不要」+「重复读」+ 「read_skill_reference_once」。
        """
        obs = asyncio.run(self._activate("editing-lca-compositions"))
        self.assertTrue(obs.success, obs.error)
        text = obs.payload["text"]
        self.assertIn("read_skill_reference_once", text)
        self.assertIn("不要", text)
        self.assertIn("重复", text)

    def test_activate_with_empty_references_declares_no_refs(self) -> None:
        """references: [] 的 skill 激活后必须显式说「无可用 references」。

        防止模型猜测 SKILL.md body 暗示的路径去 read_skill_reference_once。
        """
        obs = asyncio.run(self._activate("officecli"))
        self.assertTrue(obs.success, obs.error)
        text = obs.payload["text"]
        self.assertIn("<skill_references", text)
        self.assertIn("无可用 references", text)


class TestBuildSkillReferencesSection(unittest.TestCase):
    """单元测试 build_skill_references_section — 不走 store。"""

    def _pkg(self, references=(), version="1.0.0") -> SkillPackage:
        return SkillPackage(
            skill_id="t",
            name="t",
            summary="",
            content="body",
            resource_paths=references,
            source_url="",
            content_hash="h",
            version=version,
            references=references,
        )

    def test_with_references(self) -> None:
        section = build_skill_references_section(self._pkg(references=("r/a.md", "r/b.md")))
        self.assertIn("<skill_references", section)
        self.assertIn("- r/a.md", section)
        self.assertIn("- r/b.md", section)
        self.assertIn("不要重复读", section)

    def test_empty_references(self) -> None:
        section = build_skill_references_section(self._pkg(references=()))
        self.assertIn("<skill_references", section)
        self.assertIn("无可用 references", section)
        self.assertIn("read_skill_reference_once", section)


if __name__ == "__main__":
    unittest.main()
