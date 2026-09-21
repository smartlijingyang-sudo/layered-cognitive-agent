"""Cloud sandbox role tells the truth about CJK. It does not name missing fonts."""

from __future__ import annotations

from lca.infrastructure.runtime_plane.prompt.assembler import render_plane_prompt
from lca.infrastructure.tools.lca_computer.apis.execute.code import DESCRIPTION


def test_sandbox_role_does_not_advertise_missing_matplotlib_families() -> None:
    text = render_plane_prompt(())
    assert "font.sans-serif" in text
    assert "WenQuanYi Zen Hei" not in text
    assert "Noto Sans CJK" not in text
    assert "fc-list" in text


def test_execute_code_schema_says_fresh_interpreter() -> None:
    assert "新的解释器" in DESCRIPTION
    assert "font.sans-serif" in DESCRIPTION
