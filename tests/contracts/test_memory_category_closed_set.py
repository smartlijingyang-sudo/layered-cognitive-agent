"""PR-1（ADR-0246）：``MemoryCategory`` 闭集测试。

记忆类别是知识层的闭集分类；新增类别必须同步 whitelist/文档（C11 事件闭集
同类纪律）。
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory


def test_memory_category_closed_set_exact_members() -> None:
    """闭集成员精确等于 ADR-0246 §3.1 定义的五个类别。"""
    assert set(MemoryCategory) == {
        MemoryCategory.IDENTITY,
        MemoryCategory.PREFERENCE,
        MemoryCategory.FACT,
        MemoryCategory.EPISODIC,
        MemoryCategory.PROCEDURAL,
    }


def test_memory_category_values_are_snake_case() -> None:
    """值必须与文档一致（identity/preference/fact/episodic/procedural）。"""
    assert MemoryCategory.IDENTITY.value == "identity"
    assert MemoryCategory.PREFERENCE.value == "preference"
    assert MemoryCategory.FACT.value == "fact"
    assert MemoryCategory.EPISODIC.value == "episodic"
    assert MemoryCategory.PROCEDURAL.value == "procedural"


def test_memory_category_is_str_enum() -> None:
    """类别可安全地序列化为字符串并回读。"""
    assert MemoryCategory("identity") is MemoryCategory.IDENTITY
    assert MemoryCategory("preference") is MemoryCategory.PREFERENCE
