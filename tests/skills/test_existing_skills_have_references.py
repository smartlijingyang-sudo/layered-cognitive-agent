"""全扫 ``skills/*/SKILL.md``, 断言全部含 ``references:`` 字段(ADR-0214 §7)。

这条测试**同 PR 落**, 防止后续 PR 又引入缺 references 的 SKILL.md。
任何新增 skill 必须显式声明 ``references: []`` 或实际路径清单。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


class TestAllBundledSkillsHaveReferencesField(unittest.TestCase):
    def test_every_skill_md_has_references_field(self) -> None:
        """``skills/<id>/SKILL.md`` 必须含 ``references:`` 字段。"""
        self.assertTrue(_SKILLS_DIR.is_dir(), f"missing skills dir: {_SKILLS_DIR}")
        skill_mds = sorted(_SKILLS_DIR.glob("*/SKILL.md"))
        self.assertGreater(len(skill_mds), 0, f"no SKILL.md found under {_SKILLS_DIR}")
        # 允许 inline list 写法或 YAML 多行 list 写法。
        # 多行列表 key 行是 ``references:``(无 inline value),
        # 内联写法 key 行是 ``references: [...]``。
        pattern = re.compile(r"^\s*references\s*:", re.MULTILINE)
        for path in skill_mds:
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text,
                pattern,
                msg=(
                    f"{path.relative_to(_SKILLS_DIR)} frontmatter 缺 'references:' 字段。"
                    " 在 --- 之间加 'references: []'(空清单)或 'references: [path1, path2]'。"
                ),
            )


if __name__ == "__main__":
    unittest.main()
