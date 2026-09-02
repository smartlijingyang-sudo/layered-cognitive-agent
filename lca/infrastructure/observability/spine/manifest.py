"""Close-set of execution points that must emit a spine event.

Adding/removing a point requires a Layer-1 build-time check pass and an
EXECUTION_POINT_TEST matching it (I8 of ADR-0165.1). The set is intentional:
do not edit casually.
"""

EXECUTION_POINTS: tuple[str, ...] = (
    # Transport (ADR-0112)
    "transport.route.enter",
    "transport.route.exit",
    "transport.sse.publish",
    # Kernel lifecycle
    "kernel.boot.start",
    "kernel.boot.completed",
    "kernel.run.start",
    "kernel.run.stop",
    "kernel.run.cancelled",
    # Agent loop
    "agent_loop.iteration.start",
    "agent_loop.iteration.end",
    # Cognition
    "brain.perceive.start",
    "brain.perceive.end",
    "brain.think.start",
    "brain.think.end",
    "brain.gate.start",
    "brain.gate.end",
    "critic.eval.start",
    "critic.eval.end",
    "reasoner.reason.start",
    "reasoner.reason.end",
    "synthesizer.merge",
    "skill_router.route",
    "memory.read",
    "memory.write",
    # Body
    "body.tool.execute.start",
    "body.tool.execute.end",
    "body.tool.retry",
    # Writable matrix (ADR-0167 D11) —— coordinator-only step / segment 边
    "writable.step.start",
    "writable.step.end",
    "writable.segment.start",
    "writable.segment.end",
    # Writable matrix phase events (perceive / think / act / reflect / remember / stop)
    "perceive.phase.fold",
    "phase.perceive.fold",
    "phase.remember.fold",
    "phase.stop.fold",
    "phase.reflect.fold",
    "phase.act.fold.start",
    "phase.act.fold.end",
    "phase.tool.call.start",
    "phase.tool.call.end",
    "phase.tool.denied",
    # Lifecycle normalization (ADR-0166 S5) —— 正常路径用 lifecycle.finally
    "lifecycle.finally",
    "body.sandbox.enter",
    "body.sandbox.exit",
    # LLM
    "llm.call.start",
    "llm.call.end",
    "llm.stream.token",
    "llm.stream.stall",
    # Runtime
    "runtime.reducer.apply",
    "runtime.checkpoint.create",
    "runtime.resume.start",
    "runtime.resume.end",
    "runtime.event_publisher.publish",
    # Phase graph
    "phase_graph.node.start",
    "phase_graph.node.end",
    "phase_graph.edge.transit",
    # Exception/finally
    "exception.caught",
    "exception.finally",
)
