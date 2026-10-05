"""`trail_lines` 是「什么算一行流水」的唯一 owner。

`_documents` 与 `parse_trail` 都要把流水文件拆成行。两份拆法一旦分叉，索引里的
文档与 dream 提升出的事实就不再对应同一批行，而两边都不会报错。收敛证明是这两个
函数对同一份文本必须逐项给出相同的内容序列。
"""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.domain.trail import parse_trail, trail_lines

_MIXED = """# 2026-10-05

- 还是简洁一点好
<!-- 内部注释，不是证据 -->

- 以后不要用 emoji
普通段落不是 bullet
"""


def test_only_bullet_lines_are_evidence() -> None:
    assert trail_lines(_MIXED) == ("还是简洁一点好", "以后不要用 emoji")


def test_headings_blanks_and_comments_are_skipped() -> None:
    text = "# 2026-10-05\n\n<!-- c -->\n-   \n- 有效行\n"

    assert trail_lines(text) == ("有效行",)


def test_empty_text_yields_nothing() -> None:
    assert trail_lines("") == ()
    assert trail_lines("# 2026-10-05\n\n") == ()


def test_converges_with_parse_trail() -> None:
    """收敛证明：两个消费方不会对同一份文本给出不同的行集合。"""
    entries = parse_trail(_MIXED, source="2026-10-05", observed_at_ms=0)

    assert trail_lines(_MIXED) == tuple(entry.content for entry in entries)


def test_a_multiline_bullet_keeps_only_its_first_line() -> None:
    """钉住既有行为。

    `_BULLET` 只匹配以 `- ` 开头的行，续行被丢弃。生产上 cron handoff 文本正是
    这个形状，标题行进流水而报告正文不进。
    """
    text = "- [cron handoff] job_id=j1 report=always\n任务标题：验证提醒\nworker 报告：\n内容\n"

    assert trail_lines(text) == ("[cron handoff] job_id=j1 report=always",)


def test_content_is_stripped() -> None:
    assert trail_lines("-   带空白的行   \n") == ("带空白的行",)
