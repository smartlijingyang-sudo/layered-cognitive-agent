"""PR-3/PR-9（ADR-0246）：静态断言 reflect 域不再有硬编码意图关键词表。

ADR-0244 P4 严禁在图节点硬编码意图正则；ADR-0246 用 LLM 蒸馏替代
``_SEMANTIC_DIRECTIVE_MARKERS``。本测试防止关键词表回归。
"""

from __future__ import annotations

import inspect
from pathlib import Path

from lca.nodes.reflect.memory_extract.memory_extract import ReflectMemoryExtractExecutor
from lca.nodes.reflect.score.score import ReflectScoreExecutor

_REFLECT_DIR = Path(__file__).resolve().parents[2] / "lca" / "nodes" / "reflect"


def test_no_semantic_directive_markers_symbol() -> None:
    """``_SEMANTIC_DIRECTIVE_MARKERS`` 必须不存在。"""
    import lca.nodes.reflect.score.score as score_module

    assert not hasattr(score_module, "_SEMANTIC_DIRECTIVE_MARKERS")
    assert not hasattr(score_module, "_extract_semantic_candidate")


def test_no_keyword_marker_tuple_in_reflect_sources() -> None:
    """reflect 目录下不得重新定义关键词表或关键词提取函数。"""
    for path in _REFLECT_DIR.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        source = path.read_text(encoding="utf-8")
        assert "_SEMANTIC_DIRECTIVE_MARKERS =" not in source, f"关键词表回归: {path}"
        assert "_extract_semantic_candidate(" not in source, f"关键词提取回归: {path}"


def test_extract_executor_has_no_keyword_regex() -> None:
    """``ReflectMemoryExtractExecutor`` 源码不含意图正则表。"""
    source = inspect.getsource(ReflectMemoryExtractExecutor)
    assert "DIRECTIVE_MARKERS" not in source


def test_score_executor_has_no_keyword_regex() -> None:
    """``ReflectScoreExecutor`` 源码不含意图正则表。"""
    source = inspect.getsource(ReflectScoreExecutor)
    assert "DIRECTIVE_MARKERS" not in source
    assert "记住" not in source
