"""SKILL.md frontmatter `references` 必填契约(ADR-0214 §7.1).

加载期 fail-loud:
1. SKILL.md 缺 ``references`` 字段 → SkillContractError
2. ``references`` 路径不存在 → SkillContractError
3. ``references`` 路径存在 → 加载成功
4. 加载后 ``skill.references`` == frontmatter 列表
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.contracts.protocols.memory.operational_skills import SkillContractError
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings


class TestSkillLoadingReferencesContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_references_field_raises(self) -> None:
        """SKILL.md 缺 references 字段必须 fail-loud(ADR-0214 §7.2)。"""
        with self.assertRaises(SkillContractError) as ctx:
            self.store.install_package(
                skill_id="no-refs",
                skill_md_text="---\nname: no-refs\ndescription: d\n---\nbody",
                resource_files={},
                source_url="u",
            )
        msg = str(ctx.exception)
        self.assertIn("references", msg)
        self.assertIn("no-refs", msg)

    def test_empty_references_field_is_accepted(self) -> None:
        """``references: []`` 占位是允许的(可空清单)。"""
        pkg = self.store.install_package(
            skill_id="empty-refs",
            skill_md_text="---\nname: empty-refs\ndescription: d\nreferences: []\n---\nbody",
            resource_files={},
            source_url="u",
        )
        self.assertEqual(pkg.references, ())

    def test_inline_references_list_loads(self) -> None:
        # references 路径包括 ``resources/`` 前缀(包内布局约定)
        pkg = self.store.install_package(
            skill_id="inline-refs",
            skill_md_text=(
                "---\nname: inline-refs\ndescription: d\n"
                "references: [resources/a.md, resources/b.md]\n---\nbody"
            ),
            resource_files={"a.md": b"aaa", "b.md": b"bbb"},
            source_url="u",
        )
        self.assertEqual(pkg.references, ("resources/a.md", "resources/b.md"))

    def test_multiline_references_list_loads(self) -> None:
        pkg = self.store.install_package(
            skill_id="multi-refs",
            skill_md_text=(
                "---\nname: multi-refs\ndescription: d\nreferences:\n"
                "  - resources/a.md\n  - resources/b.md\n---\nbody"
            ),
            resource_files={"a.md": b"aaa", "b.md": b"bbb"},
            source_url="u",
        )
        self.assertEqual(pkg.references, ("resources/a.md", "resources/b.md"))

    def test_references_pointing_to_missing_file_raises(self) -> None:
        with self.assertRaises(SkillContractError) as ctx:
            self.store.install_package(
                skill_id="missing-ref",
                skill_md_text=(
                    "---\nname: missing-ref\ndescription: d\n"
                    "references: [resources/missing.md]\n---\nbody"
                ),
                resource_files={"a.md": b"aaa"},
                source_url="u",
            )
        msg = str(ctx.exception)
        self.assertIn("resources/missing.md", msg)
        self.assertIn("缺失", msg)

    def test_references_path_traversal_raises(self) -> None:
        """references 路径越界(escape 到包外)→ fail-loud。"""
        with self.assertRaises(SkillContractError) as ctx:
            self.store.install_package(
                skill_id="evil-ref",
                skill_md_text=(
                    "---\nname: evil-ref\ndescription: d\nreferences: [../escape.md]\n---\nbody"
                ),
                resource_files={},
                source_url="u",
            )
        msg = str(ctx.exception)
        self.assertIn("越界", msg)

    def test_references_persisted_in_manifest_and_get(self) -> None:
        """install 后 get 返回的 SkillPackage.references 必须 == frontmatter。"""
        self.store.install_package(
            skill_id="roundtrip",
            skill_md_text=(
                "---\nname: roundtrip\ndescription: d\nreferences: [resources/a.md]\n---\nbody"
            ),
            resource_files={"a.md": b"aaa"},
            source_url="u",
        )
        loaded = self.store.get("roundtrip")
        self.assertEqual(loaded.references, ("resources/a.md",))


if __name__ == "__main__":
    unittest.main()
