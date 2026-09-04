"""persona_from_home tests（助理人设 → RoleProfile 三元组）。

覆盖：完整 Home ⇒ role/goal/backstory 收敛；文件缺失 ⇒ 空字段降级；
backstory 截断上限。
"""

from __future__ import annotations

from pathlib import Path

from lca.plugins.assistant._home_layout import render_template, write_home_files
from lca.plugins.assistant.persona import persona_from_home


def _materialize(home: Path, template_id: str = "assistant.research") -> None:
    rendered = render_template(template_id, name="小研", description="深度研究")
    write_home_files(home, rendered.files)


class TestPersonaFromHome:
    def test_full_home_resolves_persona(self, tmp_path: Path) -> None:
        home = tmp_path / "asst_x"
        _materialize(home)
        persona = persona_from_home(str(home))
        assert persona.role == "小研"
        assert persona.goal == "深度研究"
        assert "研究助理" in persona.backstory
        assert "USER" in persona.backstory

    def test_missing_home_degrades_to_empty(self, tmp_path: Path) -> None:
        persona = persona_from_home(str(tmp_path / "nope"))
        assert persona.role == ""
        assert persona.goal == ""
        assert persona.backstory == ""

    def test_backstory_truncated(self, tmp_path: Path) -> None:
        home = tmp_path / "asst_big"
        _materialize(home)
        (home / "SOUL.md").write_text("字" * 8000, encoding="utf-8")
        persona = persona_from_home(str(home))
        assert len(persona.backstory) <= 3000

    def test_goal_falls_back_to_first_goal_name(self, tmp_path: Path) -> None:
        home = tmp_path / "asst_nongoal"
        _materialize(home)
        (home / "profile.json").write_text(
            '{"name": "小研", "description": "", "emoji": "🔍", "status": "active"}',
            encoding="utf-8",
        )
        persona = persona_from_home(str(home))
        assert persona.goal == "深度研究"  # goals.yaml 第一个 goal 的 name
