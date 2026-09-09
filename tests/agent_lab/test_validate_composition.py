"""Graph composition law + execute kernel (N3/N4/N5, C1/C4, invoke, N6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.graph.spec import InfoEdgeSpec, InfoGrant, InfoNode, SubSpecLink
from agent_lab.graph.validate import validate
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from agent_lab.primitives.edge import Edge, EdgeKind
from agent_lab.primitives.port import PortRef


def test_n3_rejects_two_sub_specs_on_one_host() -> None:
    spec = InfoEdgeSpec(
        id="loop",
        nodes=[InfoNode(id="remember", factory="graph.call", ins=["in"], outs=["out"])],
        sub_specs=[
            SubSpecLink(
                node_id="remember",
                sub_spec_id="remember",
                input_map={"in": "in"},
                output_map={"out": "out"},
            ),
            SubSpecLink(
                node_id="remember",
                sub_spec_id="stop_decide",
                input_map={"in": "in"},
                output_map={"out": "out"},
            ),
        ],
    )
    errs = validate(spec)
    assert any(e.startswith("N3:") and "remember" in e for e in errs)


def test_n4_rejects_identity_host() -> None:
    spec = InfoEdgeSpec(
        id="t",
        nodes=[
            InfoNode(
                id="think",
                factory="identity",
                ins=["in"],
                outs=["out"],
            )
        ],
        sub_specs=[
            SubSpecLink(
                node_id="think",
                sub_spec_id="think_inner",
                input_map={"in": "in"},
                output_map={"out": "out"},
            )
        ],
    )
    errs = validate(spec)
    assert any(e.startswith("N4:") and "think" in e for e in errs)


def test_n4_accepts_graph_call_host() -> None:
    spec = InfoEdgeSpec(
        id="t",
        nodes=[InfoNode(id="think", factory="graph.call", ins=["in"], outs=["out"])],
        sub_specs=[
            SubSpecLink(
                node_id="think",
                sub_spec_id="think_inner",
                input_map={"in": "in"},
                output_map={"out": "out"},
            )
        ],
    )
    errs = validate(spec)
    assert not any(e.startswith("N4:") for e in errs)


def test_n5_rejects_cross_spec_data() -> None:
    spec = InfoEdgeSpec(
        id="act",
        nodes=[
            InfoNode(id="observe", factory="act.observe", ins=["receipt"], outs=["observation"])
        ],
        edges=[
            Edge(
                id="bad",
                from_ref=PortRef(spec_id="act", node_id="observe", port_id="observation"),
                to_ref=PortRef(spec_id="model_eye", node_id="see", port_id="observation"),
                kind=EdgeKind.DATA,
            )
        ],
    )
    errs = validate(spec)
    assert any(e.startswith("N5:") for e in errs)


def test_n5_allows_project_and_borrow() -> None:
    spec = InfoEdgeSpec(
        id="act",
        nodes=[
            InfoNode(id="observe", factory="act.observe", ins=["receipt"], outs=["observation"])
        ],
        edges=[
            Edge(
                id="ok",
                from_ref=PortRef(spec_id="act", node_id="observe", port_id="observation"),
                to_ref=PortRef(spec_id="model_eye", node_id="see", port_id="observation"),
                kind=EdgeKind.PROJECT,
            )
        ],
    )
    errs = validate(spec)
    assert not any(e.startswith("N5:") for e in errs)

    borrow_spec = InfoEdgeSpec(
        id="think",
        nodes=[
            InfoNode(
                id="expose",
                factory="think.expose",
                ins=["in_assembled_manifest"],
                outs=["messages"],
            )
        ],
        grants=[
            InfoGrant(
                id="g1",
                from_spec="perceive",
                to_spec="think",
                ports=["out_manifest"],
                mode="read",
            )
        ],
        edges=[
            Edge(
                id="ok_borrow",
                from_ref=PortRef(spec_id="perceive", node_id="commit", port_id="out_manifest"),
                to_ref=PortRef(
                    spec_id="think", node_id="expose", port_id="in_assembled_manifest"
                ),
                kind=EdgeKind.BORROW,
                grant_id="g1",
            )
        ],
    )
    borrow_errs = validate(borrow_spec)
    assert not any(e.startswith("N5:") for e in borrow_errs)
    assert not any(e.startswith("C4:") for e in borrow_errs)


def test_c4_borrow_without_grant_fails() -> None:
    spec = InfoEdgeSpec(
        id="think",
        nodes=[
            InfoNode(
                id="expose",
                factory="think.expose",
                ins=["in_assembled_manifest"],
                outs=["messages"],
            )
        ],
        edges=[
            Edge(
                id="b",
                from_ref=PortRef(spec_id="perceive", node_id="commit", port_id="out_manifest"),
                to_ref=PortRef(
                    spec_id="think", node_id="expose", port_id="in_assembled_manifest"
                ),
                kind=EdgeKind.BORROW,
            )
        ],
    )
    errs = validate(spec)
    assert any(e.startswith("C4:") for e in errs)


def test_c4_borrow_with_grant_compiles() -> None:
    spec = InfoEdgeSpec(
        id="think",
        nodes=[
            InfoNode(
                id="expose",
                factory="think.expose",
                ins=["in_assembled_manifest"],
                outs=["messages"],
            )
        ],
        grants=[
            InfoGrant(
                id="g1",
                from_spec="perceive",
                to_spec="think",
                ports=["out_manifest"],
                mode="read",
            )
        ],
        edges=[
            Edge(
                id="b",
                from_ref=PortRef(spec_id="perceive", node_id="commit", port_id="out_manifest"),
                to_ref=PortRef(
                    spec_id="think", node_id="expose", port_id="in_assembled_manifest"
                ),
                kind=EdgeKind.BORROW,
                grant_id="g1",
            )
        ],
    )
    errs = validate(spec)
    assert not any(e.startswith("C4:") for e in errs)


def test_c1_act_without_project_to_model_eye_fails() -> None:
    from agent_lab.graphs.loader import load_spec

    spec = load_spec(Path("agent_lab/graphs/configs/act.yaml"))
    spec = spec.model_copy(
        update={"edges": [e for e in spec.edges if e.id != "e_observe_to_model_eye"]}
    )
    errs = validate(spec)
    assert any(e.startswith("C1:") for e in errs)


def test_agent_loop_yaml_declares_stop_siblings() -> None:
    from agent_lab.graphs.loader import load_spec

    spec = load_spec(Path("agent_lab/graphs/configs/agent_loop.yaml"))
    ids = {n.id for n in spec.nodes}
    assert "stop_decide" in ids and "stop_focus" in ids
    assert "think_guard" in ids
    hosts: dict[str, list[str]] = {}
    for link in spec.sub_specs:
        hosts.setdefault(link.node_id, []).append(link.sub_spec_id)
    assert hosts.get("remember") == ["remember"]
    assert hosts.get("stop_decide") == ["stop_decide"]
    assert ("remember", "stop_decide") not in {
        (link.node_id, link.sub_spec_id) for link in spec.sub_specs
    }


def test_load_closure_includes_nested_perceive_model_eye() -> None:
    from agent_lab.graphs.loader import load_closure

    specs = load_closure("agent_loop")
    assert "agent_loop" in specs
    assert "perceive" in specs
    assert "model_eye" in specs
    assert "think" in specs
    assert "stop_decide" in specs


def test_invoke_host_passthrough_without_worker() -> None:
    from agent_lab.runtime.invoke import invoke

    src = Artifact(kind=ArtifactKind.TEXT, content="keep")
    host = InfoNode(id="h", factory="graph.call", ins=["a"], outs=["a"])
    out = invoke(host, {"a": src})
    assert out["a"].content == "keep"

    ident = InfoNode(
        id="i",
        factory="identity",
        config={"from": "x", "to": "y"},
        ins=["x"],
        outs=["y"],
    )
    out_id = invoke(ident, {"x": src})
    assert out_id["y"].content == "keep"


def test_invoke_unknown_factory_raises_keyerror() -> None:
    from agent_lab.runtime.invoke import invoke

    node = InfoNode(id="x", factory="no.such.worker", ins=[], outs=["o"])
    with pytest.raises(KeyError):
        invoke(node, {})


def test_invoke_prefers_registered_worker_over_builtin() -> None:
    from agent_lab.runtime.invoke import invoke
    from lca.plugins.lab.internal.worker import Worker, register_worker, reset_workers

    class _Ident(Worker):
        factory = "identity"

        def execute(self, node, inputs, seams=None):
            return {"to": Artifact(kind=ArtifactKind.TEXT, content="from-worker")}

    register_worker("identity", _Ident)
    try:
        node = InfoNode(id="a", factory="identity", ins=["from"], outs=["to"])
        out = invoke(node, {"from": Artifact(kind=ArtifactKind.TEXT, content="keep")})
        assert out["to"].content == "from-worker"
    finally:
        reset_workers()


def test_invoke_resolves_yaml_factory_aliases() -> None:
    from agent_lab.runtime.invoke import invoke
    from lca.plugins.lab.internal.worker import Worker, register_worker, reset_workers

    class _Sense(Worker):
        factory = "lab.perceive.sense"

        def execute(self, node, inputs, seams=None):
            return {"sensor_items": Artifact(kind=ArtifactKind.TEXT, content="ok")}

    register_worker("lab.perceive.sense", _Sense)
    try:
        node = InfoNode(id="s", factory="perceive.sense", ins=[], outs=["sensor_items"])
        out = invoke(node, {})
        assert out["sensor_items"].content == "ok"
    finally:
        reset_workers()


def test_before_compile_topology_rewrite_fails(monkeypatch) -> None:
    import importlib

    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.graph.validate import ValidationError
    from lca.plugins.lab.internal.hooks import GraphPlugin

    class _Mutator(GraphPlugin):
        def before_compile(self, spec, sub_registry=None):
            extra = InfoNode(id="sneak", factory="identity", ins=[], outs=["x"])
            return spec.model_copy(update={"nodes": [*spec.nodes, extra]})

    compile_mod = importlib.import_module("agent_lab.graph.compile")
    monkeypatch.setattr(
        compile_mod,
        "_resolve_plugins",
        lambda spec: [_Mutator(name="__mut__", kind="event_sink")],
    )
    spec = InfoEdgeSpec(
        id="t",
        nodes=[InfoNode(id="a", factory="identity", ins=[], outs=["x"])],
    )
    with pytest.raises(ValidationError) as excinfo:
        compile_spec(spec, sub_registry={})
    assert any("topology" in e for e in excinfo.value.errors)


def test_n6_output_hooks_ignore_replaced_artifacts() -> None:
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.runtime import runner as runner_mod
    from lca.plugins.lab.internal.hooks import GraphPlugin, HookContext

    class _Swapper(GraphPlugin):
        def after_node_execute(self, ctx: HookContext) -> HookContext:
            outs = dict(ctx.payload.get("outputs") or {})
            hijacked = {
                port: Artifact(kind=ArtifactKind.TEXT, content="hijacked") for port in outs
            }
            return ctx.with_value(payload={**ctx.payload, "outputs": hijacked})

    spec = InfoEdgeSpec(
        id="t",
        nodes=[
            InfoNode(
                id="a",
                factory="identity",
                config={"from": "from", "to": "to"},
                ins=["from"],
                outs=["to"],
            )
        ],
    )
    bundle = compile_spec(spec, sub_registry={})
    src = Artifact(kind=ArtifactKind.TEXT, content="keep")
    r = runner_mod._Runner(
        spec=spec,
        bundle=bundle,
        initial={"from": src},
        sub_registry={},
        trace=runner_mod.ExecutionTrace(),
        subgraph_path=spec.id,
        inherited_plugins=[_Swapper(name="swapper", kind="swapper")],
    )
    finals = r.run()
    assert finals["to"].content == "keep"
    assert finals["to"] is src


def test_output_map_missing_export_is_atomic() -> None:
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.runtime import runner as runner_mod
    from agent_lab.runtime.runner import run as run_graph

    child = InfoEdgeSpec(
        id="child",
        nodes=[
            InfoNode(
                id="writer",
                factory="identity",
                ins=["from"],
                outs=["to"],
                config={"from": "from", "to": "to"},
            ),
        ],
        edges=[
            Edge(
                id="e0",
                from_ref=PortRef(spec_id="child", node_id="_initial", port_id="from"),
                to_ref=PortRef(spec_id="child", node_id="writer", port_id="from"),
            ),
        ],
    )
    parent = InfoEdgeSpec(
        id="parent",
        nodes=[
            InfoNode(
                id="host",
                factory="graph.call",
                ins=["from"],
                outs=["a_out", "b_out"],
            )
        ],
        edges=[
            Edge(
                id="p0",
                from_ref=PortRef(spec_id="parent", node_id="_initial", port_id="from"),
                to_ref=PortRef(spec_id="parent", node_id="host", port_id="from"),
            )
        ],
        sub_specs=[
            SubSpecLink(
                node_id="host",
                sub_spec_id="child",
                input_map={"from": "from"},
                output_map={"to": "a_out", "missing": "b_out"},
            )
        ],
    )
    with pytest.raises(RuntimeError, match="missing exports"):
        run_graph(
            parent,
            initial={"from": Artifact(kind=ArtifactKind.TEXT, content="keep")},
            sub_registry={"child": child},
        )

    bundle = compile_spec(parent, sub_registry={"child": child})
    r = runner_mod._Runner(
        spec=parent,
        bundle=bundle,
        initial={"from": Artifact(kind=ArtifactKind.TEXT, content="keep")},
        sub_registry={"child": child},
        trace=runner_mod.ExecutionTrace(),
        subgraph_path=parent.id,
    )
    with pytest.raises(RuntimeError, match="missing exports"):
        r.run()
    assert ("host", "a_out") not in r.store
    assert ("host", "b_out") not in r.store
