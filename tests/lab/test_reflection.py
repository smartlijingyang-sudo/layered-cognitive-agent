"""Tests for ADR-0211 §7 worker reflection protocol.

Verifies:
- Six-semantic-phase worker modules are auto-registered by ``load_all()``
  via ``bind_worker(discover_worker(module_path))``.
- Marker ``requires`` / ``provides`` are derived from typed signature + docstring.
- Worker file has zero framework imports (no LabCarrier / bind_carrier).
- port_to_param mapping from ``in:`` docstring lines.
- Provider escape hatch (``provider: yes`` docstring) skips reflection.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca.plugins.lab.internal.loader import (
    _LAB_HOOKS,
    _HOOK_PACKAGES,
    get_instance,
    load_all,
    reset_for_tests,
)


STAGE_WORKERS = [
    # (stage, basename, expected port mapping, expected config_params subset)
    ("perceive", "sense", {"sensors": "sensors_artifact", "state": "state_artifact"}, set()),
    ("perceive", "resolve", {"state": "state_artifact"}, {"provider_config"}),  # provider_config is config
    ("perceive", "memory", {"memory_ref": "memory_artifact", "state": "state_artifact"}, set()),
    ("perceive", "policy", {"state": "state_artifact"}, set()),
    ("perceive", "trim", {"sensor_items": "sensor_items", "memory_items": "memory_items", "policy_items": "policy_items"}, {"max_chars"}),
    ("perceive", "commit", {"trimmed_items": "trimmed_items"}, set()),
    ("think", "expose", {"in_assembled_manifest": "in_assembled_manifest"}, set()),
    ("think", "reason", {"messages": "messages", "tools": "tools"}, {"adapter_factory", "adapter_kwargs"}),
    ("think", "classify", {"response": "response"}, {"fixture_classifier"}),
    ("think", "guard", {"decision": "decision", "in_state": "in_state"}, {"provider_config", "null_gate", "gate_factory", "fixture_gate_name", "allow_empty_chain", "gate", "out_port"}),
    ("act", "shape", {"decision": "decision"}, set()),
    ("act", "authorize", {"intent": "intent"}, {"allow"}),  # allow is config
    ("act", "compose", {}, set()),  # all params are config
    ("act", "execute", {"authorized": "intent", "body_handle": "body"}, set()),
    ("act", "observe", {"receipt": "observation"}, set()),
    ("reflect", "join", {"in_observation": "in_observation", "in_decision": "in_decision", "in_prior_reflection": "in_prior_reflection"}, set()),
    ("reflect", "critique", {"combined": "combined"}, {"provider_config"}),
    ("reflect", "extract", {"reflection": "reflection"}, set()),
    ("remember", "admit", {"in_observation": "in_observation", "in_candidates": "in_candidates"}, {"provider_config"}),
    ("remember", "commit", {"in_reflection": "in_reflection", "in_observation": "in_observation", "in_decision": "in_decision", "admitted": "admitted"}, {"provider_config"}),
    ("remember", "fold_history", {"session": "session"}, set()),
    ("remember", "snapshot", {"journal_fact": "journal_fact"}, {"provider_config"}),
]


@pytest.fixture(autouse=True)
def _reload():
    import sys

    reset_for_tests()
    # 清空已 import 的 stage worker 模块缓存,强制 load_all 重新执行 module-level code
    # (reflect binding 在模块顶层,所以需要 reimport)。
    for mod_name in list(sys.modules):
        if mod_name.startswith(("lca.plugins.lab.perceive.", "lca.plugins.lab.think.",
                                "lca.plugins.lab.act.", "lca.plugins.lab.reflect.",
                                "lca.plugins.lab.remember.")):
            if mod_name.endswith(".plugin") or mod_name in (
                "lca.plugins.lab.perceive", "lca.plugins.lab.think",
                "lca.plugins.lab.act", "lca.plugins.lab.reflect",
                "lca.plugins.lab.remember",
            ):
                del sys.modules[mod_name]
    load_all()
    yield
    reset_for_tests()


@pytest.mark.parametrize("stage,basename,port_to_param,config_params", STAGE_WORKERS)
def test_reflected_marker_registered(stage, basename, port_to_param, config_params):
    marker_id = f"lab.{stage}.{basename}"
    marker = get_instance(marker_id)
    assert marker is not None, f"{marker_id} missing"
    assert marker["id"] == basename
    assert isinstance(marker["requires"], list)
    assert isinstance(marker["provides"], list)
    # requires 集合 == graph port names
    expected_requires = set(port_to_param.keys())
    assert set(marker["requires"]) == expected_requires, (
        f"{marker_id}: requires {marker['requires']} != {expected_requires}"
    )
    # config_params 是 marker 标注(不在 requires 里)
    assert set(marker.get("config_params", [])) >= config_params, (
        f"{marker_id}: config_params 缺失 {config_params - set(marker.get('config_params', []))}"
    )
    # worker_fn 是 typed function,可调
    assert callable(marker["worker_fn"])


def test_provider_escape_hatch():
    """``provider: yes`` docstring → 跳过反射,走老 ``_CARRIER + bind_carrier`` 路径。"""
    body_provider = get_instance("lab.act.body_provider")
    assert body_provider is not None
    assert body_provider["id"] == "body_provider"
    assert body_provider["stage"] == "composition"
    # 没有 worker_fn(不是反射 worker)
    assert "worker_fn" not in body_provider


def test_worker_files_have_no_framework_imports():
    """worker 文件**零 framework 知识**:不 import LabCarrier / bind_carrier / setup。"""
    base = Path("lca/plugins/lab")
    provider_dirs = {"body_provider"}  # provider 形态除外
    for stage_dir in ("perceive", "think", "act", "reflect", "remember"):
        for sub in (base / stage_dir).iterdir():
            if not sub.is_dir():
                continue
            plugin = sub / "plugin.py"
            if not plugin.exists():
                continue
            text = plugin.read_text()
            if sub.name in provider_dirs:
                continue
            # 任何 worker 不准 import hooks 或 setup()
            for forbidden in ("LabCarrier", "bind_carrier", "from lca.plugins.lab.internal.hooks import"):
                assert forbidden not in text, (
                    f"{plugin}: 含 forbidden import {forbidden!r}"
                )


def test_loader_resolves_stage_aliases():
    """alias: lab.act.shape → lab.act.shape,lab.act.body_provider → 同。"""
    # Alias: "act.shape" should resolve to "lab.act.shape"
    from lca.plugins.lab.internal.hooks import lookup_alias

    assert lookup_alias("lab.act.shape") == "lab.act.shape"
    assert lookup_alias("act.shape") == "lab.act.shape"
    assert lookup_alias("unknown_factory") is None


def test_known_subpackages_includes_stage_modules():
    """_HOOK_PACKAGES 走 dot 路径(测试期望 dot)。"""
    for stage in ("perceive", "think", "act", "reflect", "remember"):
        for sub in (Path(f"lca/plugins/lab/{stage}")).iterdir():
            if sub.is_dir() and (sub / "plugin.py").exists():
                expected = f"lca.plugins.lab.{stage}.{sub.name}.plugin"
                assert expected in _HOOK_PACKAGES, f"{expected} missing from _HOOK_PACKAGES"
