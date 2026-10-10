"""Seam 读侧 accessors 直接单元测试（ADR-0096 读侧补完 / todo-96b）。

覆盖 ``lca/contracts/observability`` 的三个读侧注册表在
``lca/`` 里的生产行为：未装配默认回退、装配后解析、缺失版本 fail-fast、
install 返回旧值以便恢复。间接路径（plugin seam/boot）另有场景测试。
"""

from __future__ import annotations

import pytest

from lca.contracts.observability import EventSpine
from lca.contracts.observability.event.identity_registry import (
    install_identity_provider,
    resolve_identity_provider,
)
from lca.contracts.observability.event.stable_ulid_identity import StableUlidIdentity
from lca.contracts.observability.schemas.envelope_v2_schema import EnvelopeV2Schema
from lca.contracts.observability.schemas.journal_schema_registry import (
    JournalSchemaRegistry,
    install_journal_schema_registry,
    resolve_journal_schema,
)
from lca.contracts.observability.schemas.v2 import SCHEMA_VERSION
from lca.contracts.observability.spine_accessors import (
    resolve_active_spine,
    set_active_spine_accessor,
)


@pytest.fixture()
def clean_identity_slot():
    previous = install_identity_provider(None)
    try:
        yield
    finally:
        install_identity_provider(previous)


@pytest.fixture()
def clean_schema_slot():
    previous = install_journal_schema_registry(None)
    try:
        yield
    finally:
        install_journal_schema_registry(previous)


@pytest.fixture()
def clean_spine_slot():
    previous = set_active_spine_accessor(None)
    try:
        yield
    finally:
        set_active_spine_accessor(previous)


class _StubIdentity:
    def derive(self, *, run_id: str, seq: int, event_type: str) -> str:
        return f"stub:{run_id}:{seq}:{event_type}"


class TestIdentityRegistryReadSide:
    def test_uninstalled_falls_back_to_stable_ulid(self, clean_identity_slot):
        provider = resolve_identity_provider()
        assert isinstance(provider, StableUlidIdentity)

    def test_default_provider_derives_unique_ids(self, clean_identity_slot):
        provider = resolve_identity_provider()
        a = provider.derive(run_id="r1", seq=1, event_type="e")
        b = provider.derive(run_id="r1", seq=2, event_type="e")
        assert a != b and isinstance(a, str)

    def test_install_returns_previous_and_resolves_installed(self, clean_identity_slot):
        stub = _StubIdentity()
        previous = install_identity_provider(stub)
        assert previous is None
        resolved = resolve_identity_provider()
        assert resolved is stub
        assert resolved.derive(run_id="r", seq=0, event_type="t") == "stub:r:0:t"

    def test_restore_returns_to_default(self, clean_identity_slot):
        stub = _StubIdentity()
        install_identity_provider(stub)
        assert resolve_identity_provider() is stub
        install_identity_provider(None)
        assert isinstance(resolve_identity_provider(), StableUlidIdentity)


class _StubSchema:
    def serialize(self, record):  # pragma: no cover - duck-typed stub
        return {"stub": True}

    def deserialize(self, data):  # pragma: no cover - duck-typed stub
        return data


class TestJournalSchemaRegistryReadSide:
    def test_default_resolves_builtin_v2_schema(self, clean_schema_slot):
        schema = resolve_journal_schema()
        assert isinstance(schema, EnvelopeV2Schema)

    def test_default_resolves_by_explicit_version(self, clean_schema_slot):
        schema = resolve_journal_schema(SCHEMA_VERSION)
        assert isinstance(schema, EnvelopeV2Schema)

    def test_installed_registry_missing_version_fails_fast(self, clean_schema_slot):
        registry = JournalSchemaRegistry()
        registry.register("v0.0.0", _StubSchema())
        previous = install_journal_schema_registry(registry)
        assert previous is None
        with pytest.raises(LookupError, match="not registered"):
            resolve_journal_schema()

    def test_installed_registry_used_when_present(self, clean_schema_slot):
        stub = _StubSchema()
        registry = JournalSchemaRegistry()
        registry.register(SCHEMA_VERSION, stub)
        install_journal_schema_registry(registry)
        assert resolve_journal_schema() is stub

    def test_registry_basics(self):
        registry = JournalSchemaRegistry()
        assert registry.name() == "JournalSchemaRegistry"
        assert registry.get("nope") is None
        registry.register("v9", _StubSchema())
        assert "v9" in registry.all()


class TestSpineAccessorsReadSide:
    def test_unwired_resolves_none(self, clean_spine_slot):
        assert resolve_active_spine() is None

    def test_install_accessor_returns_previous_and_resolves(self, clean_spine_slot):
        sentinel = object()

        def getter() -> EventSpine | None:
            return sentinel

        previous = set_active_spine_accessor(getter)
        assert previous is None
        assert resolve_active_spine() is sentinel

    def test_restore_back_to_none(self, clean_spine_slot):
        previous = set_active_spine_accessor(lambda: object())
        assert previous is None
        set_active_spine_accessor(None)
        assert resolve_active_spine() is None
