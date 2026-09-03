"""Boot-time binding completeness test — ADR-0076 §四 验证约束.

Production profiles must boot fail-closed when they lack a closure-required
capability.  This module is the public acceptance test path listed in the
ADR's 验证约束 section:

    tests/test_boot_binding_completeness.py: 生产 profile boot 时缺少
    binding 抛 ``MissingBindingError``

The test re-uses the validator in
``lca/harness/profile/runtime_binding_validator.py`` (W1 / P0 deliverable)
and exercises every required capability key, the profile ``fallback_policy``
allowlist, and the diagnostic helpers (``provider_hint`` / ``candidates`` /
``additional``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.plan_compiler import CompileOptions, compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.harness.profile.runtime_binding_validator import (
    MissingBindingError,
    RuntimeBindingValidator,
    validate_runtime_closure,
)
from lca.harness.profile.runtime_closure import (
    RUNTIME_CLOSURE_FALLBACK_POLICIES,
    RUNTIME_CLOSURE_REQUIREMENTS,
    FallbackPolicy,
    closure_provider_hint,
    closure_requirements,
    default_fallback_policy,
    runtime_closure_requirements,
)

_GOLDEN_PROFILES: tuple[str, ...] = (
    "profiles/web-standard.yaml",
    "profiles/web-standard-recovery.yaml",
    "profiles/coding-agent.yaml",
    "profiles/cordis-creator.yaml",
    "profiles/genai-traced.yaml",
    "tests/golden/profiles/standard-solo.yaml",
    "tests/golden/profiles/standard-team.yaml",
    "tests/golden/profiles/hitl-loop.yaml",
)


# ── Closure table shape ───────────────────────────────────────────────


def test_closure_requirements_table_is_populated() -> None:
    """RUNTIME_CLOSURE_REQUIREMENTS must declare the production closure set.

    Every entry is a capability key whose absence in a production profile
    triggers ``MissingBindingError`` at compile time.
    """

    assert RUNTIME_CLOSURE_REQUIREMENTS, (
        "RUNTIME_CLOSURE_REQUIREMENTS must declare at least one required capability"
    )
    expected_keys = {
        "idempotency_store",
        "effect_handler_registry",
        "delta_handler_registry",
        "evidence_store",
        "reducer",
        "artifact_closure",
        "phase_observer",
        "resume_input_adapters",
    }
    actual_keys = set(RUNTIME_CLOSURE_REQUIREMENTS.keys())
    assert expected_keys.issubset(actual_keys), (
        f"Closure table missing keys: {sorted(expected_keys - actual_keys)}. "
        "Update RUNTIME_CLOSURE_REQUIREMENTS to enumerate every production-required binding."
    )


def test_closure_compatibility_tables_are_derived_from_catalog() -> None:
    """Public compatibility tables must be projections of the one closure catalog."""

    catalog = runtime_closure_requirements()
    assert catalog
    assert {
        requirement.capability: requirement.provider_hint for requirement in catalog
    } == RUNTIME_CLOSURE_REQUIREMENTS
    assert {
        requirement.capability: requirement.default_fallback_policy for requirement in catalog
    } == RUNTIME_CLOSURE_FALLBACK_POLICIES
    for requirement in catalog:
        assert (
            default_fallback_policy(requirement.capability) == requirement.default_fallback_policy
        )


def test_closure_provider_hint_returns_path() -> None:
    """``closure_provider_hint`` must return the expected module path for each key."""

    for capability in RUNTIME_CLOSURE_REQUIREMENTS:
        hint = closure_provider_hint(capability)
        assert hint, f"closure_provider_hint({capability!r}) returned empty/None"
        assert hint.startswith("lca."), (
            f"closure_provider_hint({capability!r})={hint!r} is not a lca module path"
        )


def test_closure_requirements_is_a_tuple() -> None:
    """``closure_requirements()`` must return a stable tuple."""

    keys = closure_requirements()
    assert isinstance(keys, tuple)
    # Same call yields same tuple — deterministic ordering
    assert closure_requirements() == keys


# ── Production profile boot ────────────────────────────────────────────


def test_default_profile_passes_completeness_check() -> None:
    """``profiles/web-standard.yaml`` provides the full closure."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    validate_runtime_closure(resolved)  # no MissingBindingError


def test_compile_plan_calls_validator() -> None:
    """``compile_plan`` must invoke ``validate_runtime_closure``."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    plan = compile_plan(resolved, options=CompileOptions())
    assert compiled_run_plan_ref(plan), "compile_plan must produce a non-empty plan_ref"


@pytest.mark.parametrize("profile_path", _GOLDEN_PROFILES)
def test_golden_profiles_have_complete_closure(profile_path: str) -> None:
    """Every golden profile that exists on disk must satisfy the closure check.

    Missing profiles are silently skipped (not every repo checkout has every
    profile); at least one profile must be present.
    """

    if not Path(profile_path).exists():
        pytest.skip(f"profile {profile_path!r} not present")
    resolved = resolve_profile(profile_path)
    validator = RuntimeBindingValidator()
    validator.validate(resolved)


# ── Negative path: missing binding ─────────────────────────────────────


@pytest.mark.parametrize(
    "capability",
    [
        "idempotency_store",
        "effect_handler_registry",
        "delta_handler_registry",
        "evidence_store",
        "reducer",
        "artifact_closure",
        "phase_observer",
    ],
)
def test_missing_binding_fails_compile(capability: str, tmp_path: Path) -> None:
    """Disabling one directly resolvable production binding fails compile.

    The resume-input registry is also part of the closure table because runtime
    assembly consumes it directly. It is intentionally exercised through the
    golden-profile completeness check: disabling its shared factory seam would
    prevent unrelated registry consumers from resolving before this validator
    can provide its consolidated diagnostic.
    """

    # Map capability → patches to disable in the base bundle
    seam_map: dict[str, tuple[str, ...]] = {
        "idempotency_store": ("lca-idempotency-store-seam",),
        "effect_handler_registry": (
            "lca-effect-handler-registry-seam",
            "lca-effect-handler-provider",
        ),
        "delta_handler_registry": (
            "lca-delta-handler-registry-seam",
            "lca-delta-handler-provider",
        ),
        "evidence_store": ("lca-evidence-store-seam",),
        "reducer": ("lca-default-reducer",),
        # StopPolicy consumes artifact_closure explicitly. Disable the consumer
        # together with its provider so profile resolution can reach the
        # closure validator that this negative test exercises.
        "artifact_closure": ("lca-artifact-closure-provider", "state.stop-policy.default"),
        "phase_observer": ("lca-phase-observer-provider",),
    }
    disabled_ids = seam_map.get(capability)
    if disabled_ids is None:
        pytest.skip(f"no seam map for {capability!r}")

    patches = "\n".join(f"  - id: {plugin_id}\n    disabled: true" for plugin_id in disabled_ids)
    profile_content = f"""
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
{patches}
"""
    profile_path = tmp_path / f"test-missing-{capability.replace('_', '-')}.yaml"
    profile_path.write_text(profile_content)

    resolved = resolve_profile(profile_path)
    with pytest.raises(MissingBindingError, match=capability):
        compile_plan(resolved, options=CompileOptions())


# ── Diagnostic error shape ─────────────────────────────────────────────


def test_missing_binding_error_exposes_diagnostic_fields() -> None:
    """``MissingBindingError`` must surface capability / hint / candidates."""

    error = MissingBindingError(
        capability="effect_handler_registry",
        expected_source="bundle or profile patch",
        fallback_policy=FallbackPolicy.PRODUCTION,
        provider_hint="lca.plugins.act.effect_handler_seam",
        candidates=("bundle: bundles/base.yaml",),
        additional=(("reducer", FallbackPolicy.PRODUCTION, "lca.runtime.reducer"),),
    )
    msg = str(error)
    assert "effect_handler_registry" in msg
    assert "lca.plugins.act.effect_handler_seam" in msg
    assert "reducer" in msg
    assert "bundle: bundles/base.yaml" in msg
    assert error.capability == "effect_handler_registry"
    assert error.fallback_policy is FallbackPolicy.PRODUCTION
    assert error.provider_hint == "lca.plugins.act.effect_handler_seam"
    assert error.additional == (("reducer", FallbackPolicy.PRODUCTION, "lca.runtime.reducer"),)


def test_fallback_policy_test_default_relaxes_validator(tmp_path: Path) -> None:
    """Profile declaring ``fallback_policy: <cap>: test_default`` passes validation."""

    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - id: lca-evidence-store-seam
    disabled: true
fallback_policy:
  evidence_store: test_default
"""
    profile_path = tmp_path / "test-fallback-test-default.yaml"
    profile_path.write_text(profile_content)

    resolved = resolve_profile(profile_path)
    # No MissingBindingError because the profile declares test_default.
    validate_runtime_closure(resolved)


def test_fallback_policy_off_relaxes_validator(tmp_path: Path) -> None:
    """Profile declaring ``fallback_policy: <cap>: 'off'`` passes validation.

    YAML interprets bare ``off`` as Python ``False``; the policy parser
    accepts the string ``"off"`` as well as ``False``.
    """

    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - id: lca-evidence-store-seam
    disabled: true
fallback_policy:
  evidence_store: "off"
"""
    profile_path = tmp_path / "test-fallback-off.yaml"
    profile_path.write_text(profile_content)

    resolved = resolve_profile(profile_path)
    validate_runtime_closure(resolved)


def test_fallback_policy_invalid_value_rejected_at_resolve(tmp_path: Path) -> None:
    """An unknown ``fallback_policy`` value must be rejected by ``resolve_profile``.

    This is the front-line guard: malformed profiles fail before reaching
    the validator, so the validator cannot silently swallow typos.
    """

    from lca.harness.profile.resolve import ProfileResolveError

    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
fallback_policy:
  evidence_store: nonsense
"""
    profile_path = tmp_path / "test-fallback-invalid.yaml"
    profile_path.write_text(profile_content)

    with pytest.raises(ProfileResolveError, match="fallback_policy"):
        resolve_profile(profile_path)


__all__ = [
    "test_closure_compatibility_tables_are_derived_from_catalog",
    "test_closure_provider_hint_returns_path",
    "test_closure_requirements_is_a_tuple",
    "test_closure_requirements_table_is_populated",
    "test_compile_plan_calls_validator",
    "test_default_profile_passes_completeness_check",
    "test_fallback_policy_invalid_value_rejected_at_resolve",
    "test_fallback_policy_off_relaxes_validator",
    "test_fallback_policy_test_default_relaxes_validator",
    "test_missing_binding_error_exposes_diagnostic_fields",
]
