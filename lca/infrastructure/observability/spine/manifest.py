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
    "prompt_assembler.assemble.start",
    "prompt_assembler.assemble.end",
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
    # Loop cursor control (ADR-0169):halt / closing / fork —— 投影宿主与
    # PersistenceCoordinator 跨域订阅,在 ADR-0170 §D6 §L16 处制度化,
    # 此处仅为白名单登记(不引入新控制面)。
    "writable.iteration.halt",
    "writable.iteration.close",
    "loop.fork",
    # Writable matrix phase events (perceive / think / act / reflect / remember / stop)
    "perceive.phase.fold",
    "phase.perceive.fold",
    "phase.think.fold",
    "phase.gate.fold",
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
    # Coordinator record_* EP(ADR-0167 D2: Agent 不直接 import EventSpine,
    # 唯一写路径 = Coordinator.record_* → 这些 EP)
    "step.thinking.record",
    "step.tool_call.record",
    "step.tool_result.record",
    "step.reflect.record",
    "step.span.record",
    # Spine self-observation (ADR-2026-09-02-i17-traceback):
    # the spine itself publishes these via EmitPipeline so they ride
    # the same seal/anomaly path as producer-supplied events.
    "spine.i17.rejected",  # *.start rejected for missing source_location
    "spine.producer.failure",  # a FieldProducer raised on a sub-field
    "phase_graph.instrument.coverage",  # once-per-run I17 provider presence
)
