"""Boot-time ``provides ⊆ actual ctx.provide`` 硬门槛。

回归：幽灵 ``provides`` 不再拖到 spawn/``bind_plan`` 才挂。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.harness.profile.boot import _validate_audited_interactions
from lca.harness.profile.errors import ProfileResolveError


@dataclass
class _FakeDefinition:
    spec: object
    provided_capability_keys: tuple[str, ...]
    required_capability_keys: tuple[str, ...]

    @property
    def id(self) -> str:
        return getattr(self.spec, "id", "test-plugin")


@dataclass
class _FakeSpec:
    id: str = "test-plugin"


@dataclass
class _FakeAudited:
    provided: set[str]
    required: set[str]
    registered: set[tuple[str, str]]


def test_missing_provide_detected() -> None:
    """plugin 声明 ``provides=["x"]`` 但 setup 未 ``ctx.provide("x", …)``。"""
    defn = _FakeDefinition(
        spec=_FakeSpec(),
        provided_capability_keys=("ghost.capability",),
        required_capability_keys=(),
    )
    audited = _FakeAudited(provided=set(), required=set(), registered=set())
    with pytest.raises(ProfileResolveError, match="missing_provide"):
        _validate_audited_interactions(defn, audited)  # type: ignore[arg-type]


def test_register_through_seam_counts_as_provided() -> None:
    """``ctx.require("tools").register(tool)`` 视为 ``tools.bash`` 已兑现。"""
    defn = _FakeDefinition(
        spec=_FakeSpec(),
        provided_capability_keys=("tools.bash",),
        required_capability_keys=("tools",),
    )
    audited = _FakeAudited(
        provided=set(),
        required={"tools"},
        registered=set(),
    )
    # tools.bash 以 required seam "tools" 前缀兑现 — 不应触发 missing_provide
    _validate_audited_interactions(defn, audited)  # type: ignore[arg-type]


def test_explicit_provide_satisfies_declaration() -> None:
    defn = _FakeDefinition(
        spec=_FakeSpec(),
        provided_capability_keys=("session.store",),
        required_capability_keys=(),
    )
    audited = _FakeAudited(provided={"session.store"}, required=set(), registered=set())
    _validate_audited_interactions(defn, audited)  # type: ignore[arg-type]


def test_register_via_ctx_register_counts() -> None:
    """plugin 直接 ``ctx.register("seam", name, …)`` 也算兑现。"""
    defn = _FakeDefinition(
        spec=_FakeSpec(),
        provided_capability_keys=("mode.loop",),
        required_capability_keys=(),
    )
    audited = _FakeAudited(
        provided=set(),
        required=set(),
        registered={("mode.loop", "cognitive")},
    )
    _validate_audited_interactions(defn, audited)  # type: ignore[arg-type]
