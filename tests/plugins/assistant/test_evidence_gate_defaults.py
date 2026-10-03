# -*- coding: utf-8 -*-
"""ADR-0262 C4 证据门默认值一致性钉。

SSOT：`lca.contracts.protocols.think.learning` 的
`SKILL_ACQUISITION_MIN_CONFIDENCE` / `SKILL_ACQUISITION_MIN_EVIDENCE`。
auto_acquire 与 evolve 两处 Config 的默认值必须引用该常量，
防止阈值在两个实现里悄悄漂移。

状态（2026-10-03）：evolve 的 `min_evidence` 默认仍为 1，源码侧已用
`# ADR-0262 C4 pending` 注释标记，收紧到 3 之前须先由 tests lane
解耦共享 digest fixture（默认携带 2 refs 的测试会误红）。本文件把
"当前为 1"钉住——收紧落地时此处必须同步改为 == 常量。
"""

from __future__ import annotations

import inspect

from lca.contracts.protocols.think.learning import (
    SKILL_ACQUISITION_MIN_CONFIDENCE,
    SKILL_ACQUISITION_MIN_EVIDENCE,
)
from lca.plugins.assistant.evolve.evolve import (
    AssistantEvolveImpl,
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


def test_evolve_min_evidence_still_pending_tighten() -> None:
    # ADR-0262 C4 pending：evolve min_evidence 1 -> 3 的收紧尚未落地
    # （digest fixture 解耦前置）。钉住当前值，收紧时同步更新本断言。
    cfg = EvolveConfig()
    assert cfg.min_evidence == 1
    params = inspect.signature(AssistantEvolveImpl.__init__).parameters
    assert params["min_evidence"].default == 1
