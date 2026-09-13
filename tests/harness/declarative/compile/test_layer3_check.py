"""Layer-3 instrument markers — GraphAssembler retired (ADR-0221 P3).

``assert_all_instrumented`` / ``ExecutablePlan`` lived on the deleted
``GraphAssembler`` module. Production instrumentation now rides
``wrap_instrument`` on the v2 PlanInterpreter path. These tests pin the
wrap markers and assert the v0 assembler surface is unreachable.
"""

from __future__ import annotations

import pytest

from lca.harness.declarative.compile.instrument.wrap import (
    ASSEMBLER_PROVENANCE,
    WRAP_INSTRUMENTED_ATTR,
    wrap_executor,
    wrap_instrument,
)


class _BareExecutor:
    async def execute(self, context: object, phase_input: object) -> object:
        del context, phase_input
        return None


def test_wrap_instrument_marks_runnable() -> None:
    wrapped = wrap_instrument(_BareExecutor().execute, node_id="perceive.main")
    assert getattr(wrapped, WRAP_INSTRUMENTED_ATTR, False) is True
    assert getattr(wrapped, "wrap_provenance", None) == ASSEMBLER_PROVENANCE


def test_wrap_executor_marks_execute_closure() -> None:
    wrapped = wrap_executor(_BareExecutor())
    assert getattr(wrapped.execute, WRAP_INSTRUMENTED_ATTR, False) is True
    assert getattr(wrapped.execute, "wrap_provenance", None) == ASSEMBLER_PROVENANCE


def test_graph_assembler_module_unreachable() -> None:
    with pytest.raises(ModuleNotFoundError):
        __import__("lca.harness.declarative.compile.assembler.assembler")


def test_graph_assembler_package_export_fail_loud() -> None:
    import lca.harness.declarative as declarative

    with pytest.raises(AttributeError, match="GraphAssembler"):
        _ = declarative.GraphAssembler
