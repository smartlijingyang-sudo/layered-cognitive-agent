"""Runtime binding 完整性测试（W1 / ADR-0076）。

验证 compile 阶段对 runtime closure 完整性的校验：

- 生产 profile 缺少必需 binding 时立即失败
- profile 顶层声明 ``fallback_policy: <key>: test_default`` / ``off`` 时放行
- 错误信息含 capability key + provider_hint + candidates（provenance）+ remediation
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.boot.runtime_closure import (
    FallbackPolicy,
    runtime_closure_requirements,
)
from lca.harness.profile.resolve.resolve import resolve_profile
from lca.harness.profile.validate.runtime_binding_validator import (
    MissingBindingError,
    RuntimeBindingValidator,
    profile_allows_test_defaults,
    validate_runtime_closure,
)
from lca_kernel.plan.plan_compile import CompileOptions, compile_plan

# W1 §144 验收：每份 golden profile 都必须能生成完整 compiled plan。
# 通用生产 profile（不依赖外部 secret/endpoint 的）纳入此清单。
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


def test_runtime_closure_requirements_not_empty() -> None:
    """运行闭合需求契约必须至少声明一个 production capability。"""
    assert runtime_closure_requirements(), (
        "runtime_closure_requirements() must declare at least one required capability"
    )


def test_default_profile_provides_required_bindings() -> None:
    """默认生产 profile 必须提供所有必需的 runtime binding。"""
    resolved = resolve_profile("profiles/web-standard.yaml")
    # 不应抛出 MissingBindingError
    validator = RuntimeBindingValidator()
    validator.validate(resolved)


def test_compile_plan_validates_runtime_closure() -> None:
    """compile_plan 必须验证 runtime closure 完整性。"""
    resolved = resolve_profile("profiles/web-standard.yaml")
    # 不应抛出 MissingBindingError
    plan = compile_plan(resolved, options=CompileOptions())
    assert plan is not None
    # plan_ref 通过 plan_hash property 或 compiled_run_plan_ref 访问
    assert compiled_run_plan_ref(plan)


def test_missing_effect_handler_registry_fails_closure_validation(tmp_path: Path) -> None:
    """禁用 effect_handler_registry seam + provider 时闭包校验必须失败。

    provider 依赖 seam 提供的 capability；只禁 seam 会触发 resolve 期的
    ``Missing capability`` 错误（依赖图不闭合）。同时禁 provider 才能让
    resolve 通过、校验阶段才报 ``MissingBindingError``。
    NOTE(round-0358): v1 编译器的 compile 内钩子随 ADR-0221 P3 退役；
    canonical 校验入口现为 lca_kernel/boot/closure.py::assert_runtime_closure
    (ADR-0115)，此处直接调用 validate_runtime_closure。
    """
    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - id: lca-effect-handler-registry-seam
    disabled: true
  - id: lca-effect-handler-provider
    disabled: true
"""
    profile_path = tmp_path / "test-missing-effect-handler.yaml"
    profile_path.write_text(profile_content)

    resolved = resolve_profile(profile_path)
    with pytest.raises(MissingBindingError, match="effect_handler_registry"):
        validate_runtime_closure(resolved)


def test_missing_delta_handler_registry_fails_closure_validation(tmp_path: Path) -> None:
    """禁用 delta_handler_registry seam + provider 时 compile 必须失败。"""
    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - id: lca-delta-handler-registry-seam
    disabled: true
  - id: lca-delta-handler-provider
    disabled: true
"""
    profile_path = tmp_path / "test-missing-delta-handler.yaml"
    profile_path.write_text(profile_content)

    resolved = resolve_profile(profile_path)
    with pytest.raises(MissingBindingError, match="delta_handler_registry"):
        validate_runtime_closure(resolved)


def test_missing_evidence_store_fails_closure_validation(tmp_path: Path) -> None:
    """禁用 evidence_store seam 时 compile 必须失败（生产 profile）。"""
    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - id: lca-evidence-store-seam
    disabled: true
"""
    profile_path = tmp_path / "test-missing-evidence.yaml"
    profile_path.write_text(profile_content)

    resolved = resolve_profile(profile_path)
    with pytest.raises(MissingBindingError, match="evidence_store"):
        validate_runtime_closure(resolved)


def test_missing_reducer_fails_closure_validation(tmp_path: Path) -> None:
    """禁用 reducer plugin 时必须失败（ADR-0076 §四）。

    NOTE(round-0358): 依赖图收紧后缺失在 resolve 期即硬失败
    (ProfileResolveError: phase.think.route requires 'reducer'),到不了
    validate_runtime_closure;硬失败保证前移到了更早的层级,此处据实断言。
    """
    from lca.harness.profile.validate.errors import ProfileResolveError

    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - id: lca-default-reducer
    disabled: true
"""
    profile_path = tmp_path / "test-missing-reducer.yaml"
    profile_path.write_text(profile_content)

    with pytest.raises(ProfileResolveError, match="reducer"):
        resolve_profile(profile_path)


def test_default_reducer_plugin_declares_reducer_capability() -> None:
    """lca-default-reducer 必须声明 ``provides=["reducer"]``（ADR-0076 §三）。"""
    from lca.plugins.loop.reducer.plugin import setup

    defn = setup._lca_definition
    assert "reducer" in defn.provided_capability_keys, (
        "Default reducer plugin must declare provides=['reducer'] for W1 closure binding"
    )


def test_base_bundle_wires_reducer() -> None:
    """bundles/base.yaml 必须显式挂载生产运行时消费的 reducer plugin。"""
    bundle_text = Path("bundles/base.yaml").read_text()
    assert "lca-default-reducer" in bundle_text


def test_reducer_capability_appears_in_compiled_plan() -> None:
    """compile_plan 必须把 reducer binding 投影为 required_in_production=True。"""
    resolved = resolve_profile("profiles/web-standard.yaml")
    plan = compile_plan(resolved, options=CompileOptions())
    reducer_bindings = [b for b in plan.capability.provider_bindings if b.capability == "reducer"]
    assert reducer_bindings, "reducer binding missing from compiled plan"
    binding = reducer_bindings[0]
    assert binding.required_in_production is True
    assert binding.fallback_policy == "production"


def test_missing_binding_error_message_is_helpful() -> None:
    """MissingBindingError 消息必须包含 capability 名称、provider_hint 与 candidates。"""
    error = MissingBindingError(
        "test_capability",
        "bundle or profile patch",
        fallback_policy=FallbackPolicy.PRODUCTION,
        provider_hint="lca.plugins.<area>.test_capability_seam",
        candidates=("bundle: bundles/base.yaml", "plugin: lca-test-capability-seam"),
    )
    msg = str(error)
    assert "test_capability" in msg
    assert "bundle or profile patch" in msg
    assert "lca.plugins.<area>.test_capability_seam" in msg
    assert "bundle: bundles/base.yaml" in msg
    assert error.capability == "test_capability"
    assert error.expected_source == "bundle or profile patch"
    assert error.fallback_policy is FallbackPolicy.PRODUCTION
    assert error.provider_hint == "lca.plugins.<area>.test_capability_seam"


def test_fallback_policy_test_default_passes(tmp_path: Path) -> None:
    """profile 声明 ``fallback_policy: <cap>: test_default`` 时 validator 放行。"""
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
    # 不应抛出 MissingBindingError（test_default 放行）
    validate_runtime_closure(resolved)


def test_profile_allows_test_defaults_only_for_runtime_closure_capabilities(
    tmp_path: Path,
) -> None:
    """只有必需运行能力的 test_default 才能使 Profile 成为 fixture 范围。"""
    runtime_profile = tmp_path / "runtime-test-default.yaml"
    runtime_profile.write_text(
        """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
fallback_policy:
  evidence_store: test_default
"""
    )
    assert profile_allows_test_defaults(resolve_profile(runtime_profile)) is True

    unrelated_profile = tmp_path / "unrelated-test-default.yaml"
    unrelated_profile.write_text(
        """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
fallback_policy:
  unrelated_capability: test_default
"""
    )
    assert profile_allows_test_defaults(resolve_profile(unrelated_profile)) is False


def test_fallback_policy_off_passes(tmp_path: Path) -> None:
    """profile 声明 ``fallback_policy: <cap>: 'off'`` 时 validator 放行。

    YAML 把裸 ``off`` 解析成 Python ``False``，所以策略值必须用引号
    包裹成字符串。profile 校验接受字符串 ``"off"`` 与 ``False`` 两种形态
    （YAML 兼容性）。
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
    # 不应抛出 MissingBindingError（off 放行）
    validate_runtime_closure(resolved)


def test_fallback_policy_production_does_not_relax(tmp_path: Path) -> None:
    """profile 声明 ``fallback_policy: <cap>: production`` 时硬失败不被放行。"""
    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - id: lca-evidence-store-seam
    disabled: true
fallback_policy:
  evidence_store: production
"""
    profile_path = tmp_path / "test-fallback-production.yaml"
    profile_path.write_text(profile_content)

    resolved = resolve_profile(profile_path)
    with pytest.raises(MissingBindingError, match="evidence_store"):
        validate_runtime_closure(resolved)


def test_fallback_policy_invalid_value_rejected(tmp_path: Path) -> None:
    """profile 声明非法 fallback_policy 值时 resolve 阶段必须失败。"""
    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
fallback_policy:
  evidence_store: nonsense
"""
    profile_path = tmp_path / "test-fallback-invalid.yaml"
    profile_path.write_text(profile_content)

    from lca.harness.profile.resolve.resolve import ProfileResolveError

    with pytest.raises(ProfileResolveError, match="fallback_policy"):
        resolve_profile(profile_path)


def test_fallback_policy_not_mapping_rejected(tmp_path: Path) -> None:
    """profile 顶层 fallback_policy 非 mapping 时 resolve 阶段必须失败。"""
    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
fallback_policy: "just_a_string"
"""
    profile_path = tmp_path / "test-fallback-not-mapping.yaml"
    profile_path.write_text(profile_content)

    from lca.harness.profile.resolve.resolve import ProfileResolveError

    with pytest.raises(ProfileResolveError, match="fallback_policy"):
        resolve_profile(profile_path)


def test_all_golden_profiles_have_complete_runtime_closure() -> None:
    """所有 golden profile 都必须有完整的 runtime closure。

    验收标准（W1 §144）：web-standard、standard-solo、standard-team、
    coding-agent、hitl-loop 等生产 profile 都能通过 runtime closure 验证。
    缺失文件的 profile 自动跳过（不在仓库时）；断言集合至少非空。
    """
    seen = 0
    for profile_path in _GOLDEN_PROFILES:
        if not Path(profile_path).exists():
            continue
        seen += 1
        resolved = resolve_profile(profile_path)
        validator = RuntimeBindingValidator()
        # 不应抛出 MissingBindingError
        validator.validate(resolved)
    assert seen >= 1, "at least one golden profile must exist"


def test_candidate_list_provenance_includes_disabled_plugin(tmp_path: Path) -> None:
    """MissingBindingError 候选列表必须包含被禁用 plugin 的 provenance。"""
    profile_content = """
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - id: lca-evidence-store-seam
    disabled: true
"""
    profile_path = tmp_path / "test-candidates.yaml"
    profile_path.write_text(profile_content)

    resolved = resolve_profile(profile_path)
    try:
        validate_runtime_closure(resolved)
    except MissingBindingError as exc:
        # 候选中应包含被禁用的 evidence seam plugin id
        candidate_blob = "\n".join(exc.candidates)
        assert "lca-evidence-store-seam" in candidate_blob
        # 应包含 provenance 路径信息
        assert "evidence_store" in candidate_blob or "evidence" in candidate_blob
        return
    pytest.fail("expected MissingBindingError")


__all__ = [
    "test_all_golden_profiles_have_complete_runtime_closure",
    "test_candidate_list_provenance_includes_disabled_plugin",
    "test_compile_plan_validates_runtime_closure",
    "test_default_profile_provides_required_bindings",
    "test_fallback_policy_invalid_value_rejected",
    "test_fallback_policy_not_mapping_rejected",
    "test_fallback_policy_off_passes",
    "test_fallback_policy_production_does_not_relax",
    "test_fallback_policy_test_default_passes",
    "test_missing_binding_error_message_is_helpful",
    "test_missing_delta_handler_registry_fails_closure_validation",
    "test_missing_effect_handler_registry_fails_closure_validation",
    "test_missing_evidence_store_fails_closure_validation",
    "test_profile_allows_test_defaults_only_for_runtime_closure_capabilities",
    "test_runtime_closure_requirements_not_empty",
]


def test_fallback_policy_true_is_not_treated_as_yaml_off(tmp_path: Path) -> None:
    profile_content = """
bundles:
  - bundles/base.yaml
fallback_policy:
  evidence_store: true
"""
    profile_path = tmp_path / "test-fallback-true.yaml"
    profile_path.write_text(profile_content)

    from lca.harness.profile.resolve.resolve import ProfileResolveError

    with pytest.raises(ProfileResolveError, match="fallback_policy"):
        resolve_profile(profile_path)
