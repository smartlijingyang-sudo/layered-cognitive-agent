from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS


def test_execution_points_close_set():
    """Manifest is a closed-set of execution points, deduplicated."""
    assert isinstance(EXECUTION_POINTS, tuple)
    assert len(EXECUTION_POINTS) > 30
    assert all(isinstance(ep, str) for ep in EXECUTION_POINTS)
    assert len(set(EXECUTION_POINTS)) == len(EXECUTION_POINTS), "no duplicates"


def test_execution_points_covers_critical_layers():
    """At minimum: transport, kernel, brain, body, llm, runtime, phase_graph, exception."""
    needed = {
        "transport.route.enter",
        "transport.route.exit",
        "kernel.run.start",
        "kernel.run.stop",
        "brain.think.start",
        "brain.think.end",
        "body.tool.execute.start",
        "body.tool.execute.end",
        "llm.call.start",
        "llm.call.end",
        "runtime.reducer.apply",
        "phase_graph.node.start",
        "phase_graph.node.end",
        "exception.caught",
    }
    assert needed.issubset(set(EXECUTION_POINTS))
