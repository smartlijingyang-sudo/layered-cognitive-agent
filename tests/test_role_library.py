"""gateway role_library 单元测试（ADR-0042）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gateway.role_library import AGENCY_ROLES_DIR_ENV, FileRoleLibrary, resolve_roles_dir
from lca.contracts.protocols.casting import CastingError, RoleNotFoundError

_CARD_TEMPLATE = """---
name: {name}
description: {desc}
emoji: 🧪
---

# {name}

{name} 的角色卡正文。
"""


def _write_card(root: Path, rel: str, name: str, desc: str) -> None:
    path = root / f"{rel}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CARD_TEMPLATE.format(name=name, desc=desc), encoding="utf-8")


class TestFileRoleLibrary(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write_card(self.root, "product/pm", "产品经理", "需求分析与方案设计")
        _write_card(self.root, "strategy/lead", "项目总监", "统筹与收口")
        # 无 frontmatter 的 md 必须被跳过（README 等）
        (self.root / "README.md").write_text("# 说明文档\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_index_sorted_and_non_role_md_skipped(self) -> None:
        library = FileRoleLibrary(self.root)
        self.assertEqual(
            [entry.role_id for entry in library.index()],
            ["product/pm", "strategy/lead"],
        )

    def test_get_returns_full_card(self) -> None:
        card = FileRoleLibrary(self.root).get("product/pm")
        self.assertEqual(card.title, "产品经理")
        self.assertEqual(card.department, "product")
        self.assertEqual(card.summary, "需求分析与方案设计")
        self.assertIn("角色卡正文", card.backstory)

    def test_get_unknown_role_raises(self) -> None:
        with self.assertRaises(RoleNotFoundError):
            FileRoleLibrary(self.root).get("ghost/role")

    def test_missing_dir_raises_casting_error(self) -> None:
        with self.assertRaises(CastingError):
            FileRoleLibrary(self.root / "not-there")

    def test_empty_dir_raises_casting_error(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(CastingError):
            FileRoleLibrary(empty)

    def test_env_var_overrides_roles_dir(self) -> None:
        with mock.patch.dict(os.environ, {AGENCY_ROLES_DIR_ENV: str(self.root)}):
            self.assertEqual(resolve_roles_dir(), self.root)
            self.assertEqual(len(FileRoleLibrary().index()), 2)

    def test_repo_default_library_ships_real_roles(self) -> None:
        library = FileRoleLibrary()  # 仓库内置 roles/（agency-agents-zh）
        self.assertGreaterEqual(len(library.index()), 200)
        role_ids = {entry.role_id for entry in library.index()}
        self.assertIn("design/design-ux-researcher", role_ids)
        self.assertIn("product/product-manager", role_ids)


if __name__ == "__main__":
    unittest.main()
