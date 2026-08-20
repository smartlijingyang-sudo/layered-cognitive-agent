# Harness Spine Phase Status

Validated on 2026-08-16 against `harness-spine-spec.md` and the completion
plan.

## Delivered

- Phase A: loader seam reconciliation, plugin-tree inspection, profile-based
  composition, and compatibility boot path.
- Phase B: session spine, command/projection carrier, dual-write shadow mode,
  and legacy `/runs` translation.
- Phase C: runtime middleware, policy plugins, and deterministic replay.
- Phase D: DSH session-event mapping and registered loop-driver routing.  The
  legacy `/runs` carrier no longer imports or branches on DSH directly.
- Phase E: provider-separated tool definitions/rendering/policy pipeline;
  unified skill catalog, model and slash invocation paths with projection;
  subagent capability negotiation and lifecycle ownership; and declarative
  dependency-aware workflow execution.

## Compatibility Boundary

`gateway/runs` remains a compatibility carrier while `/v1/sessions` is the
authoritative Harness API.  Its loop selection is through
`RunLoopDriverRegistry`, so adding or replacing a loop provider does not add a
new gateway special case.

## Acceptance Evidence

The focused Harness, DSH/HIL regression, tool pipeline, skills, subagent/
workflow, and architecture-self-consistency tests are run as the final phase
acceptance suite.  `tests/test_architecture_self_consistency.py` prevents a
direct DSH dependency from returning to the legacy carrier and verifies Skills
projection and plugin-manifest composition.
