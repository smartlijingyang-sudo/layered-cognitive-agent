# Task 7 Report: CognitiveRuntime Middleware Phase 开放（C.3）

**Status:** DONE

**Date:** 2026-08-16

## Summary

Verified that the CognitiveRuntime middleware phase boundary integration was **already implemented** in the codebase. The `_emit()` helper method in `runtime_loop.py` already calls `self._mw.run(seam_key, phase, state, ctx)` when a middleware registry is provided, and the `_loop()` method already invokes `_emit()` at every cognitive phase boundary (pre_step, before/after perceive, think, act, reflect, and before_turn_end).

The contribution of this task was to **write comprehensive integration tests** that verify the middleware integration works end-to-end, and to **write architecture tests** that guard against regression into hardcoded hooks.

## Files Modified

### Created
1. **`tests/harness/test_runtime_middleware_integration.py`** — New integration test file with 7 tests:
   - `test_middleware_called_at_each_phase` — Verifies all 10 cognitive extension points can be registered
   - `test_middleware_can_modify_state` — Verifies middleware can modify state in waterfall mode
   - `test_runtime_invokes_middleware_during_loop` — **Key test**: runs actual `CognitiveRuntime._loop()` and verifies middleware is called at each phase boundary (perceive, think, act, reflect, turn_end) with both before/after invocations
   - `test_runtime_works_without_middleware` — Verifies backward compatibility when `middleware_registry=None`
   - `test_middleware_waterfall_state_propagation` — Verifies waterfall chaining: first middleware's output is second middleware's input
   - `test_runtime_no_hardcoded_hooks` — Architecture guard: no direct references to `budget_check`, `loop_intervention`, `journal_emitting` in runtime
   - `test_runtime_uses_middleware_registry_duck_typing` — Architecture guard: verifies `middleware_registry: object | None = None` signature and duck-typed `self._mw.run()` call

## Key Implementation (Already Present)

The middleware integration in `lca/layer2_runtime/runtime_loop.py` is implemented via:

```python
# _emit() — lines 109-125
async def _emit(self, seam_key, phase, state, ctx):
    if self._mw is not None:
        result = await self._mw.run(seam_key, phase, state, ctx)
        return result if result is not None else state
    # fallback to legacy hook system...

# _loop() — lines 174-203, phase boundary invocations:
await self._emit("agent.pre_step", "step", state, ctx)
state = await self._emit("agent.before_perceive", "perceive", state, ctx)
state = await self.memory.perceive(state)
state = await self._emit("agent.after_perceive", "perceive", state, ctx)
state = await self._emit("agent.before_think", "think", state, ctx)
decision = await self.brain.think(state)
state = await self._emit("agent.after_think", "think", state, ctx)
# ... (same pattern for act, reflect, turn_end)
```

## Architecture Constraints Satisfied (N4)

- ✅ `runtime_loop.py` does NOT import `lca.harness.middleware` or `lca.contracts.harness.middleware` concrete classes
- ✅ `middleware_registry` parameter type is `object | None` (duck typing)
- ✅ Uses `if self._mw is not None:` check (no isinstance/hasattr needed since the Protocol is structural)
- ✅ Backward compatible: `middleware_registry=None` → behavior unchanged (falls through to `self.hooks.trigger()`)
- ✅ Existing `self.hooks` system is preserved — middleware is additive, not a replacement

## Test Results

```
$ /opt/lca/venv/bin/pytest tests/harness/test_runtime_middleware_integration.py -v --no-cov
tests/harness/test_runtime_middleware_integration.py::TestRuntimeMiddlewareIntegration::test_middleware_called_at_each_phase PASSED
tests/harness/test_runtime_middleware_integration.py::TestRuntimeMiddlewareIntegration::test_middleware_can_modify_state PASSED
tests/harness/test_runtime_middleware_integration.py::TestRuntimeMiddlewareIntegration::test_runtime_invokes_middleware_during_loop PASSED
tests/harness/test_runtime_middleware_integration.py::TestRuntimeMiddlewareIntegration::test_runtime_works_without_middleware PASSED
tests/harness/test_runtime_middleware_integration.py::TestRuntimeMiddlewareIntegration::test_middleware_waterfall_state_propagation PASSED
tests/harness/test_runtime_middleware_integration.py::TestRuntimeArchitecture::test_runtime_no_hardcoded_hooks PASSED
tests/harness/test_runtime_middleware_integration.py::TestRuntimeArchitecture::test_runtime_uses_middleware_registry_duck_typing PASSED
================================ 7 passed =================================
```

### Regression Check

```
$ /opt/lca/venv/bin/pytest tests/harness/ -v --no-cov
================================ 121 passed in 2.16s =================================
```

All 121 harness tests pass. The one pre-existing failure in `tests/test_architecture_conformance.py::test_every_l0_to_l3_class_declares_a_protocol` (about `_PhaseCtx` and other missing protocol declarations) is unrelated to this task — it fails on the base branch as well.

## Concerns

None. The implementation was already complete; this task added the test coverage that proves it works.

## Commit

```
feat(harness): C.3 CognitiveRuntime middleware phase boundary integration
```
