"""Node-level EP dispatcher tests (ADR-0217 §3.3.2, PG-006/PG-007).

Four cases:

1. ``emit_for_node`` dispatches a known EP to its bound
   ``cognitive_emit`` function.
2. ``emit_for_node`` silently ignores unknown EP ids (the driver does
   not maintain the EP vocabulary).
3. ``NodeGraphDriver._execute_with_emits`` fires ``emit_on_enter`` and
   ``emit_on_exit`` EPs on success.
4. ``NodeGraphDriver._execute_with_emits`` fires
   ``reasoner_reason_end`` with ``outcome="failure"`` on exception and
   re-raises so the existing failure path produces a FAILED outcome.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeInput,
    NodeOutput,
)
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver
from lca.loop.emit.node_emitter import (
    emit_for_node,
)


def _state() -> AgentState:
    return AgentState(trace_id="trace:node-emit", task="test", budget=Budget())


def _spec(config: dict[str, object]) -> BundleGraphSpec:
    return BundleGraphSpec(
        id="unit.emit.spec",
        region="phase:think",
        purpose="unit",
        nodes=(
            BundleGraphNode(
                id="emit.node",
                region="phase:think",
                factory="unit.factory",
                purpose="",
                inputs=(),
                outputs=(),
                config=config,
            ),
        ),
        edges=(),
        entry="emit.node",
    )


def _driver(config: dict[str, object]) -> NodeGraphDriver:
    return NodeGraphDriver(
        spec=_spec(config),
        plan_ref="bundles/emit-test.yaml",
        scope=SimpleNamespace(resolve_factory=lambda *a, **k: SimpleNamespace()),
    )


class TestEmitForNodeDispatch:
    """``emit_for_node`` routes known EP ids to bound helpers."""

    def test_emit_for_node_routes_known_ep(self) -> None:
        state = _state()
        from lca.loop.emit import node_emitter

        def fake_target(s: AgentState) -> None:
            fake_target.calls.append(s)

        fake_target.calls = []
        with patch.dict(
            node_emitter._EP_DISPATCH,
            {"prompt_assembler_start": fake_target},
        ):
            emit_for_node("prompt_assembler_start", state)
        assert fake_target.calls == [state]

    def test_emit_for_node_unknown_ep_silent(self) -> None:
        """Unknown ``ep_id`` (not in ``_EP_DISPATCH``) is silently ignored.

        The driver does not own the EP vocabulary — the
        ``EXECUTION_POINTS`` whitelist does. Dispatcher must not raise
        on a misspelled EP; the registry-style lookup yields ``None``
        and the function returns without dispatching.
        """
        state = _state()
        from lca.loop.emit import node_emitter

        def fake_target(s: AgentState) -> None:
            fake_target.calls.append(s)

        fake_target.calls = []
        with patch.dict(
            node_emitter._EP_DISPATCH,
            {"prompt_assembler_start": fake_target},
        ):
            emit_for_node("definitely_not_an_ep", state)
        assert fake_target.calls == []


class TestExecuteWithEmits:
    """``NodeGraphDriver._execute_with_emits`` wraps executor with EP dispatch."""

    @pytest.mark.asyncio
    async def test_success_path_emits_enter_and_exit(self) -> None:
        """On success, ``emit_on_enter`` fires before executor, then
        ``emit_on_exit`` fires after — both routed through
        ``emit_for_node``.
        """
        driver = _driver(
            config={
                "emit_on_enter": ["reasoner_reason_start"],
                "emit_on_exit": ["reasoner_reason_end"],
            }
        )
        executor = SimpleNamespace()

        async def fake_node_execute(_ctx: object, _input: object) -> NodeOutput:
            return NodeOutput(port_values={})

        executor.node_execute = fake_node_execute  # type: ignore[attr-defined]
        ctx = SimpleNamespace()
        node_input = NodeInput(port_values={})
        node = driver._spec.nodes[0]
        state = _state()

        with patch(
            "lca.framework.subgraph.plugins.node_graph_driver.emit_for_node",
            autospec=True,
        ) as emit:
            out = await driver._execute_with_emits(
                executor=executor,
                ctx=ctx,
                node_input=node_input,
                node=node,
                state=state,
            )

        assert isinstance(out, NodeOutput)
        # enter fires before exit; reasoner_reason_start then reasoner_reason_end
        assert [call.args[0] for call in emit.call_args_list] == [
            "reasoner_reason_start",
            "reasoner_reason_end",
        ]

    @pytest.mark.asyncio
    async def test_exception_path_emits_reasoner_reason_end_failure(self) -> None:
        """On exception, ``reasoner_reason_end`` is emitted with
        ``outcome="failure"`` (other exit EPs are not auto-emitted) and
        the exception is re-raised so the existing FAILED
        ``InterpretationResult`` path takes over.
        """
        driver = _driver(
            config={
                "emit_on_enter": ["reasoner_reason_start"],
                "emit_on_exit": [
                    "reasoner_reason_end",
                    "prompt_assembler_end",
                ],
            }
        )
        executor = SimpleNamespace()

        async def boom(_ctx: object, _input: object) -> NodeOutput:
            raise RuntimeError("executor crashed")

        executor.node_execute = boom  # type: ignore[attr-defined]
        node_input = NodeInput(port_values={})
        node = driver._spec.nodes[0]
        state = _state()

        with (
            patch(
                "lca.framework.subgraph.plugins.node_graph_driver.emit_for_node",
                autospec=True,
            ) as emit,
            pytest.raises(RuntimeError, match="executor crashed"),
        ):
            await driver._execute_with_emits(
                executor=executor,
                ctx=SimpleNamespace(),
                node_input=node_input,
                node=node,
                state=state,
            )

        # enter fires; on failure only reasoner_reason_end fires with
        # outcome="failure" — prompt_assembler_end is intentionally not
        # auto-emitted (other EP semantics on failure are executor-owned).
        ep_calls = [(call.args[0], call.kwargs.get("outcome")) for call in emit.call_args_list]
        assert ep_calls[0] == ("reasoner_reason_start", None)
        assert ep_calls[1] == ("reasoner_reason_end", "failure")
