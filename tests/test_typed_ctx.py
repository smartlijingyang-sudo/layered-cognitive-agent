"""TypedContext Protocol — typed property accessor for cordis Context."""
from __future__ import annotations

from lca.contracts.typed_ctx import TypedContext


def test_typed_context_exposes_llm_property():
    """TypedContext declares llm property typed as LLMAdapter Protocol."""
    assert hasattr(TypedContext, "llm")
    assert isinstance(TypedContext.llm, property)


def test_typed_context_imports_cleanly():
    """TypedContext is importable (no circular imports)."""
    assert TypedContext is not None
