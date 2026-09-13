"""Layer-3 wrap_instrument contract — GraphAssembler retired.

The PR-4 spine mandate still requires ``__lca_instrumented__`` markers on
wrapped runnables. GraphAssembler.assemble used to be the production wrap
site; after ADR-0221 P3 the v2 PlanInterpreter / instrument wrap path owns
that duty. These tests pin wrap_instrument semantics and assert the v0
assembler is unreachable.
"""

from __future__ import annotations

import pytest

from lca.harness.declarative.compile.instrument.wrap import (
    ASSEMBLER_PROVENANCE,
    WRAP_INSTRUMENTED_ATTR,
    wrap_instrument,
)


async def _bare_runnable() -> None:
    return None


def test_wrap_instrument_sets_layer3_markers() -> None:
    wrapped = wrap_instrument(_bare_runnable, node_id="perceive.main")
    assert getattr(wrapped, WRAP_INSTRUMENTED_ATTR, False) is True
    assert getattr(wrapped, "wrap_provenance", None) == ASSEMBLER_PROVENANCE


def test_graph_assembler_module_unreachable() -> None:
    with pytest.raises(ModuleNotFoundError):
        __import__("lca.harness.declarative.compile.assembler.assembler")


def test_graph_assembler_export_fail_loud() -> None:
    import lca.harness.declarative as declarative

    with pytest.raises(AttributeError, match="GraphAssembler"):
        _ = declarative.GraphAssembler
