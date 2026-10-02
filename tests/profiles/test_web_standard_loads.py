"""ADR-0169 PR-25 + ADR-0174 PR-7.1/7.2:web-standard profile 装配回归测试。

web-standard 是 ADR-0169 §D11 / ADR-0174 的主 profile;
本测试保证:
- 加载 ``profiles/web-standard.yaml`` 不抛
- bundle 展开 + patch 合并 + 环境引用展开均成功
- observability 接线经 bundle 组合存在(``observability-default`` /
  ``observation-9module`` / ``loop_cursor.spine_default``;内联
  ``observability:`` 段已退役)
- ``loop_cursor.spine_default`` bundle 提供五段 wiring
  (``loop_cursor_factory`` / ``projection_host`` / ``persistence`` /
  ``model_visible`` / ``close_barrier``)
- 默认 deriver 以 bundle entries 声明
- 已注册的 plugin 不被 observability 接线破坏(entries 数量 ≥ 之前)

不验证 resolve 全过程(那是 K1b / ``test_resolve_profile``);只验
``load_profile_source`` 适配层无回归。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.harness.profile.resolve.source import load_profile_source

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "profiles" / "web-standard.yaml"


def test_web_standard_loads_without_error() -> None:
    """``profiles/web-standard.yaml`` 加载不抛(PR-25 装配后必须仍可加载)。"""
    src = load_profile_source(PROFILE_PATH)
    assert src is not None
    assert src.bundles == (
        "bundles/base.yaml",
        "bundles/observability-default.yaml",
        "bundles/observation-9module.yaml",
        "bundles/web-app.yaml",
        "bundles/scenario-cordis-creator.yaml",
        "bundles/loop_cursor.spine_default.yaml",
        "bundles/session-runtime.yaml",
        "bundles/event-bus-components.yaml",
        "bundles/outer/phase_main.yaml",
        "bundles/think/think_subgraph.yaml",
        "bundles/act/act_subgraph.yaml",
        "bundles/perceive/perceive_subgraph.yaml",
        "bundles/reflect/reflect_subgraph.yaml",
        "bundles/remember/remember_subgraph.yaml",
    )


def test_web_standard_has_observability_section() -> None:
    """observability 接线经 bundle 组合存在(内联 ``observability:`` 段已退役)。"""
    src = load_profile_source(PROFILE_PATH)
    assert src is not None
    for bundle in (
        "bundles/observability-default.yaml",
        "bundles/observation-9module.yaml",
        "bundles/loop_cursor.spine_default.yaml",
    ):
        assert bundle in src.bundles, f"web-standard 缺 observability bundle: {bundle}"


def test_web_standard_loop_cursor_implementation_is_std() -> None:
    """``loop_cursor.spine_default`` bundle 提供五段 wiring(ADR-0174 §D2)。"""
    import yaml

    bundle_path = REPO_ROOT / "bundles" / "loop_cursor.spine_default.yaml"
    raw = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    provides = raw.get("provides") or []
    for key in (
        "loop_cursor_factory",
        "projection_host",
        "persistence",
        "model_visible",
        "close_barrier",
    ):
        assert key in provides, f"loop_cursor.spine_default 缺 provides: {key}"


def test_web_standard_projection_host_initial_keys() -> None:
    """默认 deriver 以 bundle entries 声明(内联 ``initial`` 列表已退役)。"""
    import yaml

    bundle_path = REPO_ROOT / "bundles" / "loop_cursor.spine_default.yaml"
    raw = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    entry_ids = {e.get("id") for e in raw.get("entries") or [] if isinstance(e, dict)}
    for deriver in (
        "spine.deriver.anomaly",
        "spine.deriver.narrative",
        "spine.deriver.graph",
        "spine.deriver.live_tail",
    ):
        assert deriver in entry_ids, f"缺默认 deriver: {deriver}"


def test_web_standard_observability_plan_ref() -> None:
    """Retired:内联 ``observability.plan_ref`` 已随内联段退役;plan_ref 现由编译期计算。"""
    pytest.skip("retired: observability.plan_ref 内联字段已退役")


def test_web_standard_bundles_unaffected_by_observability_section() -> None:
    """新增 observability 段不能影响 bundles 列表(Patch / Bundle 阶段已固化)。"""
    src = load_profile_source(PROFILE_PATH)
    # bundles 列表未变
    assert "bundles/loop_cursor.spine_default.yaml" in src.bundles
    # entries 数量 > 100(web-standard 是大 profile,通常 ~190)
    assert len(src.entries) >= 100


def test_web_standard_patch_section_still_valid() -> None:
    """Patch 段仍包含 ``lca-llm-resolver`` + ``spine.sink.file``(未受 observability 段影响)。"""
    # Note:patch 段在 source 层展开后才进入 entries;source.entries 不含 patch
    # (patch 是 profiles yaml 顶层独立段)。这里验证 yaml 顶层 patch 段在
    yaml_raw = __import__("yaml").safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    patch = yaml_raw.get("patch") or []
    patch_ids_yaml = {p.get("id") for p in patch if isinstance(p, dict)}
    assert "spine.sink.file" in patch_ids_yaml
    # lca-llm-resolver 已迁入 bundles/base.yaml(不再是 profile patch)
    base_raw = __import__("yaml").safe_load(
        (REPO_ROOT / "bundles" / "base.yaml").read_text(encoding="utf-8")
    )
    base_ids = {e.get("id") for e in base_raw.get("entries") or [] if isinstance(e, dict)}
    assert "lca-llm-resolver" in base_ids


def test_web_standard_fallback_policy_unchanged() -> None:
    """Profile 的 ``fallback_policy``(若有)未被 observability 段破坏。"""
    import yaml

    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    # web-standard.yaml 当前未声明 fallback_policy;若后续加上则需为 mapping
    fb = raw.get("fallback_policy")
    if fb is not None:
        assert isinstance(fb, dict)


@pytest.mark.parametrize(
    "provided_key",
    ["loop_cursor_factory", "projection_host", "persistence", "model_visible", "close_barrier"],
)
def test_web_standard_each_observability_section_is_mapping(provided_key: str) -> None:
    """每段 wiring 由 bundle provides(PR-25 wiring 契约,内联段已退役)。"""
    import yaml

    bundle_path = REPO_ROOT / "bundles" / "loop_cursor.spine_default.yaml"
    raw = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    provides = raw.get("provides") or []
    assert provided_key in provides, f"bundle 缺 provides: {provided_key}"
