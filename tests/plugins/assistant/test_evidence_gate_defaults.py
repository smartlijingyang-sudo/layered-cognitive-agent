"""ADR-0262 C4 证据门默认值一致性钉。

SSOT：`lca.contracts.protocols.think.learning` 的
`SKILL_ACQUISITION_MIN_CONFIDENCE` / `SKILL_ACQUISITION_MIN_EVIDENCE`。
auto_acquire 与 evolve 两处 Config 的默认值必须引用该常量，
防止阈值在两个实现里悄悄漂移。

状态（2026-10-03）：evolve 的 `min_evidence` 默认仍为 1，源码侧已用
`# ADR-0262 C4 pending` 注释标记。tests lane 已完成解耦前置（共享 digest
fixture 与架构不变量测试的 digest 均已是 3 refs），本文件把"默认必须引用
SSOT 常量 SKILL_ACQUISITION_MIN_EVIDENCE（=3）"钉死为预期红契约——
quality lane 收紧源码默认后转绿，不改测试。
"""

from __future__ import annotations

import inspect

from lca.contracts.protocols.think.learning import (
    SKILL_ACQUISITION_MIN_CONFIDENCE,
    SKILL_ACQUISITION_MIN_EVIDENCE,
)
from lca.plugins.assistant.evolve.evolve import (
    AssistantEvolveImpl,
)
from lca.plugins.assistant.evolve.evolve import (
    Config as EvolveConfig,
)
from lca.plugins.skill.auto_acquire import Config as AutoAcquireConfig


def test_ssot_constants_have_canonical_values() -> None:
    assert SKILL_ACQUISITION_MIN_CONFIDENCE == 0.7
    assert SKILL_ACQUISITION_MIN_EVIDENCE == 3


def test_auto_acquire_config_defaults_reference_ssot() -> None:
    cfg = AutoAcquireConfig()
    assert cfg.min_confidence == SKILL_ACQUISITION_MIN_CONFIDENCE
    assert cfg.min_evidence == SKILL_ACQUISITION_MIN_EVIDENCE


def test_evolve_config_min_confidence_references_ssot() -> None:
    cfg = EvolveConfig()
    assert cfg.min_confidence == SKILL_ACQUISITION_MIN_CONFIDENCE


def test_evolve_impl_init_defaults_reference_ssot() -> None:
    params = inspect.signature(AssistantEvolveImpl.__init__).parameters
    assert params["min_confidence"].default == SKILL_ACQUISITION_MIN_CONFIDENCE


def test_evolve_min_evidence_references_ssot() -> None:
    # ADR-0262 C4 契约钉：evolve min_evidence 默认必须引用 SSOT 常量
    # SKILL_ACQUISITION_MIN_EVIDENCE（=3）。tests lane 解耦前置已完成
    # （test_evolve.py 共享 fixture 与架构不变量 digest 均为 3 refs）；
    # 源码侧收紧尚未落地前本用例预期红，quality lane 收紧后转绿，不改测试。
    cfg = EvolveConfig()
    assert cfg.min_evidence == SKILL_ACQUISITION_MIN_EVIDENCE
    params = inspect.signature(AssistantEvolveImpl.__init__).parameters
    assert params["min_evidence"].default == SKILL_ACQUISITION_MIN_EVIDENCE
