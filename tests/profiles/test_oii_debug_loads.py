"""ADR-0174 PR-7.1:oii-debug profile 装配回归测试。

oii-debug 是 ADR-0174 §D1 第 1 批迁的 profile 之一,保证:
- 加载 ``profiles/oii-debug.yaml`` 不抛
- bundle 展开 + patch 合并 + 环境引用展开均成功
- 解析后 ``observability`` 段可读(``loop_cursor`` / ``projection_host`` /
  ``persistence`` / ``model_visible`` / ``close_barrier`` 五段齐备)
- ``loop_cursor.spine_debug`` bundle(ADR-0174 §D2 命名)被正确引用
- 部署仍保留 ``spine.sink.file`` 的 debug boot-path patch
- bundle 列表含 ``spine_default`` + ``spine_debug`` 双 loop_cursor bundle

不验证 resolve 全过程(那是 K1b / ``test_resolve_profile``);只验
``load_profile_source`` 适配层无回归。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lca.harness.profile.source import load_profile_source

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "profiles" / "oii-debug.yaml"


def test_oii_debug_loads_without_error() -> None:
    """``profiles/oii-debug.yaml`` 加载不抛(PR-7.1 装配后必须仍可加载)。"""
    src = load_profile_source(PROFILE_PATH)
    assert src is not None
    assert src.bundles == (
        "bundles/base.yaml",
        "bundles/web-app.yaml",
        "bundles/scenario-cordis-creator.yaml",
        "bundles/declarative-phase-graph.yaml",
        "bundles/loop_cursor.spine_default.yaml",
        "bundles/loop_cursor.spine_debug.yaml",
    )


def test_oii_debug_has_observability_section() -> None:
    """Profile 顶层有 ``observability:`` 段(ADR-0169 §D8 + ADR-0174 §D2 装配入口)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    obs = raw.get("observability")
    assert obs is not None, "oii-debug.yaml 缺 observability 段"
    assert "loop_cursor" in obs
    assert "projection_host" in obs
    assert "persistence" in obs
    assert "model_visible" in obs
    assert "close_barrier" in obs


def test_oii_debug_loop_cursor_implementation_is_std() -> None:
    """``loop_cursor.implementation`` 是 ``std``(默认实现)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    lc = raw["observability"]["loop_cursor"]
    assert lc["implementation"] == "std"
    assert lc["spine_debug"] == "loop_cursor.spine_debug"


def test_oii_debug_projection_host_initial_keys() -> None:
    """``projection_host.initial`` 列表 = 4 个默认 deriver key(同 web-standard)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    initial = raw["observability"]["projection_host"]["initial"]
    assert isinstance(initial, list)
    assert set(initial) == {"step_tree", "narrative", "graph", "cost"}


def test_oii_debug_observability_plan_ref() -> None:
    """``observability.plan_ref`` = ``oii-debug``。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert raw["observability"]["plan_ref"] == "oii-debug"


def test_oii_debug_bundles_include_loop_cursor_spine_default_and_debug() -> None:
    """oii-debug 同时引用 ``loop_cursor.spine_default`` + ``loop_cursor.spine_debug``。

    debug profile 不能丢掉 spine_default(五缝基础) — 它只是叠 source attacher
    + redact 配置覆盖。
    """
    src = load_profile_source(PROFILE_PATH)
    assert "bundles/loop_cursor.spine_default.yaml" in src.bundles
    assert "bundles/loop_cursor.spine_debug.yaml" in src.bundles


def test_oii_debug_patch_section_preserves_debug_boot_path() -> None:
    """OII 调试关键 invariants:``spine.sink.file`` patch 仍含 debug boot_path。

    防止 PR-7.1 装配改革无意中删去 ``.lca/spine/oii-debug-boot-events.jsonl`` 路径,
    让 OII debug trace 误入生产 journal。
    """
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    patch = raw.get("patch") or []
    sink_entries = [p for p in patch if isinstance(p, dict) and p.get("id") == "spine.sink.file"]
    assert sink_entries, "oii-debug.yaml must keep spine.sink.file patch"
    sink = sink_entries[0]
    assert sink["config"]["boot_path"] == ".lca/spine/oii-debug-boot-events.jsonl"


def test_oii_debug_model_visible_enabled() -> None:
    """OII debug 默认开启 ``model_visible`` capture(close_barrier 启用)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    obs = raw["observability"]
    assert obs["model_visible"]["enabled"] is True
    assert obs["close_barrier"]["enabled"] is True


def test_oii_debug_each_observability_section_is_mapping() -> None:
    """每一段都是 mapping(同 web-standard 契约)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    obs = raw["observability"]
    for key in ("loop_cursor", "projection_host", "persistence", "model_visible", "close_barrier"):
        section = obs.get(key)
        assert isinstance(section, dict), (
            f"observability.{key} must be mapping, got {type(section).__name__}"
        )
