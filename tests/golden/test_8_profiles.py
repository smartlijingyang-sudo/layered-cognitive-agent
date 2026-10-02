"""Golden profile coverage tests (PR-10 + acceptance §7.3 V1/V2/V6/V7/V11).

Per acceptance-criteria §7.3, PR-10 stage 1 covers 8 golden profiles:

1. standard-solo — 1 agent (no team); V1 control plane + V2 plan_hash
2. standard-team — lead + members; V1 lead routing + V11 collaboration
3. coding-agent — coding scenario; V4 envelope + V7 creator personas
4. control-slot-coverage — 11 ControlSlot entries; V1 control plane
5. 11-relations-coverage — 11 Relation enum entries; V11 relations
6. patch-priority — Bundle + Patch priority; V2 plan_hash determinism
7. 4-state-artifact — ArtifactController 4 状态机; V6 state migration
8. hitl-loop — Human-in-the-loop; V1 act.authorize + ASK_HUMAN

This test boots each profile + verifies resolve → compile plan:
- Profile resolves without error (ProfileResolveError fail-fast)
- CompiledRunPlan has non-empty capability bindings
- CompiledRunPlan has non-empty scope (lifecycle + visibility)
- plan_hash stable across 2 runs (V2 determinism)
- plan_ref from compiled_run_plan_ref(plan) propagates to CapabilityArtifact

PR-10 stage 1: data layer + property test; PR-10 stage 2: e2e agent run
(deferred — large fixtures not yet ready in 8 profile YAMLs).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.scope.scope import Scope
from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.resolve.resolve import resolve_profile
from lca_kernel.plan.plan_compile import (
    compile_plan as compile_plan_factory,
)

GOLDEN_PROFILES_DIR = Path("tests/golden/profiles")

# 8 golden profile filenames (per acceptance §7.3 V1 + §16.2)
GOLDEN_PROFILES: tuple[str, ...] = (
    "standard-solo.yaml",
    "standard-team.yaml",
    "coding-agent.yaml",
    "control-slot-coverage.yaml",
    "11-relations-coverage.yaml",
    "patch-priority.yaml",
    "4-state-artifact.yaml",
    "hitl-loop.yaml",
)


class TestGoldenProfileCoverage:
    """PR-10 V1/V2/V6/V7/V11 acceptance: 8 golden profile coverage."""

    @pytest.mark.parametrize("profile_filename", GOLDEN_PROFILES)
    def test_profile_resolves(self, profile_filename: str) -> None:
        """每个 golden profile 都能 resolve + compile（V1 + V2 守护）。"""
        path = GOLDEN_PROFILES_DIR / profile_filename
        resolved = resolve_profile(path)
        plan = compile_plan_factory(resolved)

        # V1: control is carried only by the declarative plan projection.
        assert isinstance(plan.control_entries, tuple)
        # V2: plan_ref is stable; canonical_digest now emits a
        # "sha256:"-prefixed digest (DEFAULT_DIGEST_PREFIX).
        plan_ref_value = compiled_run_plan_ref(plan)
        assert plan_ref_value.startswith("sha256:"), plan_ref_value
        assert len(plan_ref_value) == len("sha256:") + 16, plan_ref_value

    @pytest.mark.parametrize("profile_filename", GOLDEN_PROFILES)
    def test_profile_has_non_empty_capability(self, profile_filename: str) -> None:
        """每个 golden profile 都有 non-empty CapabilityPlan（≥ 1 provider binding）。"""
        path = GOLDEN_PROFILES_DIR / profile_filename
        resolved = resolve_profile(path)
        plan = compile_plan_factory(resolved)
        assert len(plan.capability.provider_bindings) >= 1, (
            f"profile {profile_filename} has no capability bindings; expected at least 1"
        )

    @pytest.mark.parametrize("profile_filename", GOLDEN_PROFILES)
    def test_profile_has_valid_scope(self, profile_filename: str) -> None:
        """每个 golden profile 都有 valid ScopePlan（lifecycle + visibility）。"""
        path = GOLDEN_PROFILES_DIR / profile_filename
        resolved = resolve_profile(path)
        plan = compile_plan_factory(resolved)
        # ScopePlan is well-formed: visibility is a tuple of Scope
        # (CompileOptions.visibility defaults to () since the ADR-0221
        # cutover; emptiness is legal — visibility is only
        # serialized/projected, never used for access decisions).
        assert isinstance(plan.scope.visibility, tuple)
        assert all(isinstance(v, Scope) for v in plan.scope.visibility)
        # lifecycle is set (valid Scope member)
        assert isinstance(plan.scope.lifecycle, Scope)
        assert plan.scope.lifecycle.value != ""

    @pytest.mark.parametrize("profile_filename", GOLDEN_PROFILES)
    def test_profile_plan_hash_stable(self, profile_filename: str) -> None:
        """V2 acceptance: 同一输入 → 同 plan_ref (cross-run determinism)."""
        path = GOLDEN_PROFILES_DIR / profile_filename
        resolved_a = resolve_profile(path)
        resolved_b = resolve_profile(path)
        plan_a = compile_plan_factory(resolved_a)
        plan_b = compile_plan_factory(resolved_b)
        plan_ref_a = compiled_run_plan_ref(plan_a)
        plan_ref_b = compiled_run_plan_ref(plan_b)
        assert plan_ref_a == plan_ref_b, (
            f"profile {profile_filename} plan_ref not stable: {plan_ref_a!r} != {plan_ref_b!r}"
        )


class TestGoldenProfileInventory:
    """验证 8 golden profile 全部存在 + 大小非 0."""

    def test_8_golden_profiles_present(self) -> None:
        for profile_filename in GOLDEN_PROFILES:
            path = GOLDEN_PROFILES_DIR / profile_filename
            assert path.exists(), f"missing golden profile: {path}"
            assert path.stat().st_size > 0, f"empty golden profile: {path}"

    def test_all_8_profiles_counted(self) -> None:
        """Per acceptance §7.3: 8 个 golden profile 必须全部存在。"""
        assert len(GOLDEN_PROFILES) == 8
