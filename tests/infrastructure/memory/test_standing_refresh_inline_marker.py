"""Regression: inline standing markers must be recognized, not duplicated.

The persona ``backstory`` block arrives as ``BACKSTORY: <soul>`` with the
SOUL.md injection marker on the same line as the ``BACKSTORY:`` label.
``refresh_injected`` only matched markers at the start of a line, so this
block was treated as foreign text and SOUL.md was appended a second time at
the end of the system prompt (seen in ``run_f213fbb77a2d``). Inline markers
must be found anywhere in a line.
"""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.domain.standing import refresh_injected

_FILES = [
    ("SOUL.md", "我是人格文件"),
    ("USER.md", "用户画像"),
]

_TEXT = (
    "BACKSTORY: <!-- INJECTED FILE: SOUL.md -->\n"
    "我是人格文件\n"
    "<!-- END INJECTED FILE: SOUL.md -->\n"
    "\n"
    "ROLE: x\n"
    "<!-- INJECTED FILE: USER.md -->\n"
    "用户画像\n"
    "<!-- END INJECTED FILE: USER.md -->"
)


def test_inline_marker_is_replaced_without_appending_duplicate() -> None:
    out = refresh_injected(_TEXT, _FILES)
    assert out.count("我是人格文件") == 1
    assert out.count("<!-- INJECTED FILE: SOUL.md -->") == 1
    assert "我是人格文件" in out
    assert "用户画像" in out