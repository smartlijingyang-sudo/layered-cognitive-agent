"""把 Profile 编译出来的 CompiledRunPlan 渲染成几张可读视图。

用法：
    python scripts/lca-inspect-plan.py                 # 默认 profiles/web-standard.yaml
    python scripts/lca-inspect-plan.py profiles/coding-agent.yaml
"""

from __future__ import annotations

import sys

from lca.harness.declarative.execute.interpreter import compiled_run_plan_ref
from lca.harness.profile.plan_compiler import CompileOptions, compile_plan
from lca.harness.profile.resolve import resolve_profile

# ---------- 0. 编译计划 --------------------------------------------------------
profile_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/web-standard.yaml"
profile = resolve_profile(profile_path)
plan = compile_plan(profile, options=CompileOptions(require_executable_phase_graph=True))
plan_ref = compiled_run_plan_ref(plan)

print("=" * 78)
print(f"plan_ref = {plan_ref}   (SHA-256[:16] of canonicalised plan)")
print(
    f"profile_path: {plan.profile_path}   plan_version: {plan.plan_version}   revision: {plan.revision}"
)

issues = plan.validation_report.issues
errors = [
    i for i in issues if str(i.severity) == "ValidationSeverity.ERROR" or i.severity == "error"
]
print(f"validation: {len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
for i in issues:
    print(f"   [{i.code}] {i.severity} {i.location}: {i.message}")
print("=" * 78)

# ---------- 1. 节点视图 --------------------------------------------------------
print("\n## 1. Nodes (node · phase · binding · executor_capability · max_visits)")
print("-" * 78)
print(f"  {'node_id':<14} {'semantic':<10} {'binding':<26} {'exec_cap':<24} visits")
phase_bindings = {pb.node_id: pb for pb in plan.phase_bindings}
for n in plan.phase_graph.nodes:
    pb = phase_bindings.get(n.id)
    exec_cap = pb.executor_capability if pb else "-"
    sem = n.semantic_phase.value if hasattr(n.semantic_phase, "value") else n.semantic_phase
    print(f"  {n.id:<14} {sem:<10} {n.binding:<26} {exec_cap:<24} {n.max_visits}")

# ---------- 2. 边视图 ----------------------------------------------------------
print("\n## 2. Edges (source → target gated by when / loop_guard)")
print("-" * 78)
print(f"  {'source':<14} -> {'target':<14} predicate")
for e in plan.phase_graph.edges:
    guard = ""
    if e.loop is not None:
        guard = (
            f"   [LOOP max={e.loop.max_iterations}, budget={e.loop.budget}, "
            f"terminal=({e.loop.terminal_predicate})]"
        )
    print(f"  {e.source:<14} -> {e.target:<14} when: {e.when}{guard}")

# ---------- 3. Effect 策略 -----------------------------------------------------
print("\n## 3. Effect policy (Effect Gateway 白名单 / 审批 / 幂等)")
print("-" * 78)
ep = plan.effect_policy
print(f"  allowed_effects      : {sorted(ep.allowed_effects)}")
print(f"  approval_required    : {sorted(ep.approval_required)}")
print(f"  idempotency_required : {sorted(ep.idempotency_required)}")

# ---------- 4. Action authority ------------------------------------------------
print("\n## 4. Action authority (allowed / denied)")
print("-" * 78)
aa = plan.action_authority
print(f"  allowed_actions  : {sorted(aa.allowed_actions)}")
print(f"  forbidden_actions: {sorted(aa.forbidden_actions)}")
print(f"  scope            : {aa.scope}")
for sa in aa.scoped_actions:
    print(f"    scope={sa.scope}: allowed={sorted(sa.allowed_actions)}")

# ---------- 5. Control entries -------------------------------------------------
print("\n## 5. Control entries (govern/observe 是计划里唯一的控制面)")
print("-" * 78)
print(f"  {'phase':<10} {'executor_capability':<28} predicate             aggregation   evidence")
for ce in plan.control_entries:
    ph = ce.phase.value if hasattr(ce.phase, "value") else ce.phase
    print(
        f"  {ph:<10} {ce.executor_capability:<28} {ce.predicate:<20} "
        f"{ce.aggregation:<14} {ce.evidence_required}"
    )

# ---------- 6. 阶段执行策略 (retry / timeout / on_exhausted) --------------------
print("\n## 6. Per-node execution policy (retry, timeout, on_exhausted)")
print("-" * 78)
for n in plan.phase_graph.nodes:
    p = n.execution_policy
    if p is None:
        print(f"  {n.id:<14} (no policy)")
        continue
    oe = p.on_exhausted.value if hasattr(p.on_exhausted, "value") else p.on_exhausted
    print(
        f"  {n.id:<14} attempts={p.max_attempts} "
        f"timeout={p.timeout_seconds}s retry={p.retry_on} "
        f"on_exhausted={oe}"
    )

# ---------- 7. 把图画成 ASCII (带节点上的控制槽) -------------------------------
PHASE_COLOR = {
    "perceive": "P",
    "think": "T",
    "act": "A",
    "reflect": "R",
    "remember": "M",
    "stop": "S",
    "observe": "O",
}
SEMANTIC_LETTER = {
    "perceive": "P",
    "think": "T",
    "act": "A",
    "reflect": "R",
    "remember": "M",
    "stop": "S",
}

# 整理节点在每个 semantic_phase 上的控制贡献（来自 phase_bindings 的 contributions）
by_phase_controls: dict[str, list[str]] = {}
for pb in plan.phase_bindings:
    sem = pb.semantic_phase.value if hasattr(pb.semantic_phase, "value") else pb.semantic_phase
    for c in pb.contributions:
        role = c.role.value if hasattr(c.role, "value") else c.role
        by_phase_controls.setdefault(sem, []).append(f"{role}:{c.output}")

print("\n## 7. ASCII phase graph (节点 + 每个阶段跑哪些控制)")
print("-" * 78)

# 节点块
for n in plan.phase_graph.nodes:
    sem = n.semantic_phase.value if hasattr(n.semantic_phase, "value") else n.semantic_phase
    letter = SEMANTIC_LETTER.get(sem, "?")
    ctrls = by_phase_controls.get(sem, [])
    mark = []
    if getattr(n, "entry", False):
        mark.append("ENTRY")
    if getattr(n, "terminal", False):
        mark.append("TERMINAL")
    mark_str = ("  " + "/".join(mark)) if mark else ""
    ctrls_str = "  controls: " + ", ".join(ctrls) if ctrls else ""
    print(f"  [{letter}] {n.id:<12} ({sem}){mark_str}{ctrls_str}")

# 边
print("\n  edges:")
for e in plan.phase_graph.edges:
    guard = ""
    if e.loop is not None:
        guard = "  [loop guard: " + e.loop.terminal_predicate + "]"
    err = "  [error-path]" if "phase_error" in str(e.when) else ""
    print(f"    {e.source} ──▶ {e.target}   when: {e.when}{err}{guard}")

# ---------- 8. Capability binding 视图 (谁提供什么) ----------------------------
print("\n## 8. Capability bindings (lexicographic id wins ties)")
print("-" * 78)
for cb in plan.capability_bindings:
    print(f"  {cb.capability:<28} ← {cb.provider}")

# ---------- 9. 替换关系 -------------------------------------------------------
print("\n## 9. Replacements (plugin REPLACES graph)")
print("-" * 78)
if plan.replacement_map:
    for k, v in plan.replacement_map.items():
        print(f"  {k}  ←  {v}")
else:
    print("  (none)")

# ---------- 10. Provenance ----------------------------------------------------
print("\n## 10. Provenance (what fed this plan)")
print("-" * 78)
prov = plan.provenance
print(f"  profile_path     : {prov.profile_path}")
print("  bundles          :")
for b in prov.bundles:
    print(f"    - {b}")
print(f"  plugin_revisions : {len(prov.plugin_revisions)} entries (sorted, lexicographic)")
print(f"  task_contract    : {prov.task_contract!r}")
print(f"  environment      : {prov.environment!r}")
print(f"  actor_grant      : {prov.actor_grant}")
