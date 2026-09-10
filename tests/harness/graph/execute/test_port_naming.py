"""Port passthrough for inner→outer subgraph termination (ADR-0217 §3.3.3).

Three iron rules the :meth:`PortContext.exit_subgraph` seam enforces:

1. Iron rule 1 — port passthrough: inner_graph 终止端口名 ∈ outer
   节点 ``outputs`` → 透传到 outer PortContext.
2. Iron rule 2 — missing input == empty NodeOutput: inner_graph
   没产生某个 outer 端口名时,outer 拿到空 dict(由 ``build_input``
   缺省填空处理)。
3. Iron rule 4 — inner_graph 局部 PortContext 终止时销毁:本测试
   只校验返回值,不持有 inner PortContext 跨边界。

PG-006 同图同名端口冲突在编译期检查(spec §2.1.3 铁律 3);运行时
铁律 1 / 2 由 ``exit_subgraph`` 保障。
"""

from __future__ import annotations

from lca.harness.graph.execute.v2._port_context import PortContext


class TestExitSubgraphPassthrough:
    """``PortContext.exit_subgraph`` projects inner values onto outer ports."""

    def test_inner_port_with_matching_outer_name_passes_through(self) -> None:
        """铁律 1:inner `response` 透传到 outer `response`。"""
        ctx = PortContext()
        sentinel = object()
        ctx.merge_output({"response": sentinel, "unused": "DROP_ME"})

        outer_input = ctx.exit_subgraph(outer_outputs=("response",))
        assert outer_input == {"response": sentinel}
        # 未声明的 inner port 不外泄
        assert "unused" not in outer_input

    def test_missing_inner_port_yields_empty_dict(self) -> None:
        """铁律 2:inner 没产生 outer 要的 port → outer 拿空 dict。"""
        ctx = PortContext()
        ctx.merge_output({"other": "x"})

        outer_input = ctx.exit_subgraph(outer_outputs=("response",))
        assert outer_input == {}

    def test_multiple_outer_ports_projected_independently(self) -> None:
        """多个 outer port 各自独立投影,缺则填缺。"""
        ctx = PortContext()
        ctx.merge_output({"response": "r1", "decision": "d1"})

        outer_input = ctx.exit_subgraph(
            outer_outputs=("response", "decision", "missing_port")
        )
        assert outer_input == {"response": "r1", "decision": "d1"}
        # 缺的 port 不进 dict(由 build_input 缺省填空)
        assert "missing_port" not in outer_input
