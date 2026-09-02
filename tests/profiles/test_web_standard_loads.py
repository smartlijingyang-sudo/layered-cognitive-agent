"""ADR-0169 PR-25:web-standard profile 装配回归测试。

web-standard 是 ADR-0169 §D11 / ADR-0174 的唯一主 profile;
本测试保证:
- 加载 ``profiles/web-standard.yaml`` 不抛
- bundle 展开 + patch 合并 + 环境引用展开均成功
- 解析后 ``observability`` 段可读(``loop_cursor`` / ``projection_host`` /
  ``persistence`` / ``model_visible`` / ``close_barrier`` 五段齐备)
- 默认 deriver initial 列表有 4 个 key
- 已注册的 plugin 不被新增的 observability 段破坏(entries 数量 ≥ 之前)

不验证 resolve 全过程(那是 K1b / ``test_resolve_profile``);只验
``load_profile_source`` 适配层无回归。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.harness.profile.source import load_profile_source

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "profiles" / "web-standard.yaml"


def test_web_standard_loads_without_error() -> None:
    """``profiles/web-standard.yaml`` 加载不抛(PR-25 装配后必须仍可加载)。"""
    src = load_profile_source(PROFILE_PATH)
    assert src is not None
    assert src.bundles == (
        "bundles/base.yaml",
        "bundles/web-app.yaml",
        "bundles/scenario-cordis-creator.yaml",
        "bundles/declarative-phase-graph.yaml",
        "bundles/spine-default.yaml",
    )


def test_web_standard_has_observability_section() -> None:
    """Profile 顶层有 ``observability:`` 段(ADR-0169 §D8 PR-25 装配入口)。"""
    import yaml

    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    obs = raw.get("observability")
    assert obs is not None, "web-standard.yaml 缺 observability 段"
    assert "loop_cursor" in obs
    assert "projection_host" in obs
    assert "persistence" in obs
    assert "model_visible" in obs
    assert "close_barrier" in obs


def test_web_standard_loop_cursor_implementation_is_std() -> None:
    """``loop_cursor.implementation`` 是 ``std``(默认实现)。"""
    import yaml

    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    lc = raw["observability"]["loop_cursor"]
    assert lc["implementation"] == "std"
    assert lc["spine_default"] == "spine_default"


def test_web_standard_projection_host_initial_keys() -> None:
    """``projection_host.initial`` 列表 = 4 个默认 deriver key。"""
    import yaml

    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    initial = raw["observability"]["projection_host"]["initial"]
    assert isinstance(initial, list)
    assert set(initial) == {"step_tree", "narrative", "graph", "cost"}


def test_web_standard_observability_plan_ref() -> None:
    """``observability.plan_ref`` = ``web-standard``。"""
    import yaml

    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert raw["observability"]["plan_ref"] == "web-standard"


def test_web_standard_bundles_unaffected_by_observability_section() -> None:
    """新增 observability 段不能影响 bundles 列表(Patch / Bundle 阶段已固化)。"""
    src = load_profile_source(PROFILE_PATH)
    # bundles 列表未变
    assert "bundles/spine-default.yaml" in src.bundles
    # entries 数量 > 100(web-standard 是大 profile,通常 ~190)
    assert len(src.entries) >= 100


def test_web_standard_patch_section_still_valid() -> None:
    """Patch 段仍包含 ``lca-llm-resolver`` + ``spine.sink.file``(未受 observability 段影响)。"""
    src = load_profile_source(PROFILE_PATH)
    patch_ids = {entry.get("id") for entry in src.entries}
    # Note:patch 段在 source 层展开后才进入 entries;source.entries 不含 patch
    # (patch 是 profiles yaml 顶层独立段)。这里验证 yaml 顶层 patch 段在
    yaml_raw = __import__("yaml").safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    patch = yaml_raw.get("patch") or []
    patch_ids_yaml = {p.get("id") for p in patch if isinstance(p, dict)}
    assert "lca-llm-resolver" in patch_ids_yaml
    assert "spine.sink.file" in patch_ids_yaml


def test_web_standard_fallback_policy_unchanged() -> None:
    """Profile 的 ``fallback_policy``(若有)未被 observability 段破坏。"""
    import yaml

    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    # web-standard.yaml 当前未声明 fallback_policy;若后续加上则需为 mapping
    fb = raw.get("fallback_policy")
    if fb is not None:
        assert isinstance(fb, dict)


@pytest.mark.parametrize(
    "section_key",
    ["loop_cursor", "projection_host", "persistence", "model_visible", "close_barrier"],
)
def test_web_standard_each_observability_section_is_mapping(section_key: str) -> None:
    """每一段都是 mapping(PR-25 wiring 契约)。"""
    import yaml

    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    section = raw["observability"].get(section_key)
    assert isinstance(section, dict), (
        f"observability.{section_key} must be mapping, got {type(section).__name__}"
    )
