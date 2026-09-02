"""ADR-0174 PR-7.2:benchmark profile 装配回归测试。

benchmark 是 ADR-0174 §D1 第 1 批迁的 profile 之一,保证:
- 加载 ``profiles/benchmark.yaml`` 不抛
- bundle 展开 + patch 合并 + 环境引用展开均成功
- 解析后 ``observability`` 段可读(``loop_cursor`` / ``projection_host`` /
  ``persistence`` / ``model_visible`` / ``close_barrier`` 五段齐备)
- ``loop_cursor.spine_minimal`` bundle(ADR-0174 §D2 命名)被正确引用
- benchmark 专用裁剪:``projection_host.initial`` 是精简子集,
  ``model_visible`` 默认关闭(降低成本干扰项)。
- patch 段保留 ``lca-llm-resolver``(虽在 benchmark 通常不调,但保持装配完整)

不验证 resolve 全过程(那是 K1b / ``test_resolve_profile``);只验
``load_profile_source`` 适配层无回归。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lca.harness.profile.source import load_profile_source

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "profiles" / "benchmark.yaml"


def test_benchmark_loads_without_error() -> None:
    """``profiles/benchmark.yaml`` 加载不抛(PR-7.2 装配后必须仍可加载)。"""
    src = load_profile_source(PROFILE_PATH)
    assert src is not None
    assert src.bundles == (
        "bundles/base.yaml",
        "bundles/web-app.yaml",
        "bundles/scenario-cordis-creator.yaml",
        "bundles/declarative-phase-graph.yaml",
        "bundles/loop_cursor.spine_minimal.yaml",
    )


def test_benchmark_has_observability_section() -> None:
    """Profile 顶层有 ``observability:`` 段(ADR-0169 §D8 + ADR-0174 §D2 装配入口)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    obs = raw.get("observability")
    assert obs is not None, "benchmark.yaml 缺 observability 段"
    assert "loop_cursor" in obs
    assert "projection_host" in obs
    assert "persistence" in obs
    assert "model_visible" in obs
    assert "close_barrier" in obs


def test_benchmark_loop_cursor_implementation_is_std() -> None:
    """``loop_cursor.implementation`` 是 ``std`` 默认实现。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    lc = raw["observability"]["loop_cursor"]
    assert lc["implementation"] == "std"
    assert lc["spine_minimal"] == "loop_cursor.spine_minimal"


def test_benchmark_projection_host_initial_keys() -> None:
    """benchmark 专用裁剪:projection_host.initial 不含 narrative / graph(降低 deriver cost)。

    仅保留 step_tree + cost — 与 loop_cursor.spine_minimal 排除 4 deriver
    的特性对齐(narrative + graph 被 deriver 排除)。
    """
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    initial = raw["observability"]["projection_host"]["initial"]
    assert isinstance(initial, list)
    assert set(initial) == {"step_tree", "cost"}


def test_benchmark_model_visible_disabled_by_default() -> None:
    """benchmark 默认关闭 model_visible capture(消除 cost 干扰项)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert raw["observability"]["model_visible"]["enabled"] is False


def test_benchmark_close_barrier_enabled() -> None:
    """benchmark 仍启用 close_barrier(coordinate flush 顺序在 cost study 内仍是必要的)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert raw["observability"]["close_barrier"]["enabled"] is True


def test_benchmark_observability_plan_ref() -> None:
    """``observability.plan_ref`` = ``benchmark``。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert raw["observability"]["plan_ref"] == "benchmark"


def test_benchmark_patch_section_preserves_llm_resolver() -> None:
    """patch 段保留 ``lca-llm-resolver``(虽 benchmark 通常不调,但保持装配完整)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    patch = raw.get("patch") or []
    patch_ids = {p.get("id") for p in patch if isinstance(p, dict)}
    assert "lca-llm-resolver" in patch_ids


def test_benchmark_bundles_reference_loop_cursor_spine_minimal() -> None:
    """benchmark 仅引用 ``loop_cursor.spine_minimal``,不带 spine_default / spine_debug。

    与 ADR-0174 §D2 "单 SSOT" 原则一致:benchmark 是 cost study,只装 minimal,
    不与 web-standard / oii-debug 双 bundle 装配重复。
    """
    src = load_profile_source(PROFILE_PATH)
    assert "bundles/loop_cursor.spine_minimal.yaml" in src.bundles
    for legacy in (
        "bundles/loop_cursor.spine_default.yaml",
        "bundles/loop_cursor.spine_debug.yaml",
        "bundles/spine-default.yaml",
        "bundles/spine-benchmark-minimal.yaml",
    ):
        assert legacy not in src.bundles, (
            f"benchmark.yaml 不应引用 {legacy}(ADR-0174 §I-PROF-1 单 SSOT)"
        )


def test_benchmark_each_observability_section_is_mapping() -> None:
    """每一段都是 mapping(装配契约一致)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    obs = raw["observability"]
    for key in ("loop_cursor", "projection_host", "persistence", "model_visible", "close_barrier"):
        section = obs.get(key)
        assert isinstance(section, dict), (
            f"observability.{key} must be mapping, got {type(section).__name__}"
        )
