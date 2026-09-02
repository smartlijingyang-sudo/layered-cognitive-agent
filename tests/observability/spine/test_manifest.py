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
        "llm.stream.stall",
        "runtime.reducer.apply",
        "phase_graph.node.start",
        "phase_graph.node.end",
        "exception.caught",
    }
    assert needed.issubset(set(EXECUTION_POINTS))


def test_execution_points_covers_phase_fold_eps():
    """Coordinator.emit_phase emits ``phase.<name>.fold`` for every phase
    in the close-set {perceive, think, remember, reflect, stop, act}.

    Each dynamic construction site must have its EP whitelisted, otherwise
    EventRecord.__post_init__ raises ValueError(UnknownExecutionPoint) and
    the run terminates with broken_hop=H3.
    See run_b139e8f378cf for the regression that produced this test.
    """
    needed = {
        "phase.perceive.fold",
        "phase.think.fold",
        "phase.remember.fold",
        "phase.reflect.fold",
        "phase.stop.fold",
        "phase.act.fold.start",
        "phase.act.fold.end",
    }
    missing = needed - set(EXECUTION_POINTS)
    assert not missing, f"phase fold EP whitelist missing: {sorted(missing)}"
