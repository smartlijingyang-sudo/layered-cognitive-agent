#!/usr/bin/env python3
"""端到端冒烟测试：boot profile → compile plan → spawn agent → run task。"""

import asyncio
import os
import sys
import tempfile
import traceback

# 确保 lca 包可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("UV_CACHE_DIR", os.path.join(tempfile.gettempdir(), "uv-cache"))


async def main() -> int:
    print("=" * 60)
    print("E2E SMOKE TEST: boot → compile → bind → run")
    print("=" * 60)

    # ── Step 1: Boot profile ──────────────────────────────────────
    print("\n[1/6] resolve_profile + boot_resolved_profile ...")
    try:
        from lca.harness.profile.resolve import resolve_profile

        resolved = resolve_profile("profiles/web-standard.yaml")
        print(
            f"  ✓ ResolvedProfile: {len(resolved.plugins)} plugins, "
            f"{len(resolved.dag_edges)} DAG edges"
        )
        for p in resolved.plugins:
            status = "DISABLED" if p.disabled else "enabled"
            print(f"    - {p.id} ({p.definition.spec.layer}, {status})")
    except Exception as e:
        print(f"  ✗ resolve_profile FAILED: {e}")
        traceback.print_exc()
        return 1

    try:
        from lca.harness.profile.boot import boot_resolved_profile

        ctx = await boot_resolved_profile(resolved)
        print(f"  ✓ Boot OK, context type={type(ctx).__name__}")
    except Exception as e:
        print(f"  ✗ boot_resolved_profile FAILED: {e}")
        traceback.print_exc()
        return 1

    # ── Step 2: Compile plan ──────────────────────────────────────
    print("\n[2/6] compile_plan (declarative projection) ...")
    try:
        from lca.harness.declarative.validation import is_validation_valid, validation_errors
        from lca.harness.plan import compiled_run_plan_ref
        from lca.harness.profile.plan_compiler import compile_plan

        plan = compile_plan(resolved)
        print(f"  ✓ CompiledRunPlan: plan_ref={compiled_run_plan_ref(plan)}")
        if plan.phase_graph:
            print(
                f"    phase_graph: {len(plan.phase_graph.nodes)} nodes, "
                f"{len(plan.phase_graph.edges)} edges"
            )
            for node in plan.phase_graph.nodes:
                print(f"      node: {node.id} ({node.semantic_phase.value})")
            for edge in plan.phase_graph.edges:
                loop_info = f" [loop max={edge.loop.max_iterations}]" if edge.loop else ""
                print(f"      edge: {edge.source} → {edge.target}{loop_info}")
        else:
            print("  ✗ phase_graph is None — declarative projection empty")
            return 1
        print(f"    phase_bindings: {len(plan.phase_bindings)}")
        for binding in plan.phase_bindings:
            contribs = [c.executor for c in binding.contributions]
            print(
                f"      {binding.node_id}: executor={binding.executor_capability} "
                f"contributions={contribs}"
            )
        print(f"    control_entries: {len(plan.control_entries)}")
        print(
            f"    effect_policy: allowed={plan.effect_policy.allowed_effects if plan.effect_policy else 'None'}"
        )
        print(
            f"    validation: valid={is_validation_valid(plan.validation_report)}, "
            f"errors={[i.code for i in validation_errors(plan.validation_report)]}"
        )
    except Exception as e:
        print(f"  ✗ compile_plan FAILED: {e}")
        traceback.print_exc()
        return 1

    # ── Step 3: Check capabilities on ctx ─────────────────────────
    print("\n[3/6] inject phase executor capabilities from ctx ...")
    try:
        for binding in plan.phase_bindings:
            cap = binding.executor_capability
            obj = ctx.inject(cap)
            print(f"  ✓ ctx.inject('{cap}') → {type(obj).__name__}")
        for binding in plan.phase_bindings:
            for contrib in binding.contributions:
                obj = ctx.inject(contrib.executor)
                print(f"  ✓ ctx.inject('{contrib.executor}') → {type(obj).__name__}")
    except Exception as e:
        print(f"  ✗ inject FAILED: {e}")
        traceback.print_exc()
        return 1

    # ── Step 4: Check core capabilities ───────────────────────────
    print("\n[4/6] inject core capabilities (memory, hooks, state_store, ...) ...")
    # Note: brain/body/perceive_hub are composed graph facts, not direct capabilities.
    # Brain and Body use registries; StopPolicy is injected by the State cluster
    # and contributed only to the fixed stop phase.
    for cap in ("memory", "hooks", "state_store"):
        try:
            obj = ctx.inject(cap)
            print(f"  ✓ ctx.inject('{cap}') → {type(obj).__name__}")
        except Exception as e:
            print(f"  ✗ ctx.inject('{cap}') FAILED: {e}")
            # These are critical, fail the test
            return 1

    # ── Step 5: Spawn Agent ───────────────────────────────────────
    print("\n[5/6] spawn_agent (plan-bound assembly) ...")
    try:
        from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
        from lca.contracts.protocols.spec import AgentSpec

        # Use mock LLM to avoid needing a real key
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer4_app.spawn import spawn_agent

        spec = AgentSpec(
            profile=RoleProfile(
                role="test-agent",
                goal="Test the end-to-end flow",
                backstory="A test agent",
                tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
            ),
            llm=MockLLMAdapter(),
            tools=(),
        )
        agent = spawn_agent(spec, scope=ctx)
        print(f"  ✓ spawn_agent → {type(agent).__name__}")
        print(f"    plan_ref={agent.plan_ref}")
        print(f"    runtime type={type(agent.runtime).__name__}")
        rt = agent.runtime
        has_plan = getattr(rt, "compiled_plan", None) is not None
        has_executors = bool(getattr(rt, "phase_executors", None))
        print(f"    runtime.compiled_plan={'YES' if has_plan else 'NO'}")
        print(
            f"    runtime.phase_executors={'YES' if has_executors else 'NO'} ({len(rt.phase_executors)} executors)"
        )
    except Exception as e:
        print(f"  ✗ spawn_agent FAILED: {e}")
        traceback.print_exc()
        return 1

    # ── Step 6: Run task ──────────────────────────────────────────
    print("\n[6/6] agent.run('Hello, this is an e2e smoke test') ...")
    try:
        # Enable debug logging to see what's happening
        import logging

        logging.basicConfig(level=logging.DEBUG)

        result = await agent.run("Hello, this is an e2e smoke test. Just respond with OK.")
        print("  ✓ run completed:")
        print(f"    status={result.status}")
        print(f"    output={result.output[:200] if result.output else '(empty)'}")
        print(f"    total_steps={result.total_steps}")
        print(f"    error={result.error or '(none)'}")

        # Check if the agent actually produced output
        if result.status.value == "failed" and not result.output:
            print("\n  ⚠ Agent run completed but produced no output")
            print("    This usually means:")
            print("    - Phase executors didn't set state.final_output")
            print("    - The think phase didn't produce a Decision with response_text")
            print("    - The stop phase didn't properly extract final_output from StopDecision")
            print("    - Delta handlers didn't apply the final_output to state")
            print("    - An exception occurred during phase execution (check logs)")
            return 1
    except Exception as e:
        print(f"  ✗ agent.run FAILED: {type(e).__name__}: {e}")
        import traceback as tb

        tb.print_exc()
        return 1

    print("\n" + "=" * 60)
    print("ALL 6 STEPS PASSED ✓")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
